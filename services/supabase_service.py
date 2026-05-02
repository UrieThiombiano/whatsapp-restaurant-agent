"""
SupabaseService — Mémoire persistante de l'agent PUKRI.
Stocke l'historique des conversations par client.
L'agent se souvient même après redémarrage du serveur.

Table : conversations
  id         uuid PK auto
  phone      text  (numéro client)
  name       text  (prénom/nom WhatsApp)
  role       text  ('user' | 'assistant')
  content    text  (contenu du message)
  topics     text  (sujets abordés, séparés par virgule)
  created_at timestamptz auto

On garde les 5 dernières sessions = ~50 messages max par client.
"""

import logging
import os
from datetime import datetime, timezone

from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Nombre de messages à charger pour le contexte IA (5 sessions ≈ 40 messages)
MAX_MESSAGES_LOADED = 40
# Nombre max de messages conservés en base par client (nettoyage auto)
MAX_MESSAGES_STORED = 100


class SupabaseService:
    def __init__(self):
        url = os.getenv("SUPABASE_URL", "https://bchzfrtiocizylqiwloh.supabase.co")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not key:
            logger.warning("⚠️ SUPABASE_SERVICE_KEY non définie !")
        try:
            self._client: Client = create_client(url, key)
            logger.info("✅ Supabase connecté")
        except Exception as e:
            logger.error(f"❌ Supabase connexion échouée : {e}")
            self._client = None

    # ── Charger l'historique d'un client ──────────────────────────────────────
    async def load_history(self, phone: str) -> list[dict]:
        """
        Retourne les N derniers messages du client sous forme
        [{"role": "user"|"assistant", "content": "..."}]
        prêts à être injectés dans Claude.
        """
        if not self._client:
            return []
        try:
            resp = (
                self._client.table("conversations")
                .select("role, content, created_at")
                .eq("phone", phone)
                .order("created_at", desc=True)
                .limit(MAX_MESSAGES_LOADED)
                .execute()
            )
            rows = resp.data or []
            # Inverser pour avoir l'ordre chronologique
            rows.reverse()
            history = [{"role": r["role"], "content": r["content"]} for r in rows]
            logger.info(f"📚 Historique chargé : {phone} → {len(history)} messages")
            return history
        except Exception as e:
            logger.error(f"❌ load_history : {e}")
            return []

    # ── Charger les métadonnées d'un client ───────────────────────────────────
    async def load_client_meta(self, phone: str) -> dict:
        """
        Retourne { name, last_seen, topics } pour ce client.
        """
        if not self._client:
            return {}
        try:
            resp = (
                self._client.table("conversations")
                .select("name, topics, created_at")
                .eq("phone", phone)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if resp.data:
                row = resp.data[0]
                return {
                    "name":      row.get("name", ""),
                    "last_seen": row.get("created_at", ""),
                    "topics":    [t.strip() for t in (row.get("topics") or "").split(",") if t.strip()],
                }
            return {}
        except Exception as e:
            logger.error(f"❌ load_client_meta : {e}")
            return {}

    # ── Sauvegarder un message ─────────────────────────────────────────────────
    async def save_message(
        self,
        phone: str,
        name: str,
        role: str,
        content: str,
        topics: list = None,
    ) -> bool:
        """
        Insère un message en base.
        role = 'user' ou 'assistant'
        """
        if not self._client or not content:
            return False
        try:
            self._client.table("conversations").insert({
                "phone":      phone,
                "name":       name or "",
                "role":       role,
                "content":    content[:4000],  # Limite sécurité
                "topics":     ",".join(topics or []),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            return True
        except Exception as e:
            logger.error(f"❌ save_message : {e}")
            return False

    # ── Nettoyage auto (garder seulement les N derniers messages) ──────────────
    async def cleanup_old_messages(self, phone: str) -> None:
        """
        Supprime les anciens messages si le client en a trop.
        Appelé de temps en temps pour ne pas saturer la base.
        """
        if not self._client:
            return
        try:
            # Compter les messages
            count_resp = (
                self._client.table("conversations")
                .select("id", count="exact")
                .eq("phone", phone)
                .execute()
            )
            total = count_resp.count or 0

            if total > MAX_MESSAGES_STORED:
                # Trouver l'ID du Nème message en partant de la fin
                cutoff_resp = (
                    self._client.table("conversations")
                    .select("created_at")
                    .eq("phone", phone)
                    .order("created_at", desc=True)
                    .limit(1)
                    .offset(MAX_MESSAGES_STORED - 1)
                    .execute()
                )
                if cutoff_resp.data:
                    cutoff_date = cutoff_resp.data[0]["created_at"]
                    self._client.table("conversations").delete().eq(
                        "phone", phone
                    ).lt("created_at", cutoff_date).execute()
                    logger.info(f"🧹 Nettoyage {phone} : {total - MAX_MESSAGES_STORED} messages supprimés")
        except Exception as e:
            logger.error(f"❌ cleanup : {e}")

    # ── Test de connexion ──────────────────────────────────────────────────────
    async def ping(self) -> bool:
        if not self._client:
            return False
        try:
            self._client.table("conversations").select("id").limit(1).execute()
            return True
        except Exception:
            return False

    # ── Offres spéciales ───────────────────────────────────────────────────────
    async def get_active_offers(self) -> list[dict]:
        """
        Retourne toutes les offres spéciales actives.
        Filtre par date_fin si définie.
        """
        if not self._client:
            return []
        try:
            from datetime import date
            today = date.today().isoformat()
            resp = (
                self._client.table("special_offers")
                .select("*")
                .eq("actif", True)
                .or_(f"date_fin.is.null,date_fin.gte.{today}")
                .order("ordre")
                .execute()
            )
            offers = resp.data or []
            logger.info(f"✅ {len(offers)} offre(s) spéciale(s) active(s)")
            return offers
        except Exception as e:
            logger.error(f"❌ get_active_offers : {e}")
            return []

    async def get_offers_summary(self) -> str:
        """
        Retourne un résumé texte des offres actives pour injection dans le prompt IA.
        """
        offers = await self.get_active_offers()
        if not offers:
            return ""
        lines = ["OFFRES SPÉCIALES EN COURS :"]
        for o in offers:
            line = f"• {o['titre']} | Cible: {o['cible']} | Prix: {o['prix']}"
            if o.get("date_debut"):
                line += f" | Date: {o['date_debut']}"
            if o.get("lien_inscription"):
                line += f" | Lien: {o['lien_inscription']}"
            lines.append(line)
        return "\n".join(lines)
