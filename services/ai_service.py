"""
AIService — Utilise Claude (Anthropic) pour :
  1. Détecter l'intention du client (intent)
  2. Extraire les entités (articles commandés, questions…)
  3. Générer une réponse WhatsApp naturelle et adaptée
"""

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

# ── Prompt système ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
Tu es un assistant WhatsApp pour un restaurant de livraison / vente directe.
Tu dois analyser le message du client et répondre UNIQUEMENT en JSON valide, sans markdown, sans explication.

FORMAT DE RÉPONSE OBLIGATOIRE :
{
  "intent": "<voir liste>",
  "entities": {
    "items": [{"nom": "...", "quantite": 1}],
    "question": "..."
  },
  "reply": "Ton message WhatsApp (max 350 chars, emojis OK, *gras* OK)"
}

LISTE DES INTENTS :
- GREET     : salutation simple, sans demande précise
- MENU      : le client veut voir le menu / la carte
- ORDER     : le client commande (extrait items + quantités dans entities.items)
- CONFIRM   : le client confirme sa commande (oui, ok, c'est bon, confirme, yes…)
- CANCEL    : le client annule (non, annuler, stop, laisse tomber…)
- CART      : le client veut voir son panier actuel
- INFO      : question générale sur le restaurant (adresse, mode de paiement…)
- HOURS     : question sur les horaires d'ouverture
- FALLBACK  : message incompréhensible, hors sujet ou demande impossible

RÈGLES IMPORTANTES :
1. Pour ORDER : fais un matching tolérant aux fautes (ex: "tieb" → "Thiéboudienne")
2. Ne mentionne JAMAIS un article qui n'est pas dans le menu fourni
3. Si un article demandé n'existe pas, indique-le poliment dans la reply
4. Sois chaleureux, concis, professionnel — 1 emoji max par phrase
5. Si la session est en état "awaiting_confirmation", rappelle-le si pertinent
6. Ne réponds JAMAIS hors du JSON demandé\
"""


class AIService:
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY", "")
        )

    async def analyze(
        self,
        text: str,
        session: dict,
        menu: list,
        config: dict,
    ) -> dict:
        """
        Analyse un message client et retourne { intent, entities, reply }.
        """
        menu_ctx    = self._build_menu_ctx(menu, config)
        session_ctx = self._build_session_ctx(session)

        user_msg = (
            f"CONFIG RESTAURANT : {json.dumps(config, ensure_ascii=False)}\n"
            f"MENU DISPONIBLE : {menu_ctx}\n"
            f"SESSION CLIENT : {session_ctx}\n"
            f"MESSAGE CLIENT : \"{text}\"\n\n"
            "Analyse ce message. Réponds uniquement en JSON."
        )

        raw = ""
        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text.strip()

            # Nettoyer d'éventuels blocs markdown
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.lower().startswith("json"):
                    raw = raw[4:]

            result = json.loads(raw.strip())
            logger.info(f"🤖 Intent={result.get('intent')} | Items={result.get('entities', {}).get('items', [])}")
            return result

        except json.JSONDecodeError:
            logger.error(f"JSON invalide de l'IA : {raw[:300]}")
            return self._fallback_response()
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error : {e}")
            return self._fallback_response()
        except Exception as e:
            logger.error(f"analyze() error : {e}", exc_info=True)
            return self._fallback_response()

    # ── Helpers ────────────────────────────────────────────────────────────────
    @staticmethod
    def _build_menu_ctx(menu: list, config: dict) -> str:
        devise = config.get("devise", "FCFA")
        parts  = []
        for item in menu:
            dispo = str(item.get("disponible", "TRUE")).upper()
            if dispo == "TRUE":
                parts.append(
                    f"{item.get('nom')} [{item.get('categorie')}] "
                    f"{item.get('prix')} {devise}"
                )
        return " | ".join(parts[:40])  # Limite la taille du contexte

    @staticmethod
    def _build_session_ctx(session: dict) -> str:
        cart_str = ", ".join(
            f"{i.get('quantite')}x {i.get('nom')}"
            for i in session.get("cart", [])
        )
        return (
            f"état={session.get('state', 'idle')} | "
            f"nom={session.get('name', '?')} | "
            f"panier=[{cart_str}]"
        )

    @staticmethod
    def _fallback_response() -> dict:
        return {
            "intent": "FALLBACK",
            "entities": {},
            "reply": (
                "😊 Je n'ai pas bien compris votre message.\n"
                "Vous pouvez :\n• Taper *menu* pour voir la carte\n"
                "• Me dicter votre commande\n• Nous appeler directement !"
            ),
        }
