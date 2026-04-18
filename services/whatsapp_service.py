"""
WhatsAppService — Envoie des messages via l'API Wasender.
Gère le découpage des messages longs et la gestion d'erreurs.
"""

import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

# URLs Wasender à essayer dans l'ordre (fallback automatique)
WASENDER_URLS = [
    "https://wasender.app/api/send-message",
    "https://app.wasender.net/api/send-message",
    "https://api.wasender.app/api/send-message",
]

MAX_MESSAGE_LENGTH = 4096


class WhatsAppService:
    def __init__(self):
        self.api_key  = os.getenv("WASENDER_API_KEY", "")
        # URL custom via .env, sinon on auto-détecte
        custom_url    = os.getenv("WASENDER_API_URL", "")
        self.base_url = custom_url if custom_url else None  # None = auto-detect

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
        payload = {"phone": phone, "message": message}

        # Construire la liste d'URLs à essayer
        if self.base_url:
            urls = [self.base_url] + [u for u in WASENDER_URLS if u != self.base_url]
        else:
            urls = WASENDER_URLS

        for url in urls:
            try:
                async with httpx.AsyncClient(timeout=15.0, verify=True) as client:
                    resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code in (200, 201):
                    logger.info(f"✅ Message envoyé → {phone} | URL: {url}")
                    self.base_url = url  # Mémoriser l'URL qui fonctionne
                    return True

                logger.warning(
                    f"⚠️ {url} → HTTP {resp.status_code} : {resp.text[:200]}"
                )
                # 401 = mauvaise clé → inutile d'essayer d'autres URLs
                if resp.status_code == 401:
                    logger.error("❌ Clé API Wasender invalide (401) !")
                    return False

            except httpx.ConnectError as e:
                logger.warning(f"🔌 Connexion échouée ({url}): {e}")
            except httpx.TimeoutException:
                logger.warning(f"⏱️ Timeout ({url})")
            except Exception as e:
                logger.warning(f"❌ Erreur ({url}): {e}")

        logger.error(f"❌ Toutes les URLs Wasender ont échoué pour {phone}")
        return False

    async def _send_chunks(self, phone: str, message: str) -> bool:
        chunks  = [message[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(message), MAX_MESSAGE_LENGTH)]
        all_ok  = True
        for i, chunk in enumerate(chunks):
            ok = await self._post(phone, chunk)
            if not ok:
                all_ok = False
            if i < len(chunks) - 1:
                await asyncio.sleep(1.2)
        return all_ok
