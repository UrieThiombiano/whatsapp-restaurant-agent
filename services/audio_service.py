"""
AudioService — Télécharge et transcrit les messages vocaux WhatsApp.
Utilise OpenAI Whisper-1 (multilingue, supporte le français et les langues locales).
"""

import logging
import os
import tempfile

import httpx

logger = logging.getLogger(__name__)


class AudioService:
    def __init__(self):
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.enabled    = bool(self.openai_key)
        self.language   = os.getenv("WHISPER_LANGUAGE", "fr")  # ou "sw", "ha", etc.

        if not self.enabled:
            logger.warning(
                "⚠️ OPENAI_API_KEY non définie — transcription audio désactivée. "
                "Ajoutez-la dans .env pour activer les messages vocaux."
            )

    async def transcribe(self, audio_url: str) -> str:
        """
        Télécharge l'audio depuis audio_url et le transcrit avec Whisper.
        Retourne le texte transcrit ou "" en cas d'échec.
        """
        if not self.enabled:
            logger.warning("Transcription désactivée (pas de clé OpenAI)")
            return ""

        if not audio_url:
            return ""

        try:
            # ── Téléchargement ─────────────────────────────────────────────────
            logger.info(f"🎤 Téléchargement audio : {audio_url[:80]}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(audio_url)

            if resp.status_code != 200:
                logger.error(f"❌ Téléchargement audio échoué : HTTP {resp.status_code}")
                return ""

            audio_bytes = resp.content

            # ── Transcription Whisper ──────────────────────────────────────────
            # On importe openai ici pour rester synchrone dans le bloc with
            import openai
            openai.api_key = self.openai_key

            suffix = self._detect_suffix(audio_url)
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                with open(tmp_path, "rb") as f:
                    result = openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        language=self.language,
                    )
                text = result.text.strip()
                logger.info(f"🎤 Transcription : \"{text[:100]}\"")
                return text
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        except Exception as e:
            logger.error(f"❌ AudioService.transcribe : {e}", exc_info=True)
            return ""

    @staticmethod
    def _detect_suffix(url: str) -> str:
        """Déduit l'extension du fichier audio depuis l'URL."""
        url_lower = url.lower().split("?")[0]
        for ext in (".ogg", ".mp3", ".mp4", ".wav", ".m4a", ".webm", ".aac"):
            if url_lower.endswith(ext):
                return ext
        return ".ogg"  # Format par défaut WhatsApp
