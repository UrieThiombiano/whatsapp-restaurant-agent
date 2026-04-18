"""
🍽️ Restaurant WhatsApp Agent — Point d'entrée FastAPI
Gère les webhooks Wasender, le routage des messages et les sessions clients.
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

from services.sheets_service import SheetsService
from services.ai_service import AIService
from services.whatsapp_service import WhatsAppService
from services.audio_service import AudioService
from services.order_manager import OrderManager

# ── Services ──────────────────────────────────────────────────────────────────
sheets_service = SheetsService()
ai_service     = AIService()
whatsapp       = WhatsAppService()
audio_service  = AudioService()
order_manager  = OrderManager(sheets_service)

# ── Sessions en mémoire : { phone: { state, cart, name } } ───────────────────
sessions: dict = {}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="🍽️ Restaurant WhatsApp Agent", version="1.0.0")

WEBHOOK_SECRET = os.getenv("WASENDER_WEBHOOK_SECRET", "")


# ── Vérification signature Wasender ───────────────────────────────────────────
def verify_wasender_signature(headers: dict) -> bool:
    """
    Wasender envoie le secret brut dans x-webhook-secret (pas un HMAC).
    On compare directement. Si pas de secret configuré → on accepte tout.
    """
    if not WEBHOOK_SECRET:
        return True

    received = (
        headers.get("x-webhook-secret") or
        headers.get("x-webhook-signature") or
        ""
    ).strip()

    if not received:
        logger.warning("⚠️ Aucun secret Wasender dans les headers — accepté quand même")
        return True

    return hmac.compare_digest(WEBHOOK_SECRET.strip(), received)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
async def health_check():
    return {"status": "✅ opérationnel", "service": "Restaurant WhatsApp Agent"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint appelé par Wasender pour chaque nouveau message.
    Répond 200 immédiatement, traite en arrière-plan.
    """
    try:
        body    = await request.body()
        headers = dict(request.headers)

        # Vérification signature
        if not verify_wasender_signature(headers):
            logger.error("❌ Signature invalide — requête rejetée")
            return JSONResponse({"status": "unauthorized"}, status_code=401)

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error(f"❌ Body non-JSON: {body[:200]}")
            return JSONResponse({"status": "ok"}, status_code=200)

        logger.info(f"📥 Webhook reçu | event={payload.get('event')} | body={str(body[:300])}")
        background_tasks.add_task(handle_incoming, payload)
        return JSONResponse({"status": "ok"}, status_code=200)

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return JSONResponse({"status": "ok"}, status_code=200)


@app.post("/webhook/debug")
async def webhook_debug(request: Request):
    """Debug — affiche le payload brut. Désactiver en production."""
    body    = await request.body()
    headers = dict(request.headers)
    try:
        payload = json.loads(body)
    except Exception:
        payload = body.decode(errors="replace")
    return JSONResponse({"headers": headers, "payload": payload})


# ── Parseur Wasender (format réel observé dans les logs) ──────────────────────
def parse_wasender_payload(payload: dict) -> tuple:
    """
    Extrait (phone, text, msg_type, media_url, push_name) depuis le webhook Wasender.

    Format réel Wasender :
    {
      "event": "messages.received",
      "sessionId": "...",
      "data": {
        "messages": {
          "key": {
            "fromMe": false,
            "remoteJid": "xxx@lid",
            "senderPn": "22675850712@s.whatsapp.net",
            "cleanedSenderPn": "22675850712"
          },
          "pushName": "Urie THIOMBIANO",
          "message": {
            "conversation": "Coucou",
            "audioMessage": {...},
            "extendedTextMessage": {"text": "..."},
            "imageMessage": {...}
          }
        }
      }
    }
    """
    phone = media_url = None
    text = ""
    msg_type = "text"
    push_name = ""

    # ── Ignorer les événements non-message ────────────────────────────────────
    event = payload.get("event", "")
    if event and event != "messages.received":
        logger.info(f"⏭️  Événement ignoré : {event}")
        return None, "", "ignored", None, ""

    # ── Extraction du bloc messages ───────────────────────────────────────────
    data = payload.get("data", {})
    msg  = data.get("messages", {})

    if not msg:
        logger.warning("⚠️ Pas de bloc 'messages' dans data")
        return None, "", "unknown", None, ""

    key = msg.get("key", {})

    # ── Ignorer les messages envoyés par le bot lui-même ──────────────────────
    if key.get("fromMe", False):
        logger.info("⏭️  Message fromMe ignoré")
        return None, "", "fromMe", None, ""

    # ── Phone ─────────────────────────────────────────────────────────────────
    raw_phone = (
        key.get("cleanedSenderPn") or
        key.get("senderPn", "").replace("@s.whatsapp.net", "") or
        key.get("remoteJid", "").replace("@c.us", "").replace("@lid", "") or
        ""
    ).strip()

    if raw_phone:
        phone = "+" + raw_phone if not raw_phone.startswith("+") else raw_phone

    push_name = msg.get("pushName", "")

    # ── Contenu du message ────────────────────────────────────────────────────
    message_obj = msg.get("message", {})

    # Texte simple (conversation)
    if "conversation" in message_obj:
        text     = message_obj["conversation"]
        msg_type = "text"

    # Texte étendu
    elif "extendedTextMessage" in message_obj:
        text     = message_obj["extendedTextMessage"].get("text", "")
        msg_type = "text"

    # Audio / vocal
    elif "audioMessage" in message_obj or "pttMessage" in message_obj:
        audio    = message_obj.get("audioMessage") or message_obj.get("pttMessage", {})
        media_url = audio.get("url") or audio.get("directPath")
        msg_type  = "audio"

    # Image avec légende
    elif "imageMessage" in message_obj:
        text     = message_obj["imageMessage"].get("caption", "")
        msg_type = "image"

    # Bouton / liste (réponse rapide)
    elif "buttonsResponseMessage" in message_obj:
        text     = message_obj["buttonsResponseMessage"].get("selectedDisplayText", "")
        msg_type = "text"
    elif "listResponseMessage" in message_obj:
        text     = message_obj["listResponseMessage"].get("title", "")
        msg_type = "text"

    else:
        # Type inconnu → log pour debug
        logger.warning(f"⚠️ Type de message inconnu : {list(message_obj.keys())}")
        msg_type = "unknown"

    logger.info(f"✅ Parsé — phone={phone} | type={msg_type} | text='{text[:60]}' | name={push_name}")
    return phone, text.strip(), msg_type, media_url, push_name


# ── Traitement principal ───────────────────────────────────────────────────────
async def handle_incoming(payload: dict):
    phone = None
    try:
        phone, text, msg_type, media_url, push_name = parse_wasender_payload(payload)

        # Ignorer les événements non pertinents
        if msg_type in ("ignored", "fromMe", "unknown") or not phone:
            return

        logger.info(f"📱 De: {phone} ({push_name}) | Type: {msg_type} | Texte: '{text[:60]}'")

        # ── Transcription audio ───────────────────────────────────────────────
        if msg_type == "audio" and media_url:
            text = await audio_service.transcribe(media_url)
            if not text:
                await whatsapp.send(phone, "🎤 Je n'ai pas pu transcrire votre vocal. Réessayez en texte !")
                return

        if not text or not text.strip():
            await whatsapp.send(phone, "🤔 Message vide reçu. Envoyez du texte ou un vocal !")
            return

        # ── Session client ────────────────────────────────────────────────────
        session = sessions.get(phone, {
            "state": "idle",
            "cart": [],
            "name": push_name or None,
            "pending_order": None
        })
        # Mettre à jour le nom si on le récupère maintenant
        if push_name and not session.get("name"):
            session["name"] = push_name

        # ── Données Google Sheets ─────────────────────────────────────────────
        menu   = await sheets_service.get_menu()
        config = await sheets_service.get_config()

        # ── Analyse IA ────────────────────────────────────────────────────────
        result   = await ai_service.analyze(text=text, session=session, menu=menu, config=config)
        intent   = result.get("intent", "FALLBACK")
        entities = result.get("entities", {})
        ai_reply = result.get("reply", "")

        logger.info(f"🤖 Intent={intent} | Entities={entities}")

        # ── Routage selon intent ──────────────────────────────────────────────
        if intent == "ORDER" and entities.get("items"):
            res = await order_manager.process_order_request(
                phone, session, entities["items"], menu, config
            )
            response_text    = res["message"]
            sessions[phone]  = res["session"]

        elif intent == "CONFIRM" and session.get("state") == "awaiting_confirmation":
            res = await order_manager.finalize_order(phone, session, config)
            response_text    = res["message"]
            sessions[phone]  = res["session"]

        elif intent == "CANCEL":
            sessions[phone] = {
                "state": "idle",
                "cart": [],
                "name": session.get("name"),
                "pending_order": None
            }
            response_text = "❌ Commande annulée. Je suis là si vous avez besoin ! 😊"

        elif intent == "MENU":
            response_text   = format_menu(menu, config)
            sessions[phone] = session

        elif intent == "CART":
            response_text   = format_cart(session, config)
            sessions[phone] = session

        else:
            # GREET, INFO, HOURS, FALLBACK → réponse IA directe
            response_text   = ai_reply
            sessions[phone] = session

        await whatsapp.send(phone, response_text)

    except Exception as e:
        logger.error(f"❌ handle_incoming error: {e}", exc_info=True)
        if phone:
            await whatsapp.send(
                phone,
                "⚠️ Une erreur s'est produite. Réessayez dans un instant ou appelez-nous. 🙏"
            )


# ── Formateurs de messages ─────────────────────────────────────────────────────
def format_menu(menu: list, config: dict) -> str:
    if not menu:
        return "😔 Menu indisponible pour l'instant. Appelez-nous directement !"

    devise    = config.get("devise", "FCFA")
    nom_resto = config.get("restaurant_nom", "Notre Restaurant")

    categories: dict = {}
    for item in menu:
        if str(item.get("disponible", "TRUE")).upper() == "TRUE":
            cat = item.get("categorie", "Autres")
            categories.setdefault(cat, []).append(item)

    lines = [f"🍽️ *Menu — {nom_resto}*\n"]
    for cat, items in categories.items():
        lines.append(f"━━ *{cat}* ━━")
        for item in items:
            emoji = item.get("emoji", "•")
            nom   = item.get("nom", "")
            prix  = item.get("prix", "")
            desc  = item.get("description", "")
            lines.append(f"{emoji} *{nom}* — {prix} {devise}")
            if desc:
                lines.append(f"   _{desc}_")
        lines.append("")

    lines.append("📝 Pour commander, dites-moi simplement ce que vous souhaitez !")
    return "\n".join(lines)


def format_cart(session: dict, config: dict) -> str:
    cart   = session.get("cart", [])
    devise = config.get("devise", "FCFA")

    if not cart:
        return "🛒 Votre panier est vide. Demandez le *menu* pour commencer ! 😊"

    lines = ["🛒 *Votre panier :*\n"]
    total = 0
    for item in cart:
        qty        = item.get("quantite", 1)
        nom        = item.get("nom", "")
        prix       = item.get("prix", 0)
        sous_total = qty * prix
        total     += sous_total
        lines.append(f"• {qty}x {nom} — {sous_total:.0f} {devise}")

    lines.append(f"\n💰 *Total : {total:.0f} {devise}*")
    if session.get("state") == "awaiting_confirmation":
        lines.append("\nConfirmez avec *OUI* ✅ ou annulez avec *NON* ❌")

    return "\n".join(lines)
