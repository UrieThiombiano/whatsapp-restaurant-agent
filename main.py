"""
🤖 PUKRI AI SYSTEMS — Agent WhatsApp Commercial
FastAPI · Claude claude-sonnet-4-5 · Wasender · Google Sheets
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
from services.sheets_service import SheetsService

# ── Services ──────────────────────────────────────────────────────────────────
ai_service = AIService()
whatsapp   = WhatsAppService()
sheets     = SheetsService()

# ── Sessions : { phone: { history: [], name: str } } ─────────────────────────
sessions: dict   = {}
MAX_HISTORY      = 16   # 8 tours de conversation conservés
WEBHOOK_SECRET   = os.getenv("WASENDER_WEBHOOK_SECRET", "")

app = FastAPI(title="🤖 PUKRI AI SYSTEMS Agent", version="2.0.0")


# ── Signature ─────────────────────────────────────────────────────────────────
def verify_sig(headers: dict) -> bool:
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
        if not verify_sig(headers):
            return JSONResponse({"status": "unauthorized"}, status_code=401)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return JSONResponse({"status": "ok"}, status_code=200)
        background_tasks.add_task(handle_incoming, payload)
        return JSONResponse({"status": "ok"}, status_code=200)
    except Exception as e:
        logger.error(f"Webhook: {e}", exc_info=True)
        return JSONResponse({"status": "ok"}, status_code=200)


# ── Parseur Wasender ──────────────────────────────────────────────────────────
def parse_payload(payload: dict) -> tuple:
    """Retourne (phone, text, msg_type, push_name)"""
    if payload.get("event", "") not in ("messages.received", ""):
        return None, "", "ignored", ""

    data = payload.get("data", {})
    msg  = data.get("messages", {})
    if not msg:
        return None, "", "unknown", ""

    key = msg.get("key", {})
    if key.get("fromMe", False):
        return None, "", "fromMe", ""

    raw = (
        key.get("cleanedSenderPn") or
        key.get("senderPn", "").replace("@s.whatsapp.net", "") or ""
    ).strip()
    phone     = ("+" + raw) if raw and not raw.startswith("+") else raw
    push_name = msg.get("pushName", "")

    message_obj = msg.get("message", {})
    text, msg_type = "", "text"

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

    return phone, text.strip(), msg_type, push_name


# ── Traitement principal ───────────────────────────────────────────────────────
async def handle_incoming(payload: dict):
    phone = None
    try:
        phone, text, msg_type, push_name = parse_payload(payload)

        if msg_type in ("ignored", "fromMe", "unknown") or not phone:
            return

        logger.info(f"📱 {phone} ({push_name}) → '{text[:80]}' [{msg_type}]")

        # Audio → demander de réécrire
        if msg_type == "audio":
            await whatsapp.send(
                phone,
                "🎤 Message vocal reçu !\n"
                "Pour mieux vous aider, pouvez-vous réécrire votre question en texte ? 😊"
            )
            return

        if not text:
            return

        # ── Session ───────────────────────────────────────────────────────────
        session   = sessions.get(phone, {"history": [], "name": push_name or ""})
        if push_name and not session.get("name"):
            session["name"] = push_name
        name      = session.get("name", "")
        history   = session["history"]

        # ── Message de bienvenue (1ère interaction) ────────────────────────────
        if not history:
            first_name = name.split()[0] if name else ""
            ctx = (
                f"[Contexte : nouveau client. "
                f"{'Prénom : ' + first_name + '. ' if first_name else ''}"
                f"Accueille-le chaleureusement et demande comment tu peux l'aider.]"
            )
            history.append({"role": "user", "content": ctx})
            # On va générer le welcome avec le vrai message du client aussi
            history.append({"role": "assistant", "content": ""})  # placeholder

        # ── Charger base connaissance + offres (parallèle) ────────────────────
        kb, offres = await _load_context()

        # ── Ajouter message client ─────────────────────────────────────────────
        history.append({"role": "user", "content": text})

        # Nettoyer le placeholder vide si présent
        history = [h for h in history if h.get("content") != ""]

        # ── Appel IA ──────────────────────────────────────────────────────────
        result    = await ai_service.chat(history, knowledge_base=kb, offres=offres)
        reply     = result.get("reply", "")
        action    = result.get("action", "NONE")
        action_data = result.get("action_data", {})

        if not reply:
            reply = AIService._fallback_text()

        # ── Ajouter réponse à l'historique ────────────────────────────────────
        history.append({"role": "assistant", "content": reply})

        # Tronquer si trop long (garder les derniers MAX_HISTORY messages)
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]

        session["history"] = history
        sessions[phone]    = session

        # ── Actions Google Sheets ──────────────────────────────────────────────
        if action == "LEAD":
            await sheets.save_lead({
                "telephone": phone,
                "nom":       name,
                "type":      action_data.get("type", "INTERET"),
                "details":   action_data.get("details", text[:200]),
                "statut":    "À traiter",
            })
            logger.info(f"📊 Lead enregistré : {phone} → {action_data.get('type')}")

        elif action == "UNKNOWN":
            await sheets.save_unknown_question(
                phone=phone,
                name=name,
                question=action_data.get("question", text),
            )
            logger.info(f"❓ Question inconnue enregistrée : '{action_data.get('question', text)[:60]}'")

        # ── Envoi réponse ─────────────────────────────────────────────────────
        await whatsapp.send(phone, reply)

    except Exception as e:
        logger.error(f"❌ handle_incoming : {e}", exc_info=True)
        if phone:
            await whatsapp.send(
                phone,
                "Désolé, je rencontre un souci technique. 🙏\n"
                "Contactez-nous directement :\n"
                "📱 72 91 80 81 / 75 85 07 12"
            )


async def _load_context() -> tuple:
    """Charge KB + offres en parallèle depuis Google Sheets."""
    import asyncio
    try:
        kb, offres = await asyncio.gather(
            sheets.get_knowledge_base(),
            sheets.get_offres(),
            return_exceptions=True
        )
        if isinstance(kb, Exception):
            logger.error(f"KB error: {kb}")
            kb = ""
        if isinstance(offres, Exception):
            logger.error(f"Offres error: {offres}")
            offres = ""
        return kb, offres
    except Exception as e:
        logger.error(f"_load_context: {e}")
        return "", ""
