"""
WhatsAppService — Envoi via Wasender API officielle.
URL : https://www.wasenderapi.com/api/send-message
Payload : { "to": "+226...", "text": "..." }
"""

import asyncio
import logging
import os
import httpx

logger = logging.getLogger(__name__)

WASENDER_URL      = "https://www.wasenderapi.com/api/send-message"
MAX_MSG_LENGTH    = 4096


class WhatsAppService:
    def __init__(self):
        self.api_key = os.getenv("WASENDER_API_KEY", "")
        if not self.api_key:
            logger.warning("⚠️ WASENDER_API_KEY non définie !")

    async def send(self, phone: str, message: str) -> bool:
        if not phone or not message:
            return False
        message = message.strip()
        if len(message) > MAX_MSG_LENGTH:
            return await self._send_chunks(phone, message)
        return await self._post(phone, message)

    async def _post(self, phone: str, message: str) -> bool:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"to": phone, "text": message}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(WASENDER_URL, json=payload, headers=headers)

            if resp.status_code in (200, 201):
                logger.info(f"✅ Message envoyé → {phone}")
                return True

            logger.error(f"❌ Wasender {resp.status_code} : {resp.text[:200]}")
            return False

        except httpx.TimeoutException:
            logger.error(f"⏱️ Timeout → {phone}")
            return False
        except Exception as e:
            logger.error(f"❌ send error : {e}")
            return False

    async def _send_chunks(self, phone: str, message: str) -> bool:
        chunks = [message[i:i+MAX_MSG_LENGTH] for i in range(0, len(message), MAX_MSG_LENGTH)]
        ok_all = True
        for i, chunk in enumerate(chunks):
            if not await self._post(phone, chunk):
                ok_all = False
            if i < len(chunks) - 1:
                await asyncio.sleep(1.5)
        return ok_all
