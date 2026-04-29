"""
SheetsService PUKRI — Google Sheet comme cerveau vivant de l'agent.

4 onglets :
  Base_Connaissance → FAQ dynamique que l'agent consulte à chaque message
  Leads             → RDV + commandes + prospects intéressés
  Questions_Inconnues → Ce que l'agent ne savait pas répondre (à traiter)
  Offres            → Détail des offres et prix (modifiable sans toucher au code)
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
CACHE_TTL = 180  # 3 minutes pour la base de connaissance


class SheetsService:
    def __init__(self):
        self.sheet_id   = os.getenv("GOOGLE_SHEET_ID", "")
        self.creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")
        self._client       = None
        self._spreadsheet  = None
        self._kb_cache     = None
        self._kb_ts        = 0.0
        self._offres_cache = None
        self._offres_ts    = 0.0

    # ── Connexion ──────────────────────────────────────────────────────────────
    def _get_client(self):
        if self._client is None:
            creds        = Credentials.from_service_account_file(self.creds_file, scopes=SCOPES)
            self._client = gspread.authorize(creds)
        return self._client

    def _ws(self, name: str) -> gspread.Worksheet:
        if self._spreadsheet is None:
            self._spreadsheet = self._get_client().open_by_key(self.sheet_id)
        return self._spreadsheet.worksheet(name)

    # ── Base de connaissance ────────────────────────────────────────────────────
    async def get_knowledge_base(self) -> str:
        """
        Retourne la base de connaissance formatée pour injection dans le prompt.
        Colonnes : question | reponse | categorie
        Cache 3 min.
        """
        now = time.time()
        if self._kb_cache and (now - self._kb_ts) < CACHE_TTL:
            return self._kb_cache

        def _fetch():
            ws  = self._ws("Base_Connaissance")
            return ws.get_all_records()

        try:
            rows   = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            lines  = []
            for r in rows:
                q = r.get("question", "").strip()
                a = r.get("reponse", "").strip()
                if q and a:
                    lines.append(f"Q: {q}\nR: {a}")
            result = "\n\n".join(lines)
            self._kb_cache = result
            self._kb_ts    = now
            logger.info(f"✅ Base connaissance : {len(rows)} entrées")
            return result
        except Exception as e:
            logger.error(f"❌ get_knowledge_base : {e}")
            return self._kb_cache or ""

    # ── Offres ─────────────────────────────────────────────────────────────────
    async def get_offres(self) -> str:
        """
        Retourne le détail des offres depuis l'onglet Offres.
        Colonnes : offre | description | prix | disponible
        Cache 3 min.
        """
        now = time.time()
        if self._offres_cache and (now - self._offres_ts) < CACHE_TTL:
            return self._offres_cache

        def _fetch():
            ws = self._ws("Offres")
            return ws.get_all_records()

        try:
            rows  = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            lines = []
            for r in rows:
                if str(r.get("disponible", "TRUE")).upper() == "TRUE":
                    offre = r.get("offre", "")
                    desc  = r.get("description", "")
                    prix  = r.get("prix", "")
                    lines.append(f"• {offre} : {desc} — {prix}")
            result = "\n".join(lines)
            self._offres_cache = result
            self._offres_ts    = now
            logger.info(f"✅ Offres rechargées : {len(rows)} entrées")
            return result
        except Exception as e:
            logger.error(f"❌ get_offres : {e}")
            return self._offres_cache or ""

    # ── Enregistrer un lead ─────────────────────────────────────────────────────
    async def save_lead(self, lead: dict) -> bool:
        """
        Ajoute une ligne dans l'onglet Leads.
        Colonnes : date | telephone | nom | type | details | statut | source
        """
        def _save():
            ws = self._ws("Leads")
            ws.append_row([
                lead.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
                lead.get("telephone", ""),
                lead.get("nom", ""),
                lead.get("type", ""),      # RDV / COMMANDE / INTERET
                lead.get("details", ""),
                lead.get("statut", "À traiter"),
                "WhatsApp Agent",
            ])

        try:
            await asyncio.get_event_loop().run_in_executor(None, _save)
            logger.info(f"✅ Lead sauvegardé : {lead.get('type')} — {lead.get('telephone')}")
            return True
        except Exception as e:
            logger.error(f"❌ save_lead : {e}")
            return False

    # ── Enregistrer une question inconnue ──────────────────────────────────────
    async def save_unknown_question(self, phone: str, name: str, question: str) -> bool:
        """
        Ajoute dans l'onglet Questions_Inconnues pour traitement humain.
        Colonnes : date | telephone | nom | question | statut
        """
        def _save():
            ws = self._ws("Questions_Inconnues")
            ws.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                phone,
                name,
                question,
                "À répondre",
            ])

        try:
            await asyncio.get_event_loop().run_in_executor(None, _save)
            logger.info(f"✅ Question inconnue enregistrée : '{question[:60]}'")
            return True
        except Exception as e:
            logger.error(f"❌ save_unknown_question : {e}")
            return False

    def invalidate_cache(self):
        self._kb_cache     = None
        self._offres_cache = None
        self._kb_ts        = 0.0
        self._offres_ts    = 0.0
