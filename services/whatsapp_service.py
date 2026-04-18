"""
WhatsAppService — Envoie des messages via l'API Wasender.
Gère le découpage des messages longs et la gestion d'erreurs.
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

# URL Wasender (configurable via .env)
DEFAULT_WASENDER_URL = "https://api.wasenderapp.com/api/send-message"

MAX_MESSAGE_LENGTH = 4096  # Limite WhatsApp


class WhatsAppService:
    def __init__(self):
        self.api_key  = os.getenv("WASENDER_API_KEY", "")
        self.base_url = os.getenv("WASENDER_API_URL", DEFAULT_WASENDER_URL)

        if not self.api_key:
            logger.warning("⚠️ WASENDER_API_KEY non définie !")

    async def send(self, phone: str, message: str) -> bool:
        """
        Envoie un message texte WhatsApp.
        Découpe automatiquement si > 4096 caractères.
        """
        if not phone or not message:
            return False

        message = message.strip()

        # Messages longs → découpage
        if len(message) > MAX_MESSAGE_LENGTH:
            return await self._send_chunks(phone, message)

        return await self._post(phone, message)

    async def _post(self, phone: str, message: str) -> bool:
        """Appel API Wasender."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "phone": phone,
            "message": message,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self.base_url, json=payload, headers=headers)

            if resp.status_code == 200:
                logger.info(f"✅ Message envoyé → {phone}")
                return True

            # Gestion erreurs HTTP Wasender
            logger.error(
                f"❌ Wasender HTTP {resp.status_code} → {phone} | "
                f"Response: {resp.text[:200]}"
            )
            return False

        except httpx.TimeoutException:
            logger.error(f"⏱️ Timeout Wasender → {phone}")
            return False
        except httpx.ConnectError as e:
            logger.error(f"🔌 Connexion Wasender échouée : {e}")
            return False
        except Exception as e:
            logger.error(f"❌ WhatsAppService._post : {e}", exc_info=True)
            return False

    async def _send_chunks(self, phone: str, message: str) -> bool:
        """Découpe un message long et envoie par parties."""
        chunks = [
            message[i : i + MAX_MESSAGE_LENGTH]
            for i in range(0, len(message), MAX_MESSAGE_LENGTH)
        ]
        all_ok = True
        for i, chunk in enumerate(chunks):
            ok = await self._post(phone, chunk)
            if not ok:
                all_ok = False
            if i < len(chunks) - 1:
                await asyncio.sleep(1.2)  # Anti-spam WhatsApp
        return all_ok
