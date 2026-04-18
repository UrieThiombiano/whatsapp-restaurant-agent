"""
WhatsAppService — Envoie des messages via l'API Wasender (wasenderapi.com).
URL officielle : https://www.wasenderapi.com/api/send-message
Payload : { "to": "+22675850712", "text": "message" }
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

WASENDER_API_URL = "https://www.wasenderapi.com/api/send-message"
MAX_MESSAGE_LENGTH = 4096


class WhatsAppService:
    def __init__(self):
        self.api_key = os.getenv("WASENDER_API_KEY", "")
        if not self.api_key:
            logger.warning("⚠️ WASENDER_API_KEY non définie !")

    async def send(self, phone: str, message: str) -> bool:
        if not phone or not message:
            return False
        message = message.strip()
        if len(message) > MAX_MESSAGE_LENGTH:
            return await self._send_chunks(phone, message)
        return await self._post(phone, message)

    async def _post(self, phone: str, message: str) -> bool:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # ✅ Payload officiel Wasender : "to" + "text"
        payload = {
            "to": phone,
            "text": message,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, verify=True) as client:
                resp = await client.post(WASENDER_API_URL, json=payload, headers=headers)

            if resp.status_code in (200, 201):
                logger.info(f"✅ Message envoyé → {phone}")
                return True

            logger.error(
                f"❌ Wasender HTTP {resp.status_code} → {phone} | "
                f"Body: {resp.text[:300]}"
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
        chunks = [message[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(message), MAX_MESSAGE_LENGTH)]
        all_ok = True
        for i, chunk in enumerate(chunks):
            ok = await self._post(phone, chunk)
            if not ok:
                all_ok = False
            if i < len(chunks) - 1:
                await asyncio.sleep(1.2)
        return all_ok
