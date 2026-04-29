"""
🤖 PUKRI AI SYSTEMS — Agent WhatsApp
Backend FastAPI · Claude claude-sonnet-4-5 · Wasender
"""

import hashlib
import hmac
import json
import logging
import os
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

from services.ai_service import AIService
from services.whatsapp_service import WhatsAppService

# ── Services ──────────────────────────────────────────────────────────────────
ai_service = AIService()
whatsapp   = WhatsAppService()

# ── Sessions : { phone: [ {role, content}, ... ] } ────────────────────────────
# On garde l'historique complet par client (max 20 tours)
sessions: dict = {}
MAX_HISTORY = 20

WEBHOOK_SECRET = os.getenv("WASENDER_WEBHOOK_SECRET", "")

app = FastAPI(title="🤖 PUKRI AI SYSTEMS — Agent WhatsApp", version="2.0.0")


# ── Vérification signature Wasender ───────────────────────────────────────────
def verify_signature(headers: dict) -> bool:
    if not WEBHOOK_SECRET:
        return True
    received = (
        headers.get("x-webhook-secret") or
        headers.get("x-webhook-signature") or ""
    ).strip()
    if not received:
        return True
    return hmac.compare_digest(WEBHOOK_SECRET.strip(), received)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
async def health():
    return {
        "status": "✅ opérationnel",
        "agent": "PUKRI AI SYSTEMS",
        "model": "claude-sonnet-4-5"
    }


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        body    = await request.body()
        headers = dict(request.headers)

        if not verify_signature(headers):
            return JSONResponse({"status": "unauthorized"}, status_code=401)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return JSONResponse({"status": "ok"}, status_code=200)

        logger.info(f"📥 event={payload.get('event')} | {str(body[:200])}")
        background_tasks.add_task(handle_incoming, payload)
        return JSONResponse({"status": "ok"}, status_code=200)

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse({"status": "ok"}, status_code=200)


# ── Parseur Wasender ──────────────────────────────────────────────────────────
def parse_payload(payload: dict) -> tuple:
    """Retourne (phone, text, msg_type, push_name)"""
    event = payload.get("event", "")
    if event and event != "messages.received":
        return None, "", "ignored", ""

    data = payload.get("data", {})
    msg  = data.get("messages", {})
    if not msg:
        return None, "", "unknown", ""

    key = msg.get("key", {})
    if key.get("fromMe", False):
        return None, "", "fromMe", ""

    # Phone
    raw = (
        key.get("cleanedSenderPn") or
        key.get("senderPn", "").replace("@s.whatsapp.net", "") or ""
    ).strip()
    phone     = ("+" + raw) if raw and not raw.startswith("+") else raw
    push_name = msg.get("pushName", "")

    # Contenu
    message_obj = msg.get("message", {})
    text     = ""
    msg_type = "text"

    if "conversation" in message_obj:
        text = message_obj["conversation"]
    elif "extendedTextMessage" in message_obj:
        text = message_obj["extendedTextMessage"].get("text", "")
    elif "buttonsResponseMessage" in message_obj:
        text = message_obj["buttonsResponseMessage"].get("selectedDisplayText", "")
    elif "listResponseMessage" in message_obj:
        text = message_obj["listResponseMessage"].get("title", "")
    elif "audioMessage" in message_obj or "pttMessage" in message_obj:
        msg_type = "audio"
    else:
        msg_type = "unknown"

    logger.info(f"✅ phone={phone} | type={msg_type} | text='{text[:60]}' | name={push_name}")
    return phone, text.strip(), msg_type, push_name


# ── Traitement principal ───────────────────────────────────────────────────────
async def handle_incoming(payload: dict):
    phone = None
    try:
        phone, text, msg_type, push_name = parse_payload(payload)

        if msg_type in ("ignored", "fromMe", "unknown") or not phone:
            return

        # Audio : on demande de réécrire en texte (Whisper non configuré ici)
        if msg_type == "audio":
            await whatsapp.send(
                phone,
                "🎤 Je reçois votre message vocal ! Pour mieux vous aider, "
                "pouvez-vous réécrire votre question en texte ? 😊"
            )
            return

        if not text:
            return

        logger.info(f"📱 De: {phone} ({push_name}) → '{text[:80]}'")

        # ── Historique conversation ───────────────────────────────────────────
        history = sessions.get(phone, [])

        # Message de bienvenue si première interaction
        if not history and push_name:
            first_name = push_name.split()[0] if push_name else ""
            greeting_ctx = (
                f"[Le client s'appelle {first_name}. "
                f"C'est son tout premier message. Accueille-le chaleureusement par son prénom.]"
            )
            history.append({"role": "user", "content": greeting_ctx})
            welcome = await ai_service.chat(history)
            history.append({"role": "assistant", "content": welcome})
            await whatsapp.send(phone, welcome)

        # Ajouter le message du client
        history.append({"role": "user", "content": text})

        # Générer la réponse
        reply = await ai_service.chat(history)
        history.append({"role": "assistant", "content": reply})

        # Limiter l'historique (éviter context trop long)
        if len(history) > MAX_HISTORY * 2:
            # Garder les 2 premiers (contexte accueil) + les 10 derniers tours
            history = history[:2] + history[-(MAX_HISTORY * 2 - 2):]

        sessions[phone] = history

        await whatsapp.send(phone, reply)

    except Exception as e:
        logger.error(f"❌ handle_incoming : {e}", exc_info=True)
        if phone:
            await whatsapp.send(
                phone,
                "Je suis momentanément indisponible. 🙏\n"
                "Contactez-nous directement :\n"
                "📱 72 91 80 81 / 75 85 07 12"
            )
