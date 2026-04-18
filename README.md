# 🍽️ Restaurant WhatsApp Agent

Agent conversationnel WhatsApp pour restaurant / food delivery.
Construit avec **FastAPI + Claude AI + Google Sheets + Wasender**.

---

## 🏗️ Architecture

```
Client WhatsApp
      │  (texte ou vocal)
      ▼
 ┌─────────────┐
 │   Wasender  │  ← API WhatsApp
 └──────┬──────┘
        │ webhook POST /webhook
        ▼
 ┌──────────────────────────────────────────────┐
 │              FastAPI  (main.py)              │
 │                                              │
 │  parse_wasender_payload()                    │
 │       │                                      │
 │       ├─ Audio ? ──► AudioService (Whisper)  │
 │       │                                      │
 │       ▼                                      │
 │  AIService.analyze()  ◄── Google Sheets      │
 │  (Claude Sonnet)           (menu + config)   │
 │       │                                      │
 │       ▼  intent routing                      │
 │  ┌──────────┬──────────┬───────────┐         │
 │  │  ORDER   │ CONFIRM  │MENU/INFO  │         │
 │  └────┬─────┴────┬─────┴─────┬─────┘         │
 │       │          │           │               │
 │  OrderManager  Finalize    Direct reply      │
 │  (fuzzy match) (Sheets)                      │
 └──────────────────────────────────────────────┘
        │
        ▼
 WhatsAppService.send()
        │
        ▼
 ┌─────────────┐
 │   Wasender  │ → Client WhatsApp
 └─────────────┘
```

---

## 📊 Structure Google Sheets

Créez un Google Spreadsheet avec **4 onglets** exactement nommés ainsi :

### Onglet 1 : `Menu`

| id | nom | categorie | description | prix | disponible | emoji | temps_preparation |
|----|-----|-----------|-------------|------|------------|-------|-------------------|
| 1 | Thiéboudienne | Plats | Riz au poisson façon dakaroise | 3500 | TRUE | 🍚 | 35 |
| 2 | Yassa Poulet | Plats | Poulet mariné citron-oignon | 3000 | TRUE | 🍗 | 30 |
| 3 | Fonio Légumes | Plats | Fonio aux légumes du jardin | 2500 | TRUE | 🌿 | 25 |
| 4 | Jus de Bissap | Boissons | Jus d'hibiscus frais | 500 | TRUE | 🍹 | 5 |
| 5 | Jus de Gingembre | Boissons | Gingembre citron miel | 500 | TRUE | 🫚 | 5 |
| 6 | Eau 1.5L | Boissons | Eau minérale fraîche | 300 | TRUE | 💧 | 1 |
| 7 | Salade César | Entrées | Laitue, croûtons, parmesan | 1500 | TRUE | 🥗 | 10 |
| 8 | Plateau Mixte | Spéciaux | Assortiment du chef | 5000 | FALSE | 🍱 | 45 |

> **Règles** :
> - `disponible` : `TRUE` ou `FALSE` (en MAJUSCULES)
> - `prix` : nombre entier sans symbole (ex: `3500`)
> - `id` : unique, entier croissant

---

### Onglet 2 : `Config`

| cle | valeur |
|-----|--------|
| restaurant_nom | Chez Aminata |
| devise | FCFA |
| horaires | Lun–Sam 10h00–22h00, Dim 11h00–20h00 |
| adresse | Avenue Kwamé N'Krumah, Ouagadougou |
| telephone_contact | +226 70 00 00 00 |
| delai_livraison | 30–45 min |
| message_accueil | Bienvenue chez Chez Aminata ! Comment puis-je vous aider ? |
| frais_livraison | 500 |
| commande_minimum | 2000 |

---

### Onglet 3 : `Commandes` (rempli automatiquement)

| id_commande | telephone | nom_client | articles_json | total | statut | horodatage | notes |
|-------------|-----------|------------|---------------|-------|--------|------------|-------|
| CMD-20240601-A1B2 | +22670000000 | Moussa | [...] | 6500 | En attente | 2024-06-01 14:30:00 | |

---

## ⚙️ Installation

### 1. Cloner & installer

```bash
git clone <votre-repo>
cd whatsapp-restaurant-agent

python -m venv venv
source venv/bin/activate      # Linux/Mac
# venv\Scripts\activate       # Windows

pip install -r requirements.txt
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditez .env avec vos vraies clés
```

### 3. Configurer Google Sheets API

**a) Créer un Service Account Google :**
1. Allez sur [console.cloud.google.com](https://console.cloud.google.com)
2. Créez un projet → Activez l'API **Google Sheets** et **Google Drive**
3. IAM & Admin → Comptes de service → Créer un compte
4. Téléchargez la clé JSON → renommez en `google_credentials.json`
5. Placez `google_credentials.json` à la racine du projet

**b) Partager le Spreadsheet :**
- Ouvrez votre Google Sheet
- Partagez avec l'email du service account (format: `xxx@projet.iam.gserviceaccount.com`)
- Permission : **Éditeur**

### 4. Lancer le serveur

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Le serveur est accessible sur `http://localhost:8000`

---

## 🌐 Déploiement en production

### Option A : Railway (recommandé, gratuit au départ)

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

Ajoutez les variables d'env dans le dashboard Railway.
**Important** : uploadez `google_credentials.json` comme variable d'env encodée en base64 :

```bash
base64 google_credentials.json | tr -d '\n'
```

Puis dans Railway, créez `GOOGLE_CREDENTIALS_B64` avec la valeur, et adaptez `sheets_service.py` :

```python
import base64, json, tempfile
b64 = os.getenv("GOOGLE_CREDENTIALS_B64")
if b64:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json.dump(json.loads(base64.b64decode(b64)), f)
        self.creds_file = f.name
```

### Option B : Render

1. Connectez votre repo GitHub à [render.com](https://render.com)
2. New → Web Service → Python
3. Build command : `pip install -r requirements.txt`
4. Start command : `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Ajoutez les variables d'env

### Option C : VPS (Ubuntu)

```bash
# Installer
pip install -r requirements.txt

# Service systemd
cat > /etc/systemd/system/whatsapp-agent.service << 'EOF'
[Unit]
Description=Restaurant WhatsApp Agent
After=network.target

[Service]
WorkingDirectory=/home/ubuntu/whatsapp-restaurant-agent
ExecStart=/home/ubuntu/whatsapp-restaurant-agent/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
EnvironmentFile=/home/ubuntu/whatsapp-restaurant-agent/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl enable whatsapp-agent
systemctl start whatsapp-agent
```

### Configuration Wasender Webhook

Dans votre dashboard Wasender :
- **Webhook URL** : `https://votre-domaine.com/webhook`
- **Méthode** : POST
- **Events** : `message.received` (ou équivalent)

---

## 📡 Exemples de payloads Wasender

### Message texte entrant (webhook reçu)

```json
{
  "event": "message",
  "data": {
    "from": "22670123456@c.us",
    "type": "chat",
    "body": "Bonjour, je voudrais 2 Yassa Poulet et 1 Jus de Bissap",
    "timestamp": 1717242600,
    "pushName": "Moussa"
  }
}
```

### Message vocal entrant

```json
{
  "event": "message",
  "data": {
    "from": "22670123456@c.us",
    "type": "ptt",
    "audio": {
      "url": "https://mmg.whatsapp.net/d/xxx.ogg",
      "mimetype": "audio/ogg; codecs=opus"
    },
    "timestamp": 1717242700
  }
}
```

### Envoi d'un message (via Wasender)

```bash
curl -X POST https://api.wasenderapp.com/api/send-message \
  -H "Authorization: Bearer VOTRE_CLE_WASENDER" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+22670123456",
    "message": "🎉 Commande confirmée ! Réf: CMD-20240601-A1B2"
  }'
```

---

## 💬 Exemples de conversations

### Scénario 1 : Commande simple

```
Client  → "Bonjour !"
Agent   → "👋 Bonjour ! Bienvenue chez Chez Aminata 🍽️
           Tapez *menu* pour voir la carte ou dites-moi
           directement ce que vous souhaitez commander !"

Client  → "Je voudrais 2 yassa poulet et 1 bissap"
Agent   → "📋 Récapitulatif de votre commande :
           🍗 2x Yassa Poulet — 6000 FCFA
           🍹 1x Jus de Bissap — 500 FCFA

           💰 Total : 6500 FCFA
           ✅ Confirmez avec OUI | ❌ Annulez avec NON"

Client  → "oui"
Agent   → "🎉 Commande confirmée !
           📋 Référence : CMD-20240601-A1B2
           💰 Total : 6500 FCFA
           ⏱️ Délai estimé : 30–45 min
           Merci Moussa ! Votre commande est en préparation 🍽️"
```

### Scénario 2 : Consultation menu

```
Client  → "C'est quoi le menu ?"
Agent   → "🍽️ Menu — Chez Aminata
           ━━ Plats ━━
           🍚 *Thiéboudienne* — 3500 FCFA
              _Riz au poisson façon dakaroise_
           🍗 *Yassa Poulet* — 3000 FCFA
              _Poulet mariné citron-oignon_
           ...
           📝 Pour commander, dites-moi ce que vous souhaitez !"
```

### Scénario 3 : Article non disponible

```
Client  → "Un plateau mixte stp"
Agent   → "📋 Récapitulatif :
           ⚠️ Non disponible / non trouvé : _plateau mixte_

           Votre panier est vide. Tapez *menu* pour voir
           ce qui est disponible !"
```

---

## 🔧 Personnalisation

### Ajouter un nouvel intent

Dans `services/ai_service.py`, ajoutez l'intent dans `SYSTEM_PROMPT` et gérez-le dans `main.py` :

```python
elif intent == "DELIVERY_ADDRESS":
    response_text = f"📍 Nous livrons dans un rayon de 10km autour de {config.get('adresse')} !"
    sessions[phone] = session
```

### Changer la langue de l'IA

Dans `.env` :
```
WHISPER_LANGUAGE=fr   # fr, en, sw, ha, ar...
```

Dans `ai_service.py`, le prompt peut être adapté en mooré, dioula, etc.

### Activer le rechargement du menu en temps réel

```python
# Dans sheets_service.py, réduire le TTL du cache :
CACHE_TTL = 60  # 1 minute au lieu de 5
```

---

## 🧪 Test local

```bash
# Simuler un webhook entrant
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "from": "22670000000@c.us",
      "type": "chat",
      "body": "Bonjour, montrez-moi le menu"
    }
  }'

# Health check
curl http://localhost:8000/
```

---

## 📁 Structure du projet

```
whatsapp-restaurant-agent/
├── main.py                    # FastAPI app, webhook, routage
├── services/
│   ├── __init__.py
│   ├── sheets_service.py      # Google Sheets (lecture menu, écriture commandes)
│   ├── ai_service.py          # Claude — intent, entities, réponse
│   ├── whatsapp_service.py    # Wasender — envoi messages
│   ├── audio_service.py       # OpenAI Whisper — transcription vocale
│   └── order_manager.py       # Logique panier + commandes
├── google_credentials.json    # ⚠️ NE PAS COMMITER — à ajouter dans .gitignore
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

---

## ⚠️ Sécurité

```gitignore
# .gitignore — OBLIGATOIRE
.env
google_credentials.json
__pycache__/
*.pyc
venv/
```

---

## 🆘 Dépannage fréquent

| Problème | Solution |
|----------|----------|
| `gspread.exceptions.SpreadsheetNotFound` | Vérifiez `GOOGLE_SHEET_ID` + partage avec le service account |
| `anthropic.AuthenticationError` | Vérifiez `ANTHROPIC_API_KEY` |
| Wasender 401 | Vérifiez `WASENDER_API_KEY` et l'URL dans `.env` |
| Menu vide | Vérifiez que l'onglet s'appelle exactement `Menu` (M majuscule) |
| Audio non transcrit | Ajoutez `OPENAI_API_KEY` dans `.env` |
| Sessions perdues au redémarrage | Normal (in-memory). Pour persistance → ajouter Redis |
