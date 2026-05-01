"""
SheetsService PUKRI v2 — Cache long (10 min) pour éviter quota Google Sheets.
Fallback intégré sur les données essentielles si le Sheet est indisponible.
"""

import asyncio
import logging
import os
import time
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Cache long pour ne pas dépasser le quota Google Sheets (60 req/min gratuit)
CACHE_TTL = 600  # 10 minutes

# ── Données de secours si le Sheet est inaccessible ───────────────────────────
FALLBACK_OFFRES = """• Formation en ligne – Individuel : 29 990 FCFA / séance
• Formation en ligne – Groupe (6-10 pers) : 23 990 FCFA / pers / séance
• Formation sur site – Individuel (Ouaga) : 49 990 FCFA / séance
• Formation sur site – Groupe (6-10 pers) : 49 990 FCFA / pers / séance
• Agent IA – Installation : 499 990 FCFA à 999 990 FCFA (selon complexité)
• Agent IA – Abonnement mensuel : 49 990 FCFA à 299 990 FCFA / mois
• Consulting IA : Sur devis
• Solution IA sur mesure : Sur devis"""

FALLBACK_KB = """Q: C'est quoi PUKRI AI SYSTEMS ?
R: PUKRI AI SYSTEMS est spécialisée dans l'IA pour entreprises africaines. On augmente votre productivité, automatise vos tâches et vous aide à générer plus de revenus. Pas de théorie — des résultats concrets.

Q: C'est quoi l'intelligence artificielle ?
R: L'IA c'est une technologie qui permet à une machine de réfléchir comme un humain pour aider à travailler plus vite et mieux. C'est ce que fait ChatGPT, Siri, ou les recommandations YouTube.

Q: C'est quoi un agent IA ?
R: Un agent IA c'est un assistant qui travaille pour vous automatiquement — répond à vos clients, prend des commandes, gère des tâches sans que vous soyez là. Exactement ce que vous utilisez maintenant !

Q: Pourquoi choisir PUKRI ?
R: On ne fait pas de théorie. On met en place des solutions concrètes adaptées à votre réalité. On comprend les entreprises africaines. On ne vend pas de l'IA, on apporte des résultats.

Q: Comment nous contacter ?
R: Appelez ou écrivez sur WhatsApp : 72 91 80 81 / 75 85 07 12. Email : contact.pukri.ai@gmail.com

Q: Faut-il être expert en informatique ?
R: Non ! Nos formations sont faites pour tout le monde, débutants complets inclus.

Q: Vous êtes où ?
R: Basés à Ouagadougou. Formations sur site à Ouaga, formations en ligne partout en Afrique."""


class SheetsService:
    def __init__(self):
        self.sheet_id   = os.getenv("GOOGLE_SHEET_ID", "")
        self.creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")
        self._client        = None
        self._spreadsheet   = None
        self._kb_cache      = None
        self._kb_ts         = 0.0
        self._offres_cache  = None
        self._offres_ts     = 0.0
        self._sheets_ok     = True
        # Créer le fichier credentials depuis la variable d'env base64 si présent
        self._init_credentials()

    def _init_credentials(self):
        """
        Sur Render, on ne peut pas uploader de fichier.
        On stocke le JSON encodé en base64 dans GOOGLE_CREDENTIALS_B64.
        Cette méthode le décode et crée le fichier à la volée.
        """
        b64 = os.getenv("GOOGLE_CREDENTIALS_B64", "")
        if b64:
            import base64, json, tempfile
            try:
                decoded = base64.b64decode(b64).decode("utf-8")
                # Valider que c'est bien du JSON
                json.loads(decoded)
                # Écrire dans un fichier temporaire
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False
                )
                tmp.write(decoded)
                tmp.close()
                self.creds_file = tmp.name
                logger.info(f"✅ Credentials Google décodés depuis GOOGLE_CREDENTIALS_B64 → {self.creds_file}")
            except Exception as e:
                logger.error(f"❌ Décodage GOOGLE_CREDENTIALS_B64 échoué : {e}")
        elif os.path.exists(self.creds_file):
            logger.info(f"✅ Credentials Google trouvés : {self.creds_file}")
        else:
            logger.error(
                f"❌ Pas de credentials Google ! "
                f"Ajoute GOOGLE_CREDENTIALS_B64 sur Render. "
                f"(base64 de ton google_credentials.json)"
            )

    def _get_client(self):
        if self._client is None:
            creds        = Credentials.from_service_account_file(self.creds_file, scopes=SCOPES)
            self._client = gspread.authorize(creds)
        return self._client

    def _ws(self, name: str):
        if self._spreadsheet is None:
            self._spreadsheet = self._get_client().open_by_key(self.sheet_id)
        return self._spreadsheet.worksheet(name)

    async def get_knowledge_base(self) -> str:
        now = time.time()
        if self._kb_cache is not None and (now - self._kb_ts) < CACHE_TTL:
            return self._kb_cache

        def _fetch():
            ws   = self._ws("Base_Connaissance")
            rows = ws.get_all_records()
            lines = []
            for r in rows:
                q = r.get("question", "").strip()
                a = r.get("reponse", "").strip()
                if q and a:
                    lines.append(f"Q: {q}\nR: {a}")
            return "\n\n".join(lines)

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            self._kb_cache = result or FALLBACK_KB
            self._kb_ts    = now
            self._sheets_ok = True
            logger.info(f"✅ KB chargée depuis Sheets ({len(result)} chars)")
            return self._kb_cache
        except Exception as e:
            logger.warning(f"⚠️ KB Sheet indisponible ({e}) → fallback")
            self._kb_cache = FALLBACK_KB
            self._kb_ts    = now  # Cache le fallback aussi pour éviter spam
            return FALLBACK_KB

    async def get_offres(self) -> str:
        now = time.time()
        if self._offres_cache is not None and (now - self._offres_ts) < CACHE_TTL:
            return self._offres_cache

        def _fetch():
            ws   = self._ws("Offres")
            rows = ws.get_all_records()
            lines = []
            for r in rows:
                if str(r.get("disponible", "TRUE")).upper() == "TRUE":
                    offre = r.get("offre", "")
                    desc  = r.get("description", "")
                    prix  = r.get("prix", "")
                    lines.append(f"• {offre} : {desc} — {prix}")
            return "\n".join(lines)

        try:
            result = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            self._offres_cache = result or FALLBACK_OFFRES
            self._offres_ts    = now
            logger.info(f"✅ Offres chargées depuis Sheets ({len(result)} chars)")
            return self._offres_cache
        except Exception as e:
            logger.warning(f"⚠️ Offres Sheet indisponible ({e}) → fallback")
            self._offres_cache = FALLBACK_OFFRES
            self._offres_ts    = now
            return FALLBACK_OFFRES

    async def save_lead(self, lead: dict) -> bool:
        logger.info(f"📊 Tentative save_lead : {lead}")
        if not self.sheet_id:
            logger.error("❌ save_lead : GOOGLE_SHEET_ID non défini !")
            return False

        def _save():
            ws = self._ws("Leads")
            row = [
                lead.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
                lead.get("telephone", ""),
                lead.get("nom", ""),
                lead.get("type", ""),
                lead.get("details", ""),
                lead.get("statut", "À traiter"),
                "WhatsApp Agent",
            ]
            logger.info(f"📊 Insertion ligne Leads : {row}")
            ws.append_row(row)
        try:
            await asyncio.get_event_loop().run_in_executor(None, _save)
            logger.info(f"✅ Lead enregistré : {lead.get('telephone')} → {lead.get('type')}")
            return True
        except Exception as e:
            logger.error(f"❌ save_lead ERREUR : {type(e).__name__}: {e}", exc_info=True)
            return False

    async def save_unknown_question(self, phone: str, name: str, question: str) -> bool:
        def _save():
            ws = self._ws("Questions_Inconnues")
            ws.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                phone, name, question, "À répondre",
            ])
        try:
            await asyncio.get_event_loop().run_in_executor(None, _save)
            logger.info(f"✅ Question inconnue : '{question[:60]}'")
            return True
        except Exception as e:
            logger.error(f"❌ save_unknown_question : {e}")
            return False
