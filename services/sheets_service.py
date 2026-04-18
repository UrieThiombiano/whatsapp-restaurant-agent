"""
SheetsService — Connexion Google Sheets avec cache 5 minutes.
Lit Menu, Config et écrit les commandes confirmées.
"""

import asyncio
import logging
import os
import time

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

CACHE_TTL = 300  # 5 minutes


class SheetsService:
    def __init__(self):
        self.sheet_id   = os.getenv("GOOGLE_SHEET_ID", "")
        self.creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")
        self._client       = None
        self._spreadsheet  = None
        self._menu_cache   = None
        self._config_cache = None
        self._menu_ts      = 0.0
        self._config_ts    = 0.0

    # ── Connexion ──────────────────────────────────────────────────────────────
    def _get_client(self) -> gspread.Client:
        if self._client is None:
            creds = Credentials.from_service_account_file(self.creds_file, scopes=SCOPES)
            self._client = gspread.authorize(creds)
        return self._client

    def _worksheet(self, name: str) -> gspread.Worksheet:
        if self._spreadsheet is None:
            self._spreadsheet = self._get_client().open_by_key(self.sheet_id)
        return self._spreadsheet.worksheet(name)

    # ── Menu ───────────────────────────────────────────────────────────────────
    async def get_menu(self) -> list[dict]:
        """
        Retourne tous les articles du menu (onglet 'Menu').
        Cache 5 minutes pour éviter de surcharger l'API Sheets.
        """
        now = time.time()
        if self._menu_cache and (now - self._menu_ts) < CACHE_TTL:
            return self._menu_cache

        def _fetch():
            ws = self._worksheet("Menu")
            return ws.get_all_records()

        try:
            records = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            self._menu_cache = records
            self._menu_ts    = now
            logger.info(f"✅ Menu rechargé : {len(records)} articles")
            return records
        except Exception as e:
            logger.error(f"❌ get_menu : {e}")
            return self._menu_cache or []

    # ── Config ─────────────────────────────────────────────────────────────────
    async def get_config(self) -> dict:
        """
        Retourne la config resto (onglet 'Config') sous forme {cle: valeur}.
        Cache 5 minutes.
        """
        now = time.time()
        if self._config_cache and (now - self._config_ts) < CACHE_TTL:
            return self._config_cache

        def _fetch():
            ws = self._worksheet("Config")
            rows = ws.get_all_records()
            return {r["cle"]: r["valeur"] for r in rows if r.get("cle")}

        try:
            cfg = await asyncio.get_event_loop().run_in_executor(None, _fetch)
            self._config_cache = cfg
            self._config_ts    = now
            logger.info(f"✅ Config rechargée : {list(cfg.keys())}")
            return cfg
        except Exception as e:
            logger.error(f"❌ get_config : {e}")
            return self._config_cache or {
                "restaurant_nom": "Notre Restaurant",
                "devise": "FCFA",
                "horaires": "08h00 – 22h00",
                "delai_livraison": "30–45 min",
            }

    # ── Sauvegarde commande ────────────────────────────────────────────────────
    async def save_order(self, order: dict) -> bool:
        """
        Ajoute une ligne dans l'onglet 'Commandes'.
        Colonnes : id_commande | telephone | nom_client | articles_json
                   total | statut | horodatage | notes
        """
        def _save():
            ws = self._worksheet("Commandes")
            ws.append_row([
                order.get("id_commande", ""),
                order.get("telephone", ""),
                order.get("nom_client", ""),
                order.get("articles_json", ""),
                order.get("total", 0),
                order.get("statut", "En attente"),
                order.get("horodatage", ""),
                order.get("notes", ""),
            ])

        try:
            await asyncio.get_event_loop().run_in_executor(None, _save)
            logger.info(f"✅ Commande sauvegardée : {order.get('id_commande')}")
            return True
        except Exception as e:
            logger.error(f"❌ save_order : {e}")
            return False

    # ── Mise à jour statut commande ────────────────────────────────────────────
    async def update_order_status(self, order_id: str, statut: str) -> bool:
        """Cherche la commande par id et met à jour la colonne 'statut'."""
        def _update():
            ws = self._worksheet("Commandes")
            cell = ws.find(order_id)
            if cell:
                # Colonne statut = 6
                ws.update_cell(cell.row, 6, statut)
                return True
            return False

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _update)
        except Exception as e:
            logger.error(f"❌ update_order_status : {e}")
            return False

    def invalidate_cache(self):
        """Force le rechargement au prochain appel."""
        self._menu_cache   = None
        self._config_cache = None
        self._menu_ts      = 0.0
        self._config_ts    = 0.0
