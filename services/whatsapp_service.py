"""
WhatsAppService — Envoi via Wasender.
Supporte : texte, image+légende, image seule.
"""

import asyncio
import logging
import os
import httpx

logger = logging.getLogger(__name__)

WASENDER_URL   = "https://www.wasenderapi.com/api/send-message"
MAX_MSG_LENGTH = 4096


class WhatsAppService:
    def __init__(self):
        self.api_key = os.getenv("WASENDER_API_KEY", "")
        if not self.api_key:
            logger.warning("⚠️ WASENDER_API_KEY non définie !")

    # ── Texte simple ───────────────────────────────────────────────────────────
    async def send(self, phone: str, message: str) -> bool:
        if not phone or not message:
            return False
        message = message.strip()
        if len(message) > MAX_MSG_LENGTH:
            return await self._send_chunks(phone, message)
        return await self._post(phone, {"to": phone, "text": message})

    # ── Image avec légende optionnelle ─────────────────────────────────────────
    async def send_image(self, phone: str, image_url: str, caption: str = "") -> bool:
        """
        Envoie une image WhatsApp avec légende optionnelle.
        image_url doit être une URL publique HTTPS.
        """
        if not phone or not image_url:
            return False
        payload = {"to": phone, "imageUrl": image_url}
        if caption:
            payload["text"] = caption[:1024]  # Limite WhatsApp sur les légendes
        return await self._post(phone, payload)

    # ── Offre spéciale : image + message séparé ────────────────────────────────
    async def send_offer(self, phone: str, offer: dict) -> bool:
        """
        Envoie une offre spéciale complète (plan payant Wasender — pas de limite) :
        1. Le flyer (image)
        2. La description complète
        3. Le lien d'inscription
        Tous les éléments sont TOUJOURS envoyés même si image_url est vide.
        """
        ok = True

        # 1. Flyer — toujours tenter si image_url présente
        image_url = offer.get("image_url", "").strip()
        if image_url:
            img_ok = await self.send_image(phone, image_url)
            logger.info(f"🖼️ Flyer {'envoyé ✅' if img_ok else 'échec ❌'} → {phone}")
            await asyncio.sleep(0.8)
        else:
            logger.warning(f"⚠️ Pas d'image_url pour l'offre '{offer.get('titre','?')}' — vérifier Supabase")

        # 2. Description complète — OBLIGATOIRE
        description = offer.get("description", "").strip()
        if description:
            ok = await self._post(phone, {"to": phone, "text": description})
            logger.info(f"📝 Description {'envoyée ✅' if ok else 'échec ❌'} → {phone}")
            await asyncio.sleep(0.8)

        # 3. Lien inscription — si disponible
        lien = offer.get("lien_inscription", "").strip()
        if lien:
            msg = f"👉 *Inscrivez-vous ici :*\n{lien}\n\n⚠️ Places limitées — ne tardez pas !"
            ok = await self._post(phone, {"to": phone, "text": msg})
            logger.info(f"🔗 Lien {'envoyé ✅' if ok else 'échec ❌'} → {phone}")

        return ok

    # ── Internals ──────────────────────────────────────────────────────────────
    async def _post(self, phone: str, payload: dict) -> bool:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(WASENDER_URL, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                logger.info(f"✅ Envoyé → {phone} | type={list(payload.keys())}")
                return True
            logger.error(f"❌ Wasender {resp.status_code} : {resp.text[:200]}")
            return False
        except httpx.TimeoutException:
            logger.error(f"⏱️ Timeout → {phone}")
            return False
        except Exception as e:
            logger.error(f"❌ _post error : {e}")
            return False

    async def _send_chunks(self, phone: str, message: str) -> bool:
        chunks = [message[i:i+MAX_MSG_LENGTH] for i in range(0, len(message), MAX_MSG_LENGTH)]
        ok_all = True
        for i, chunk in enumerate(chunks):
            if not await self._post(phone, {"to": phone, "text": chunk}):
                ok_all = False
            if i < len(chunks) - 1:
                await asyncio.sleep(1.5)
        return ok_all
