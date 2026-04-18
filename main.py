"""
🍽️ Restaurant WhatsApp Agent — Point d'entrée FastAPI
Gère les webhooks Wasender, le routage des messages et les sessions clients.
"""

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

# ── Sessions en mémoire : { phone: { state, cart, name, pending_order } } ─────
sessions: dict = {}

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="🍽️ Restaurant WhatsApp Agent", version="1.0.0")


@app.get("/")
async def health_check():
    return {"status": "✅ opérationnel", "service": "Restaurant WhatsApp Agent"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint appelé par Wasender pour chaque nouveau message.
    On répond 200 immédiatement, on traite en arrière-plan.
    """
    try:
        payload = await request.json()
        logger.info(f"📥 Webhook reçu: {str(payload)[:200]}")
        background_tasks.add_task(handle_incoming, payload)
        return JSONResponse({"status": "ok"}, status_code=200)
    except Exception as e:
        logger.error(f"Webhook parse error: {e}")
        return JSONResponse({"status": "ok"}, status_code=200)  # Toujours 200


# ── Traitement principal ───────────────────────────────────────────────────────
async def handle_incoming(payload: dict):
    phone = None
    try:
        phone, text, msg_type, media_url = parse_wasender_payload(payload)

        if not phone:
            logger.warning("Aucun numéro trouvé dans le payload")
            return

        logger.info(f"📱 De: {phone} | Type: {msg_type} | Texte: {str(text)[:60]}")

        # ── Transcription audio ───────────────────────────────────────────────
        if msg_type in ("audio", "voice", "ptt") and media_url:
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
            "name": None,
            "pending_order": None
        })

        # ── Données Google Sheets ─────────────────────────────────────────────
        menu   = await sheets_service.get_menu()
        config = await sheets_service.get_config()

        # ── Analyse IA ────────────────────────────────────────────────────────
        result  = await ai_service.analyze(text=text, session=session, menu=menu, config=config)
        intent  = result.get("intent", "FALLBACK")
        entities = result.get("entities", {})
        ai_reply = result.get("reply", "")

        logger.info(f"🤖 Intent: {intent} | Entities: {entities}")

        # ── Routage selon intent ──────────────────────────────────────────────
        if intent == "ORDER" and entities.get("items"):
            res = await order_manager.process_order_request(
                phone, session, entities["items"], menu, config
            )
            response_text = res["message"]
            sessions[phone] = res["session"]

        elif intent == "CONFIRM" and session.get("state") == "awaiting_confirmation":
            res = await order_manager.finalize_order(phone, session, config)
            response_text = res["message"]
            sessions[phone] = res["session"]

        elif intent == "CANCEL":
            sessions[phone] = {
                "state": "idle",
                "cart": [],
                "name": session.get("name"),
                "pending_order": None
            }
            response_text = "❌ Commande annulée. Je suis là si vous avez besoin ! 😊"

        elif intent == "MENU":
            response_text = format_menu(menu, config)
            sessions[phone] = session

        elif intent == "CART":
            response_text = format_cart(session, config)
            sessions[phone] = session

        else:
            # GREET, INFO, HOURS, FALLBACK → réponse IA directe
            response_text = ai_reply
            sessions[phone] = session

        await whatsapp.send(phone, response_text)

    except Exception as e:
        logger.error(f"❌ handle_incoming error: {e}", exc_info=True)
        if phone:
            await whatsapp.send(
                phone,
                "⚠️ Une erreur s'est produite. Réessayez dans un instant ou appelez-nous directement. 🙏"
            )


# ── Parseur Wasender (multi-format) ───────────────────────────────────────────
def parse_wasender_payload(payload: dict) -> tuple:
    """
    Extrait (phone, text, msg_type, media_url) depuis le webhook Wasender.
    Gère les deux formats courants (enveloppe `data` ou plat).
    """
    phone = media_url = None
    text = ""
    msg_type = "text"

    data = payload.get("data", payload)

    # Phone
    raw_phone = (
        data.get("from") or data.get("phone") or data.get("sender") or
        payload.get("from") or payload.get("phone") or ""
    )
    if raw_phone:
        phone = (
            raw_phone
            .replace("@c.us", "")
            .replace("@s.whatsapp.net", "")
            .strip()
        )
        if phone and not phone.startswith("+"):
            phone = "+" + phone

    # Type
    msg_type = str(
        data.get("type") or data.get("messageType") or payload.get("type", "text")
    ).lower()

    # Contenu texte
    if msg_type in ("text", "chat", "extendedtextmessage", "conversation"):
        body = (
            data.get("body") or data.get("text") or
            data.get("message") or payload.get("body") or ""
        )
        if isinstance(body, dict):
            text = body.get("body", "") or body.get("text", "")
        else:
            text = str(body)

    # Contenu audio
    elif msg_type in ("audio", "voice", "ptt"):
        media = data.get("audio") or data.get("media") or {}
        if isinstance(media, dict):
            media_url = media.get("url") or media.get("link")
        media_url = media_url or data.get("mediaUrl") or data.get("url")

    return phone, text.strip(), msg_type, media_url


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
        qty       = item.get("quantite", 1)
        nom       = item.get("nom", "")
        prix      = item.get("prix", 0)
        sous_total = qty * prix
        total     += sous_total
        lines.append(f"• {qty}x {nom} — {sous_total:.0f} {devise}")

    lines.append(f"\n💰 *Total : {total:.0f} {devise}*")
    if session.get("state") == "awaiting_confirmation":
        lines.append("\nConfirmez avec *OUI* ✅ ou annulez avec *NON* ❌")

    return "\n".join(lines)
