"""
setup_pukri_sheets.py — Configure le Google Sheet PUKRI AI SYSTEMS.
Exécuter UNE SEULE FOIS.

Usage :
  pip install gspread google-auth
  python3 setup_pukri_sheets.py
"""

import sys
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID    = ""   # ← REMPLIS ICI l'ID de ton nouveau Sheet PUKRI
CREDENTIALS = "google_credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── Données initiales ──────────────────────────────────────────────────────────

OFFRES = [
    ["offre", "description", "prix", "disponible"],
    ["Formation en ligne – Individuel",
     "Formation IA pratique, 1 personne, en ligne",
     "29 990 FCFA / séance", "TRUE"],
    ["Formation en ligne – Groupe",
     "Formation IA pratique, 6 à 10 personnes, en ligne",
     "23 990 FCFA / pers / séance", "TRUE"],
    ["Formation sur site – Individuel",
     "Formation IA pratique, 1 personne, à Ouagadougou",
     "49 990 FCFA / séance", "TRUE"],
    ["Formation sur site – Groupe",
     "Formation IA pratique, 6 à 10 personnes, à Ouagadougou",
     "49 990 FCFA / pers / séance", "TRUE"],
    ["Agent IA – Installation",
     "Conception et mise en place d'un agent IA sur mesure (jusqu'à 1 mois selon complexité)",
     "499 990 FCFA à 999 990 FCFA", "TRUE"],
    ["Agent IA – Abonnement mensuel",
     "Maintenance, hébergement et suivi mensuel de l'agent IA",
     "49 990 FCFA à 299 990 FCFA / mois", "TRUE"],
    ["Consulting IA",
     "Analyse de votre activité et recommandations IA personnalisées",
     "Sur devis", "TRUE"],
    ["Solution IA sur mesure",
     "Développement d'outils IA adaptés à votre entreprise",
     "Sur devis", "TRUE"],
]

BASE_CONNAISSANCE = [
    ["question", "reponse", "categorie"],
    ["C'est quoi PUKRI AI SYSTEMS ?",
     "PUKRI AI SYSTEMS est une entreprise spécialisée dans l'intégration de l'intelligence artificielle pour les entreprises africaines. Notre mission : augmenter votre productivité, automatiser vos tâches et vous aider à gagner plus. Nous ne faisons pas de la théorie — nous apportons des résultats concrets.",
     "Présentation"],
    ["C'est quoi l'intelligence artificielle ?",
     "L'intelligence artificielle, c'est une technologie qui permet à une machine de réfléchir un peu comme un humain pour aider à travailler plus vite et mieux. C'est ce que vous utilisez quand vous utilisez ChatGPT, Siri ou les recommandations de YouTube.",
     "Pédagogie"],
    ["C'est quoi un agent IA ?",
     "Un agent IA c'est comme un assistant qui travaille pour vous automatiquement. Par exemple, il peut répondre à vos clients sur WhatsApp, prendre des commandes, répondre aux questions — même quand vous dormez. C'est exactement ce que vous utilisez là !",
     "Pédagogie"],
    ["Pourquoi choisir PUKRI ?",
     "Parce que nous ne faisons pas de la théorie. On met en place des solutions concrètes adaptées à votre activité. On comprend la réalité des entreprises africaines. Et surtout : nous ne vendons pas de l'IA, nous apportons des résultats.",
     "Commercial"],
    ["Vous êtes basés où ?",
     "Nous sommes basés à Ouagadougou, Burkina Faso. Nos formations sur site se font à Ouagadougou, mais nos formations en ligne et nos agents IA peuvent servir partout en Afrique.",
     "Présentation"],
    ["Comment vous contacter ?",
     "Vous pouvez nous appeler ou nous écrire sur WhatsApp : 72 91 80 81 / 75 85 07 12. Ou par email : contact.pukri.ai@gmail.com. On répond rapidement !",
     "Contact"],
    ["Combien de temps dure une formation ?",
     "Chaque séance de formation dure en général entre 2h et 4h selon le programme. Le nombre de séances dépend de votre niveau de départ et de vos objectifs. On s'adapte à vous.",
     "Formation"],
    ["Est-ce qu'il faut être expert en informatique pour vos formations ?",
     "Absolument pas ! Nos formations sont conçues pour tout le monde. Que vous soyez débutant complet ou déjà à l'aise avec les outils numériques, on s'adapte à votre niveau.",
     "Formation"],
    ["Est-ce qu'il y a des offres promotionnelles ?",
     "Oui, nous avons actuellement des tarifs promotionnels sur toutes nos formations ! C'est le bon moment pour se lancer. Voulez-vous que je vous détaille les prix ?",
     "Commercial"],
    ["Quels types d'agents IA vous créez ?",
     "On crée plusieurs types d'agents selon vos besoins : agent réceptionniste WhatsApp, agent commercial (prise de commandes, relance clients), agent service client 24h/24, et des agents sur mesure selon votre activité.",
     "Offres"],
    ["Est-ce qu'un agent IA peut remplacer mon équipe ?",
     "Pas remplacer — renforcer ! L'agent gère les tâches répétitives (répondre aux questions fréquentes, prendre les commandes, qualifier les prospects) pour que votre équipe se concentre sur ce qui a vraiment de la valeur.",
     "Pédagogie"],
    ["Combien de temps pour mettre en place un agent IA ?",
     "En général entre 2 semaines et 1 mois selon la complexité. Un agent simple (répondre aux questions, prendre des commandes) peut être opérationnel en 2 semaines. Un système plus complexe avec plusieurs agents qui travaillent ensemble peut prendre plus de temps.",
     "Offres"],
]

LEADS_HEADERS = [
    ["date", "telephone", "nom", "type", "details", "statut", "source"]
]

QUESTIONS_HEADERS = [
    ["date", "telephone", "nom", "question", "statut"]
]

GREEN  = {"red": 0.18, "green": 0.65, "blue": 0.36}
BLUE   = {"red": 0.13, "green": 0.37, "blue": 0.71}
ORANGE = {"red": 0.93, "green": 0.53, "blue": 0.18}
PURPLE = {"red": 0.42, "green": 0.19, "blue": 0.62}

def style(ws, nb_cols, color):
    ws.format(f"A1:{chr(64+nb_cols)}1", {
        "textFormat": {"bold": True, "fontSize": 11, "foregroundColor": {"red":1,"green":1,"blue":1}},
        "backgroundColor": color,
    })

def setup_sheet(spreadsheet, name, rows_data, color, nb_cols):
    try:
        ws = spreadsheet.worksheet(name)
        ws.clear()
        print(f"  ↩️  '{name}' existant — réinitialisé")
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=500, cols=nb_cols+2)
        print(f"  ✅ '{name}' créé")
    ws.append_rows(rows_data, value_input_option="USER_ENTERED")
    style(ws, nb_cols, color)
    return ws


def main():
    print("\n🤖 Configuration Google Sheet — PUKRI AI SYSTEMS")
    print("=" * 58)

    if not SHEET_ID:
        print("\n❌ SHEET_ID vide ! Ouvre ce script et remplis la variable SHEET_ID.")
        sys.exit(1)

    print("\n🔑 Connexion...")
    try:
        creds        = Credentials.from_service_account_file(CREDENTIALS, scopes=SCOPES)
        client       = gspread.authorize(creds)
        spreadsheet  = client.open_by_key(SHEET_ID)
        print(f"  ✅ Connecté : '{spreadsheet.title}'")
    except FileNotFoundError:
        print(f"\n❌ '{CREDENTIALS}' introuvable ! Place-le dans le même dossier.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Connexion échouée : {e}")
        sys.exit(1)

    print("\n📋 Création des onglets...")
    setup_sheet(spreadsheet, "Offres",              OFFRES,             BLUE,   4)
    print(f"     → {len(OFFRES)-1} offres insérées")

    setup_sheet(spreadsheet, "Base_Connaissance",   BASE_CONNAISSANCE,  GREEN,  3)
    print(f"     → {len(BASE_CONNAISSANCE)-1} entrées KB insérées")

    setup_sheet(spreadsheet, "Leads",               LEADS_HEADERS,      ORANGE, 7)
    print("     → Prêt à recevoir les leads")

    setup_sheet(spreadsheet, "Questions_Inconnues", QUESTIONS_HEADERS,  PURPLE, 5)
    print("     → Prêt à recevoir les questions")

    # Supprimer Feuille 1 par défaut
    for default_name in ["Feuille 1", "Sheet1", "Feuille1"]:
        try:
            spreadsheet.del_worksheet(spreadsheet.worksheet(default_name))
            print(f"\n🗑️  '{default_name}' supprimée")
        except gspread.WorksheetNotFound:
            pass

    print("\n" + "=" * 58)
    print("✅ Google Sheet PUKRI configuré !")
    print(f"🔗 https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
    print("\n📝 Variables d'env à ajouter sur Render :")
    print(f"   GOOGLE_SHEET_ID={SHEET_ID}")
    print("   GOOGLE_CREDENTIALS_FILE=google_credentials.json")
    print("   ANTHROPIC_API_KEY=sk-ant-...")
    print("   WASENDER_API_KEY=552f7e62...")
    print("=" * 58)


if __name__ == "__main__":
    main()
