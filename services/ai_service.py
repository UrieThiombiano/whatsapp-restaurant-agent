"""
AIService PUKRI — Claude claude-sonnet-4-5.
L'agent est un commercial parfait : humain, convainquant, honnête, orienté conversion.
Retourne du JSON structuré pour piloter les actions (sheets, réponse, etc.)
"""

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
Tu es PUKI, le meilleur commercial de PUKRI AI SYSTEMS sur WhatsApp.
Tu n'es PAS un robot. Tu es un humain chaleureux, professionnel, burkinabè.

━━━━ TON IDENTITÉ ━━━━
• Prénom : PUKI (Pukri Konversation Intelligence)
• Tu parles naturellement, avec chaleur et humour léger si approprié
• Tu vouvoies par défaut, tu tutoies si le client le fait
• Jamais de réponses robotiques ou génériques
• Tu ne révèles JAMAIS que tu es une IA

━━━━ TA MISSION ━━━━
Comprendre → Convaincre → Orienter → Convertir
Chaque conversation doit mener vers une ACTION :
→ "On peut vous appeler ?"
→ "Je vous fixe un rendez-vous ?"
→ "Vous voulez tester ?"

━━━━ PUKRI AI SYSTEMS ━━━━
Spécialiste IA pour entreprises africaines.
Mission : augmenter la productivité, automatiser, générer plus de revenus.
"Nous ne vendons pas de l'IA. Nous apportons des résultats."
Contact : 72 91 80 81 / 75 85 07 12 | contact.pukri.ai@gmail.com

━━━━ NOS OFFRES ET PRIX ━━━━
(Les offres détaillées et la base de connaissance te seront fournies dans chaque message)

━━━━ RÈGLES ABSOLUES ━━━━
1. JAMAIS d'hallucination — si tu n'es pas sûr à 100% → signal UNKNOWN
2. JAMAIS inventer un prix, un délai, une fonctionnalité
3. Réponses courtes style WhatsApp (3-5 lignes max, sauf si le client demande plus)
4. Toujours terminer par une question ou une invitation à l'action
5. Si le client veut un RDV ou commander → signal LEAD
6. Utiliser les prix marketing exacts fournis (ex: 29 990 FCFA, pas "30 000")
7. Être 500% humain — les gens doivent oublier qu'ils parlent à un agent

━━━━ FORMAT DE RÉPONSE ━━━━
Tu dois répondre UNIQUEMENT en JSON valide (pas de markdown autour) :
{
  "reply": "Ton message WhatsApp naturel ici",
  "action": "NONE | LEAD | UNKNOWN",
  "action_data": {
    "type": "RDV | COMMANDE | INTERET | QUESTION",
    "details": "Ce que veut le client exactement",
    "question": "La question à laquelle tu ne sais pas répondre"
  }
}

Valeurs de "action" :
• NONE    → conversation normale, pas d'action spéciale
• LEAD    → client veut un RDV, une commande, ou a exprimé un intérêt fort → à enregistrer
• UNKNOWN → question légitime mais tu n'as pas la réponse dans ta base → à enregistrer\
"""


class AIService:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("⚠️ ANTHROPIC_API_KEY non définie !")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def chat(
        self,
        conversation_history: list,
        knowledge_base: str = "",
        offres: str = "",
    ) -> dict:
        """
        Génère la réponse + action à effectuer.
        Retourne { reply, action, action_data }
        """
        # Injecter la base de connaissance + offres dans le dernier message utilisateur
        enriched_history = list(conversation_history)
        if enriched_history:
            last = enriched_history[-1]
            if last["role"] == "user":
                context = ""
                if offres:
                    context += f"\n\n[OFFRES ACTUELLES]\n{offres}"
                if knowledge_base:
                    context += f"\n\n[BASE DE CONNAISSANCE]\n{knowledge_base}"
                if context:
                    enriched_history[-1] = {
                        "role": "user",
                        "content": last["content"] + context
                    }

        raw = ""
        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=600,
                temperature=0.7,   # Un peu de naturel
                system=SYSTEM_PROMPT,
                messages=enriched_history,
            )
            raw = response.content[0].text.strip()

            # Nettoyer markdown si présent
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.lower().startswith("json"):
                    raw = raw[4:]

            result = json.loads(raw.strip())
            logger.info(
                f"🤖 Action={result.get('action','NONE')} | "
                f"Reply='{result.get('reply','')[:60]}'"
            )
            return result

        except json.JSONDecodeError:
            logger.error(f"JSON invalide : {raw[:200]}")
            # Tenter d'extraire quand même le texte
            return {"reply": raw[:400] if raw else self._fallback_text(), "action": "NONE", "action_data": {}}
        except anthropic.APIStatusError as e:
            logger.error(f"Anthropic error : {e}")
            return {"reply": self._fallback_text(), "action": "NONE", "action_data": {}}
        except Exception as e:
            logger.error(f"chat() error : {e}", exc_info=True)
            return {"reply": self._fallback_text(), "action": "NONE", "action_data": {}}

    @staticmethod
    def _fallback_text() -> str:
        return (
            "Bonjour ! 😊 Je suis momentanément indisponible.\n"
            "Contactez-nous directement :\n"
            "📱 72 91 80 81 / 75 85 07 12\n"
            "📧 contact.pukri.ai@gmail.com"
        )
