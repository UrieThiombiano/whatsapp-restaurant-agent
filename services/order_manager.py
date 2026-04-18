"""
OrderManager — Gère le cycle de vie des commandes :
  1. Matching articles (fuzzy + partiel)
  2. Construction du panier
  3. Récapitulatif + demande de confirmation
  4. Finalisation → sauvegarde Google Sheets
"""

import json
import logging
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)


# ── Matching flou ─────────────────────────────────────────────────────────────
def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def find_menu_item(name: str, menu: list) -> Optional[dict]:
    """
    Cherche un article dans le menu avec tolérance aux fautes et abréviations.
    Seuil : similarité >= 0.55 OU contenance partielle.
    """
    if not name or not menu:
        return None

    best_score = 0.0
    best_item  = None

    for item in menu:
        if str(item.get("disponible", "TRUE")).upper() != "TRUE":
            continue

        nom_menu = item.get("nom", "")
        score    = _similarity(name, nom_menu)

        if score > best_score:
            best_score = score
            best_item  = item

    if best_score >= 0.55:
        return best_item

    # Matching partiel : "tieb" → "Thiéboudienne"
    name_lower = name.lower()
    for item in menu:
        if str(item.get("disponible", "TRUE")).upper() != "TRUE":
            continue
        nom_lower = item.get("nom", "").lower()
        if name_lower in nom_lower or nom_lower in name_lower:
            return item

    return None


# ── OrderManager ──────────────────────────────────────────────────────────────
class OrderManager:
    def __init__(self, sheets_service):
        self.sheets = sheets_service

    async def process_order_request(
        self,
        phone: str,
        session: dict,
        requested_items: list,
        menu: list,
        config: dict,
    ) -> dict:
        """
        Construit / met à jour le panier, vérifie la dispo,
        et retourne un récapitulatif + demande de confirmation.
        """
        devise  = config.get("devise", "FCFA")
        cart    = list(session.get("cart", []))  # copie
        added   = []
        missing = []

        for req in requested_items:
            nom = req.get("nom", "").strip()
            try:
                qty = max(1, int(req.get("quantite", 1)))
            except (ValueError, TypeError):
                qty = 1

            if not nom:
                continue

            menu_item = find_menu_item(nom, menu)

            if menu_item:
                nom_exact = menu_item["nom"]
                prix = float(
                    str(menu_item.get("prix", 0))
                    .replace(" ", "")
                    .replace(",", ".")
                    .replace("\xa0", "")
                )

                # Mise à jour panier (incrément si déjà présent)
                existing = next((c for c in cart if c["nom"] == nom_exact), None)
                if existing:
                    existing["quantite"] += qty
                else:
                    cart.append({
                        "id":       menu_item.get("id", ""),
                        "nom":      nom_exact,
                        "prix":     prix,
                        "quantite": qty,
                        "emoji":    menu_item.get("emoji", "•"),
                    })

                added.append(f"{qty}x {nom_exact}")
                logger.info(f"🛒 +{qty}x '{nom_exact}' ({prix} {devise})")
            else:
                missing.append(nom)
                logger.warning(f"⚠️ Article non trouvé : '{nom}'")

        total = sum(i["prix"] * i["quantite"] for i in cart)

        # ── Construction message récapitulatif ────────────────────────────────
        lines = ["📋 *Récapitulatif de votre commande :*\n"]
        for item in cart:
            sous_total = item["prix"] * item["quantite"]
            lines.append(
                f"{item['emoji']} {item['quantite']}x {item['nom']} "
                f"— {sous_total:.0f} {devise}"
            )

        lines.append(f"\n💰 *Total : {total:.0f} {devise}*")

        if missing:
            lines.append(
                f"\n⚠️ Non disponible / non trouvé : _{', '.join(missing)}_"
            )

        if cart:
            lines.append(
                "\n✅ Confirmez avec *OUI*  |  ❌ Annulez avec *NON*"
            )
            state = "awaiting_confirmation"
        else:
            lines = ["😔 Aucun article valide trouvé dans votre commande. "
                     "Tapez *menu* pour voir ce qui est disponible !"]
            state = "idle"

        session["cart"]  = cart
        session["state"] = state

        return {"message": "\n".join(lines), "session": session}

    async def finalize_order(
        self,
        phone: str,
        session: dict,
        config: dict,
    ) -> dict:
        """
        Enregistre la commande confirmée dans Google Sheets
        et notifie le client.
        """
        cart   = session.get("cart", [])
        devise = config.get("devise", "FCFA")

        if not cart:
            session["state"] = "idle"
            return {
                "message": "⚠️ Votre panier est vide. Passez une commande d'abord !",
                "session": session,
            }

        total    = sum(i["prix"] * i["quantite"] for i in cart)
        order_id = (
            f"CMD-{datetime.now().strftime('%Y%m%d%H%M')}"
            f"-{uuid.uuid4().hex[:4].upper()}"
        )
        now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        order = {
            "id_commande":  order_id,
            "telephone":    phone,
            "nom_client":   session.get("name") or "",
            "articles_json": json.dumps(cart, ensure_ascii=False),
            "total":        total,
            "statut":       "En attente",
            "horodatage":   now_str,
            "notes":        "",
        }

        saved = await self.sheets.save_order(order)

        # Config
        delai     = config.get("delai_livraison", "30–45 min")
        nom_resto = config.get("restaurant_nom", "notre restaurant")
        contact   = config.get("telephone_contact", "")

        if saved:
            msg_lines = [
                "🎉 *Commande confirmée !*\n",
                f"📋 Référence : `{order_id}`",
                f"💰 Total : *{total:.0f} {devise}*",
                f"⏱️ Délai estimé : *{delai}*",
                "",
                f"Merci pour votre confiance ! {nom_resto} prépare votre commande 🍽️",
            ]
            if contact:
                msg_lines.append(f"📞 Questions ? Appelez le {contact}")
        else:
            msg_lines = [
                f"⚠️ Votre commande est reçue (réf. `{order_id}`) "
                f"mais un problème d'enregistrement s'est produit.",
                f"Merci d'appeler {contact or 'le restaurant'} pour confirmation. 🙏",
            ]

        # Réinitialiser la session
        session["cart"]          = []
        session["state"]         = "idle"
        session["pending_order"] = None

        return {"message": "\n".join(msg_lines), "session": session}
