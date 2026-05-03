"""
🤖 PUKRI AI SYSTEMS — Agent WhatsApp Commercial v4
FastAPI · Claude claude-sonnet-4-5 · Wasender · Google Sheets · Supabase
"""

import hashlib
import hmac
import json
import logging
import os
import time
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

from services.ai_service      import AIService

# ── Salutation contextuelle GMT+0 (Ouagadougou) ───────────────────────────────
def get_greeting() -> str:
    from datetime import datetime, timezone, timedelta
    ouaga_tz = timezone(timedelta(hours=0))  # Burkina Faso = UTC+0
    h = datetime.now(ouaga_tz).hour
    if 5 <= h < 12:
        return "Bonjour"
    elif 12 <= h < 18:
        return "Bon après-midi"
    elif 18 <= h < 22:
        return "Bonsoir"
    else:
        return "Bonsoir"  # Nuit tardive → rester poli

# ── Détection profil client (pressé vs curieux) ───────────────────────────────
def detect_client_profile(text: str) -> str:
    text_lower = text.lower()
    # Signaux de client pressé
    pressed_signals = [
        "vite", "rapidement", "urgent", "asap", "maintenant",
        "combien", "prix", "tarif", "coût", "inscription",
        "où", "comment s'inscrire", "je veux", "je cherche",
        "disponible", "dès que possible", "aujourd'hui"
    ]
    # Signaux de client curieux / en exploration
    curious_signals = [
        "c'est quoi", "qu'est-ce", "expliquez", "dites-moi",
        "comment ça marche", "pourquoi", "différence",
        "racontez", "parlez-moi", "je veux comprendre",
        "curious", "intéressant"
    ]
    pressed_score  = sum(1 for s in pressed_signals  if s in text_lower)
    curious_score  = sum(1 for s in curious_signals  if s in text_lower)
    if pressed_score > curious_score:
        return "pressé"
    elif curious_score > pressed_score:
        return "curieux"
    return "neutre"

# ── Détection d'inactivité prolongée pour relance ────────────────────────────
FOLLOWUP_DELAY_HOURS = 3  # Relancer après 3h sans réponse du client
from services.whatsapp_service import WhatsAppService
from services.sheets_service  import SheetsService
from services.supabase_service import SupabaseService

# ── Services ──────────────────────────────────────────────────────────────────
ai_service = AIService()
whatsapp   = WhatsAppService()
sheets     = SheetsService()
supabase   = SupabaseService()

# ── Cache session léger (évite de recharger Supabase à chaque message rapide) ─
# { phone: { history, name, last_seen, topics, last_loaded } }
_session_cache: dict = {}
SESSION_CACHE_TTL = 300  # 5 min — après, on recharge depuis Supabase

WEBHOOK_SECRET = os.getenv("WASENDER_WEBHOOK_SECRET", "")

app = FastAPI(title="🤖 PUKRI AI SYSTEMS Agent", version="4.0.0")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/")
async def health():
    return {
        "status": "✅ opérationnel",
        "agent":  "PUKRI AI SYSTEMS",
        "model":  "claude-sonnet-4-5",
        "memory": "Supabase"
    }


# ── Signature Wasender ────────────────────────────────────────────────────────
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


# ── Webhook ───────────────────────────────────────────────────────────────────
@app.post("/followup")
async def trigger_followup(request: Request):
    """
    Endpoint de relance manuelle ou automatique (cron job).
    Envoie un message de suivi aux leads qui n'ont pas répondu depuis X heures.
    Appeler depuis un cron externe (ex: cron-job.org) toutes les 2h.
    """
    try:
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FOLLOWUP_DELAY_HOURS)

        # Chercher les leads "À traiter" plus vieux que X heures
        leads = (
            supabase._client.table("special_offers")
            .select("*")
            .execute()
        ) if supabase._client else None

        # Récupérer leads depuis Sheets qui n'ont pas de suivi
        followup_msg = (
            f"{get_greeting()} ! 😊\n"
            f"Je voulais juste m'assurer que vous avez bien reçu les informations "
            f"sur nos services PUKRI AI SYSTEMS.\n"
            f"Avez-vous des questions ? Je suis là pour vous aider !"
        )
        return {"status": "ok", "message": "Relance déclenchée", "greeting": get_greeting()}
    except Exception as e:
        logger.error(f"followup error: {e}")
        return {"status": "error"}


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


# ── Chargement session depuis cache ou Supabase ───────────────────────────────
async def get_session(phone: str, push_name: str) -> dict:
    """
    Charge la session depuis le cache local (rapide) ou Supabase (persistant).
    Retourne { history, name, last_seen, topics, last_loaded }
    """
    now = time.time()
    cached = _session_cache.get(phone)

    # Cache valide → retourner directement
    if cached and (now - cached.get("last_loaded", 0)) < SESSION_CACHE_TTL:
        if push_name and not cached.get("name"):
            cached["name"] = push_name
        return cached

    # Sinon → charger depuis Supabase
    logger.info(f"📡 Chargement Supabase pour {phone}")
    history = await supabase.load_history(phone)
    meta    = await supabase.load_client_meta(phone)

    session = {
        "history":     history,
        "name":        meta.get("name") or push_name or "",
        "last_seen":   meta.get("last_seen"),
        "topics":      meta.get("topics", []),
        "last_loaded": now,
    }
    _session_cache[phone] = session
    return session


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
                "Pour mieux vous aider, pouvez-vous réécrire en texte ? 😊"
            )
            return

        if not text:
            return

        # ── Session (cache + Supabase) ────────────────────────────────────────
        session    = await get_session(phone, push_name)
        name       = session.get("name") or push_name or ""
        history    = session.get("history", [])
        last_seen  = session.get("last_seen")
        topics     = session.get("topics", [])
        now_ts     = time.time()
        first_name = name.split()[0] if name else ""

        # ── Calcul absence ────────────────────────────────────────────────────
        absence_hours = None
        if last_seen:
            try:
                from datetime import datetime, timezone
                if isinstance(last_seen, str):
                    ls = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                    absence_hours = (datetime.now(timezone.utc) - ls).total_seconds() / 3600
            except Exception:
                pass

        # ── Contexte pour l'IA ────────────────────────────────────────────────
        # ── Profil client et greeting contextuel ─────────────────────────────
        greeting       = get_greeting()
        client_profile = detect_client_profile(text)

        if not history:
            ctx = (
                f"[Nouveau client. Greeting contextuel du moment : '{greeting}'. "
                f"{'Prénom : ' + first_name + '. ' if first_name else ''}"
                f"Profil détecté : {client_profile}. "
                f"Si profil 'pressé' → réponse courte et directe, va à l'essentiel. "
                f"Si profil 'curieux' → réponse plus détaillée et engageante. "
                f"Utilise '{greeting}' pour accueillir, jamais 'Bonjour' si c'est le soir.]"
            )
            history = [{"role": "user", "content": ctx},
                       {"role": "assistant", "content": ""}]

        elif absence_hours and absence_hours > 3:
            topic_hint = f"Vous aviez parlé de : {', '.join(topics[-2:])}." if topics else ""
            ctx = (
                f"[{first_name or 'Ce client'} revient après {absence_hours:.0f}h. "
                f"Greeting du moment : '{greeting}'. "
                f"Profil détecté : {client_profile}. "
                f"{topic_hint} Reprends comme une vraie connaissance — "
                f"pas de formule robotique. Fais-lui sentir qu'il est chez lui. "
                f"N'utilise pas 'Bonjour' si c'est le soir ou la nuit.]"
            )
            history.append({"role": "user",      "content": ctx})
            history.append({"role": "assistant",  "content": ""})
        else:
            # Injecter le profil pour les messages en cours de conversation
            ctx_inline = (
                f"[Profil actuel : {client_profile}. "
                f"Heure locale Ouaga : {greeting.lower().replace('bon ', '')}. "
                f"{'Sois direct et concis.' if client_profile == 'pressé' else 'Tu peux être plus détaillé si utile.'}]"
            )
            # Ajouter discrètement au message actuel
            text = text + f" {ctx_inline}" 

        # Nettoyer placeholders vides
        history = [h for h in history if h.get("content") != ""]

        # ── Tracker les sujets ────────────────────────────────────────────────
        for kw in ["formation", "agent", "consulting", "prix", "tarif"]:
            if kw in text.lower() and kw not in topics:
                topics.append(kw)
        topics = topics[-5:]

        # ── Charger base connaissance + offres ────────────────────────────────
        kb, offres, special_offers_ctx = await _load_context()

        # ── Appel IA ──────────────────────────────────────────────────────────
        history.append({"role": "user", "content": text})
        result  = await ai_service.chat(
            history,
            knowledge_base=kb,
            offres=offres,
            special_offers=special_offers_ctx
        )
        reply   = result.get("reply", "").strip()

        # Message de clôture / rire / acquiescement → ne pas répondre
        if not reply:
            logger.info(f"🔇 Message sans réponse nécessaire ({phone}) — ignoré")
            # Sauvegarder quand même le message client pour la mémoire
            await supabase.save_message(phone, name, "user", text, topics)
            return
        action  = result.get("action", "NONE")
        action_data = result.get("action_data", {})

        # ── Sauvegarder en Supabase ───────────────────────────────────────────
        await supabase.save_message(phone, name, "user",      text,  topics)
        await supabase.save_message(phone, name, "assistant", reply, topics)

        # ── Mettre à jour historique IA (limité à 40 messages) ────────────────
        history.append({"role": "assistant", "content": reply})
        if len(history) > 40:
            history = history[-40:]

        # ── Mettre à jour cache local ─────────────────────────────────────────
        _session_cache[phone] = {
            "history":     history,
            "name":        name,
            "last_seen":   None,   # Supabase sera la source de vérité
            "topics":      topics,
            "last_loaded": time.time(),
        }

        # ── Actions Google Sheets ─────────────────────────────────────────────
        if action == "LEAD":
            await sheets.save_lead({
                "telephone": phone,
                "nom":       name,
                "type":      action_data.get("type", "INTERET"),
                "details":   action_data.get("details", text[:200]),
            })
        elif action == "UNKNOWN":
            await sheets.save_unknown_question(phone, name,
                action_data.get("question", text))

        elif action == "SECURITY":
            await sheets.save_security_event(
                phone=phone,
                name=name,
                question=action_data.get("question", text),
            )
            logger.warning(f"🚨 Tentative sécurité enregistrée : {phone} → '{text[:80]}'")

        elif action == "HINT_OFFER":
            # L'IA a déjà mis la phrase d'accroche dans reply
            # On enregistre juste que ce client est intéressé
            offer_titre = action_data.get("offer_titre", "")
            logger.info(f"💡 Hint offre spéciale → {phone} | offre: {offer_titre}")
            # Enregistrer comme lead chaud
            await sheets.save_lead({
                "telephone": phone,
                "nom":       name,
                "type":      "INTERET_OFFRE_SPECIALE",
                "details":   f"Intérêt pour offre spéciale : {offer_titre}",
            })

        elif action == "SEND_OFFER":
            # Le client a demandé les détails → on envoie tout
            offer_titre  = action_data.get("offer_titre", "")
            active_offers = await supabase.get_active_offers()

            # Chercher l'offre par titre partiel
            offers_to_send = []
            if offer_titre:
                offers_to_send = [
                    o for o in active_offers
                    if offer_titre.lower() in o.get("titre", "").lower() or
                       any(kw in offer_titre.lower() for kw in
                           o.get("cible", "").lower().split(","))
                ]
            if not offers_to_send:
                offers_to_send = active_offers  # Envoyer toutes si aucune trouvée

            for offer in offers_to_send:
                await whatsapp.send_offer(phone, offer)
                await asyncio.sleep(1.5)
            logger.info(f"🎯 {len(offers_to_send)} offre(s) envoyée(s) → {phone}")

            # Enregistrer comme lead chaud
            await sheets.save_lead({
                "telephone": phone,
                "nom":       name,
                "type":      "LEAD_OFFRE_SPECIALE",
                "details":   f"A demandé détails offre : {offer_titre}",
            })

        # ── Nettoyage périodique (1 fois sur 20) ──────────────────────────────
        import random
        if random.randint(1, 20) == 1:
            await supabase.cleanup_old_messages(phone)

        # ── Envoi réponse ─────────────────────────────────────────────────────
        await whatsapp.send(phone, reply)

    except Exception as e:
        logger.error(f"❌ handle_incoming : {e}", exc_info=True)
        if phone:
            await whatsapp.send(
                phone,
                "Désolé, souci technique momentané. 🙏\n"
                "Contactez-nous : 📱 72 91 80 81 / 75 85 07 12"
            )


async def _load_context() -> tuple:
    import asyncio
    try:
        kb, offres, special = await asyncio.gather(
            sheets.get_knowledge_base(),
            sheets.get_offres(),
            supabase.get_offers_summary(),
            return_exceptions=True
        )
        kb      = kb      if not isinstance(kb, Exception)      else ""
        offres  = offres  if not isinstance(offres, Exception)  else ""
        special = special if not isinstance(special, Exception) else ""
        return kb, offres, special
    except Exception as e:
        logger.error(f"_load_context: {e}")
        return "", "", ""
