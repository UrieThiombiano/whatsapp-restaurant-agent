"""
AIService PUKRI — Claude claude-sonnet-4-5.
Version 3 : Anti-hallucination renforcée + prix donnés directement + ton naturel.
"""

import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Tu es PUKI, commercial de PUKRI AI SYSTEMS sur WhatsApp.
Tu es humain, chaleureux, direct. Tu parles comme un Burkinabè professionnel.

━━━━ RÈGLES ABSOLUES — NE JAMAIS VIOLER ━━━━

🚫 RÈGLE 1 — ZÉRO HALLUCINATION
Tu ne mentionnes QUE ce qui est dans la BASE DE CONNAISSANCE et les OFFRES fournies.
Interdit d'inventer : certificats, vidéos, exercices, modules, fonctionnalités, délais, garanties.
Si tu n'as pas l'info → action UNKNOWN, tu dis que tu vas vérifier.

🚫 RÈGLE 2 — DONNER LES PRIX IMMÉDIATEMENT
Quand un client demande les prix, les tarifs, combien ça coûte → tu donnes DIRECTEMENT les prix du Sheet.
JAMAIS de "ça dépend", JAMAIS de questions avant de donner les prix.
Tu donnes d'abord les prix, PUIS tu peux poser une question si utile.

🚫 RÈGLE 3 — PAS DE MENSONGE PAR OMISSION
Si on demande le prix d'une formation individuelle en ligne → tu donnes "29 990 FCFA / séance".
Point. Pas d'esquive, pas de "j'ai besoin de vérifier avec l'équipe".

━━━━ PUKRI AI SYSTEMS ━━━━
Spécialiste IA pour entreprises africaines.
Contact : 72 91 80 81 / 75 85 07 12 | contact.pukri.ai@gmail.com
"Nous ne vendons pas de l'IA. Nous apportons des résultats."

━━━━ TA MISSION COMMERCIALE ━━━━
Comprendre → Informer honnêtement → Convaincre → Convertir
Chaque échange doit mener vers : appel / RDV / inscription.
Mais d'abord : répondre clairement à ce qu'on te demande.

━━━━ PERSONNALITÉ ━━━━
• Chaleureux, direct, jamais robotique
• Réponses courtes WhatsApp (3-5 lignes max)
• Vouvoiement par défaut
• Jamais dire que tu es une IA
• Terminer par une question ou une invitation à l'action

━━━━ FORMAT JSON OBLIGATOIRE ━━━━
Réponds UNIQUEMENT en JSON valide (sans markdown autour) :
{
  "reply": "Ton message WhatsApp ici",
  "action": "NONE | LEAD | UNKNOWN",
  "action_data": {
    "type": "RDV | COMMANDE | INTERET | QUESTION",
    "details": "Détails du lead",
    "question": "Question sans réponse dans la base"
  }
}

Actions :
• NONE    → réponse normale
• LEAD    → client veut RDV, commande, ou intérêt fort confirmé → enregistrer
• UNKNOWN → question légitime sans réponse dans ta base → enregistrer + dire qu'on revient\
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
        enriched_history = list(conversation_history)

        if enriched_history:
            last = enriched_history[-1]
            if last["role"] == "user":
                context_parts = []
                if offres:
                    context_parts.append(f"[OFFRES ET TARIFS EXACTS — À UTILISER DIRECTEMENT]\n{offres}")
                if knowledge_base:
                    context_parts.append(f"[BASE DE CONNAISSANCE — SEULES INFOS AUTORISÉES]\n{knowledge_base}")
                if context_parts:
                    context_parts.append(
                        "[RAPPEL] Si le client demande un prix → donne-le IMMÉDIATEMENT depuis les offres ci-dessus. "
                        "N'invente rien qui n'est pas listé."
                    )
                    enriched_history[-1] = {
                        "role": "user",
                        "content": last["content"] + "\n\n" + "\n\n".join(context_parts)
                    }

        raw = ""
        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=500,
                temperature=0.5,
                system=SYSTEM_PROMPT,
                messages=enriched_history,
            )
            raw = response.content[0].text.strip()

            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.lower().startswith("json"):
                    raw = raw[4:]

            result = json.loads(raw.strip())
            logger.info(f"🤖 Action={result.get('action','NONE')} | Reply='{result.get('reply','')[:80]}'")
            return result

        except json.JSONDecodeError:
            logger.error(f"JSON invalide : {raw[:200]}")
            return {"reply": raw[:400] if raw else self._fallback(), "action": "NONE", "action_data": {}}
        except anthropic.APIStatusError as e:
            logger.error(f"Anthropic error : {e}")
            return {"reply": self._fallback(), "action": "NONE", "action_data": {}}
        except Exception as e:
            logger.error(f"chat() error : {e}", exc_info=True)
            return {"reply": self._fallback(), "action": "NONE", "action_data": {}}

    @staticmethod
    def _fallback() -> str:
        return (
            "Bonjour ! 😊 Je suis momentanément indisponible.\n"
            "Contactez-nous directement :\n"
            "📱 72 91 80 81 / 75 85 07 12\n"
            "📧 contact.pukri.ai@gmail.com"
        )
