"""
LeadService — Qualification des leads + Relances automatiques.

Fonctionnement :
  1. Chaque conversation est analysée pour extraire le profil client
  2. Un score 0-100 est calculé selon le budget, délai, rôle
  3. Des relances sont planifiées automatiquement (J+1, J+3, J+7)
  4. L'endpoint /process-followups envoie les relances dues
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ── Scoring des leads ─────────────────────────────────────────────────────────
SCORE_RULES = {
    "delai_achat": {
        "immédiat":           40,
        "ce mois":            30,
        "3 mois":             15,
        "pas encore décidé":   5,
    },
    "budget": {
        "plus de 100k":       30,
        "30k-100k":           20,
        "moins de 30k":       10,
        "non précisé":         5,
    },
    "role": {
        "dirigeant":          20,
        "entrepreneur":       18,
        "salarié":            10,
        "étudiant":            7,
        "autre":               5,
    },
    "service_vise": {
        "agent_ia":           10,
        "consulting":          8,
        "formation":           6,
        "autre":               3,
    }
}

# ── Messages de relance ───────────────────────────────────────────────────────
FOLLOWUP_SEQUENCES = {
    1: {  # J+1
        "formation": (
            "Bonjour {prenom} ! 😊\n"
            "Je voulais juste m'assurer que vous avez bien reçu nos informations sur la formation IA.\n"
            "Avez-vous eu le temps d'y réfléchir ? Je suis là si vous avez des questions !"
        ),
        "consulting": (
            "Bonjour {prenom} ! 😊\n"
            "Suite à notre échange sur le consulting IA, je voulais vérifier que vous avez bien tout reçu.\n"
            "Un audit IA de votre activité peut vraiment changer la donne. On en parle ?"
        ),
        "agent_ia": (
            "Bonjour {prenom} ! 😊\n"
            "J'espère que vous avez bien reçu les infos sur nos agents IA.\n"
            "Un agent disponible 24h/24 pour vos clients — vous voyez le potentiel ?"
        ),
        "default": (
            "Bonjour {prenom} ! 😊\n"
            "Je voulais juste prendre de vos nouvelles suite à notre échange chez PUKRI AI SYSTEMS.\n"
            "Avez-vous des questions ? Je suis là pour vous aider !"
        )
    },
    3: {  # J+3
        "default": (
            "Bonjour {prenom} 👋\n"
            "Je repassais voir si vous avez pu réfléchir à nos services.\n"
            "🎯 Rappel : l'IA évolue très vite — ceux qui se forment aujourd'hui auront une longueur d'avance demain.\n"
            "On peut fixer un rapide appel de 10 minutes pour répondre à vos questions ?"
        )
    },
    7: {  # J+7
        "default": (
            "Bonjour {prenom} ! 😊\n"
            "Une dernière fois de ma part — j'aurais voulu vous aider à franchir le pas vers l'IA.\n"
            "Si ce n'est pas le bon moment, pas de souci du tout. 🙏\n"
            "Mais si jamais vous changez d'avis, vous savez où nous trouver :\n"
            "📱 72 91 80 81 / 75 85 07 12\n"
            "📧 contact.pukri.ai@gmail.com\n"
            "Bonne continuation ! 🚀"
        )
    }
}


class LeadService:
    def __init__(self, supabase_svc, whatsapp_svc):
        self.db  = supabase_svc
        self.wa  = whatsapp_svc

    # ── Scoring ───────────────────────────────────────────────────────────────
    def calculate_score(self, qualification: dict) -> int:
        score = 0
        for field, rules in SCORE_RULES.items():
            value = qualification.get(field, "").lower().strip()
            # Chercher une correspondance partielle
            for key, pts in rules.items():
                if key in value:
                    score += pts
                    break
        return min(score, 100)

    def get_lead_status(self, score: int) -> str:
        if score >= 70:  return "chaud"
        elif score >= 40: return "tiède"
        elif score >= 20: return "froid"
        return "nouveau"

    # ── Upsert qualification ──────────────────────────────────────────────────
    async def update_qualification(self, phone: str, nom: str, updates: dict) -> dict:
        """
        Met à jour la qualification d'un lead et recalcule son score.
        Crée l'entrée si elle n'existe pas.
        """
        if not self.db._client:
            return {}
        try:
            # Charger qualification existante
            res = self.db._client.table("lead_qualification").select("*").eq("phone", phone).execute()
            existing = res.data[0] if res.data else {}

            # Merger les updates
            merged = {**existing, **updates, "phone": phone, "nom": nom or existing.get("nom", "")}
            merged["score"]      = self.calculate_score(merged)
            merged["statut"]     = self.get_lead_status(merged["score"])
            merged["updated_at"] = datetime.now(timezone.utc).isoformat()

            if existing:
                self.db._client.table("lead_qualification").update(merged).eq("phone", phone).execute()
                logger.info(f"✅ Lead mis à jour : {phone} | score={merged['score']} | statut={merged['statut']}")
            else:
                self.db._client.table("lead_qualification").insert(merged).execute()
                logger.info(f"✅ Nouveau lead qualifié : {phone} | score={merged['score']}")

            return merged
        except Exception as e:
            logger.error(f"❌ update_qualification : {e}")
            return {}

    # ── Planifier les relances ────────────────────────────────────────────────
    async def schedule_followups(self, phone: str, nom: str, service: str):
        """
        Planifie les 3 relances automatiques : J+1, J+3, J+7.
        Annule les relances pending existantes avant d'en créer de nouvelles.
        """
        if not self.db._client:
            return
        try:
            # Annuler les relances pending existantes pour ce client
            self.db._client.table("followups").update({"statut": "cancelled"}).eq("phone", phone).eq("statut", "pending").execute()

            now = datetime.now(timezone.utc)
            prenom = nom.split()[0] if nom else "vous"

            for days in [1, 3, 7]:
                # Choisir le bon message
                seq_msgs = FOLLOWUP_SEQUENCES.get(days, FOLLOWUP_SEQUENCES[7])
                msg_tpl  = seq_msgs.get(service, seq_msgs.get("default", ""))
                message  = msg_tpl.format(prenom=prenom)

                scheduled = now + timedelta(days=days)
                # Envoyer à 9h heure Ouaga (UTC+0)
                scheduled = scheduled.replace(hour=9, minute=0, second=0, microsecond=0)

                self.db._client.table("followups").insert({
                    "phone":        phone,
                    "nom":          nom,
                    "message":      message,
                    "sequence":     days,
                    "statut":       "pending",
                    "scheduled_at": scheduled.isoformat(),
                }).execute()

            logger.info(f"📅 3 relances planifiées pour {phone} (J+1, J+3, J+7)")
        except Exception as e:
            logger.error(f"❌ schedule_followups : {e}")

    # ── Exécuter les relances dues ────────────────────────────────────────────
    async def process_due_followups(self) -> int:
        """
        Envoie toutes les relances dont l'heure est passée.
        À appeler via l'endpoint /process-followups (cron toutes les 30 min).
        Retourne le nombre de relances envoyées.
        """
        if not self.db._client:
            return 0
        try:
            now = datetime.now(timezone.utc).isoformat()
            res = (
                self.db._client.table("followups")
                .select("*")
                .eq("statut", "pending")
                .lte("scheduled_at", now)
                .order("scheduled_at")
                .limit(20)  # Max 20 relances par batch
                .execute()
            )
            due = res.data or []
            sent = 0

            for followup in due:
                phone   = followup["phone"]
                message = followup["message"]
                fup_id  = followup["id"]

                # Vérifier que le client n'a pas déjà répondu récemment (24h)
                recent = await self._client_responded_recently(phone, hours=24)
                if recent:
                    # Annuler cette relance — client actif
                    self.db._client.table("followups").update({
                        "statut": "cancelled"
                    }).eq("id", fup_id).execute()
                    logger.info(f"⏭️  Relance annulée — {phone} a été actif récemment")
                    continue

                # Envoyer le message
                ok = await self.wa.send(phone, message)
                statut = "sent" if ok else "pending"  # Retry si échec

                self.db._client.table("followups").update({
                    "statut":  statut,
                    "sent_at": datetime.now(timezone.utc).isoformat() if ok else None,
                }).eq("id", fup_id).execute()

                if ok:
                    sent += 1
                    logger.info(f"📬 Relance J+{followup['sequence']} envoyée → {phone}")
                    # Incrémenter le compteur de contacts
                    self.db._client.table("lead_qualification").update({
                        "nb_contacts": self.db._client.table("lead_qualification")
                            .select("nb_contacts").eq("phone", phone).execute()
                            .data[0].get("nb_contacts", 0) + 1
                            if self.db._client.table("lead_qualification").select("nb_contacts").eq("phone", phone).execute().data
                            else 1
                    }).eq("phone", phone).execute()

                await asyncio.sleep(2)  # Pause entre chaque envoi

            return sent
        except Exception as e:
            logger.error(f"❌ process_due_followups : {e}")
            return 0

    async def _client_responded_recently(self, phone: str, hours: int = 24) -> bool:
        """Vérifie si le client a envoyé un message dans les X dernières heures."""
        if not self.db._client:
            return False
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            res = (
                self.db._client.table("conversations")
                .select("id")
                .eq("phone", phone)
                .eq("role", "user")
                .gte("created_at", cutoff)
                .limit(1)
                .execute()
            )
            return bool(res.data)
        except Exception:
            return False

    # ── Extraction des infos de qualification depuis le texte ─────────────────
    @staticmethod
    def extract_qualification_signals(text: str) -> dict:
        """
        Détecte les signaux de qualification dans le message du client.
        Retourne un dict partiel des champs mis à jour.
        """
        text_lower = text.lower()
        updates = {}

        # Rôle
        if any(w in text_lower for w in ["étudiant", "élève", "université", "école", "étude"]):
            updates["role"] = "étudiant"
        elif any(w in text_lower for w in ["directeur", "pdg", "dg ", "dirigeant", "patron", "président"]):
            updates["role"] = "dirigeant"
        elif any(w in text_lower for w in ["entrepreneur", "startup", "ma boîte", "mon entreprise", "fondateur"]):
            updates["role"] = "entrepreneur"
        elif any(w in text_lower for w in ["salarié", "employé", "je travaille", "mon patron", "mon chef"]):
            updates["role"] = "salarié"

        # Service visé
        if any(w in text_lower for w in ["formation", "apprendre", "cours", "former"]):
            updates["service_vise"] = "formation"
        elif any(w in text_lower for w in ["consulting", "conseil", "audit", "analyse"]):
            updates["service_vise"] = "consulting"
        elif any(w in text_lower for w in ["agent", "whatsapp", "chatbot", "automatiser", "bot"]):
            updates["service_vise"] = "agent_ia"

        # Délai d'achat
        if any(w in text_lower for w in ["maintenant", "aujourd'hui", "immédiatement", "de suite", "asap"]):
            updates["delai_achat"] = "immédiat"
        elif any(w in text_lower for w in ["ce mois", "cette semaine", "bientôt", "prochainement"]):
            updates["delai_achat"] = "ce mois"
        elif any(w in text_lower for w in ["réfléchir", "voir", "je vais voir", "pas encore"]):
            updates["delai_achat"] = "pas encore décidé"

        # Taille structure
        if any(w in text_lower for w in ["seul", "individuel", "solo", "freelance"]):
            updates["taille_struct"] = "individuel"
        elif any(w in text_lower for w in ["équipe", "employés", "staff", "collaborateurs"]):
            updates["taille_struct"] = "TPE"
        elif any(w in text_lower for w in ["entreprise", "société", "organisation"]):
            updates["taille_struct"] = "PME"

        return updates
