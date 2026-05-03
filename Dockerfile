# ─────────────────────────────────────────────────────────────────
#  🤖 PUKRI AI SYSTEMS — Dockerfile optimisé
#  Build : docker build -t pukri-agent .
#  Run   : docker run -p 8000:8000 --env-file .env pukri-agent
# ─────────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Dépendances Python (couche cachée)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# 2 workers Uvicorn pour traitement parallèle
# --loop uvloop pour performance maximale async
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--timeout-keep-alive", "30"]
