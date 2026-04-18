# ─────────────────────────────────────────────────────────────────
#  🍽️ Restaurant WhatsApp Agent — Dockerfile
#  Build : docker build -t whatsapp-agent .
#  Run   : docker run -p 8000:8000 --env-file .env whatsapp-agent
# ─────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# Métadonnées
LABEL maintainer="restaurant-whatsapp-agent"
LABEL description="Agent WhatsApp restaurant — FastAPI + Claude + Wasender"

# Répertoire de travail
WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python (couche cachée)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY . .

# Port exposé
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Démarrage
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
