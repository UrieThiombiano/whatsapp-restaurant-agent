"""
🚀 activate_pukri.py — Script d'activation TOUT-EN-UN
Exécute sur ta machine Windows :
  python activate_pukri.py

Ce script :
  1. Crée la table special_offers dans Supabase
  2. Crée le bucket Storage pukri-media
  3. Upload le flyer de formation
  4. Met à jour la DB avec l'URL de l'image
  5. Vérifie que tout fonctionne
"""

import os, sys, time

SUPABASE_URL = "https://bchzfrtiocizylqiwloh.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJjaHpmcnRpb2NpenlscWl3bG9oIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NzY0Mjk3OSwiZXhwIjoyMDkzMjE4OTc5fQ.H1S_Urh2tMCDYxYNoumILP8FAdUdUHhQNYxg1R28XP4"
BUCKET       = "pukri-media"

# Nom du fichier image du flyer de formation (dans le même dossier que ce script)
FLYER_FORMATION = "flyer_formation_mai.jpg"
FLYER_CONSULTING = "flyer_consulting.jpg"  # optionnel

print("\n🚀 PUKRI AI SYSTEMS — Activation complète")
print("=" * 55)

# ── Vérifier les dépendances ───────────────────────────────────
try:
    from supabase import create_client
except ImportError:
    print("📦 Installation de supabase...")
    os.system(f"{sys.executable} -m pip install supabase -q")
    from supabase import create_client

client = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✅ Connexion Supabase OK")

# ── ÉTAPE 1 : Créer la table special_offers ───────────────────
print("\n📋 Étape 1 — Création table special_offers...")
try:
    res = client.table("special_offers").select("id").limit(1).execute()
    print(f"   Table déjà existante ({len(res.data)} lignes)")
except Exception:
    print("   ⚠️  Table manquante — va dans Supabase → SQL Editor et exécute :")
    print("   create_special_offers_table.sql")

# ── ÉTAPE 2 : Insérer les offres ──────────────────────────────
print("\n📊 Étape 2 — Insertion des offres spéciales...")

offres = [
    {
        "titre": "Formation IA Pratique — Mai 2026",
        "description": """🚨 Étudiants, chercheurs d'emploi, candidats aux concours… cette formation peut changer votre avenir !

Aujourd'hui, beaucoup ratent des opportunités non pas par manque de talent, mais parce qu'ils ne maîtrisent pas encore l'Intelligence Artificielle.

Avec l'IA, vous pouvez :
✅ Étudier plus efficacement
✅ Préparer vos concours intelligemment
✅ Créer un CV professionnel
✅ Rédiger lettres, dossiers et présentations plus vite
✅ Trouver de meilleures opportunités
✅ Développer des compétences recherchées

🎓 PUKRI AI SYSTEMS lance une formation pratique en IA
📅 En ligne : 14 Mai (depuis partout)
📍 En présentiel à Ouagadougou : 15 Mai
💰 Coût : 19 990 FCFA — tarif promotionnel 🔥
⚠️ Places limitées pour une meilleure prise en charge — inscription obligatoire

🚀 Prenez de l'avance sur les autres dès maintenant !""",
        "lien_inscription": "https://docs.google.com/forms/d/e/1FAIpQLSfkNBq-XEzNItQI_egrZ9bkOkSefrz8ergHKGEdkq9-G_KpIw/viewform?usp=publish-editor",
        "cible": "étudiants, chercheurs emploi, concours",
        "prix": "19 990 FCFA",
        "date_debut": "2026-05-14",
        "date_fin": "2026-05-15",
        "actif": True,
        "ordre": 1,
        "image_url": ""
    },
    {
        "titre": "Consulting IA — Offre Spéciale Entreprises",
        "description": """💼 Votre entreprise est-elle prête pour l'IA ?

PUKRI AI SYSTEMS vous propose un accompagnement personnalisé :
✅ Audit de votre activité
✅ Identification des opportunités IA dans votre secteur
✅ Plan d'action concret et réalisable
✅ Recommandations adaptées à votre réalité terrain

🎯 Résultat : Gain de temps, réduction des coûts, plus de performance

📞 Contactez-nous :
WhatsApp : 72 91 80 81 / 75 85 07 12
📧 contact.pukri.ai@gmail.com

🚀 Les entreprises qui intègrent l'IA aujourd'hui domineront leur marché demain !""",
        "lien_inscription": "",
        "cible": "entreprises, dirigeants, managers",
        "prix": "Sur devis",
        "date_debut": None,
        "date_fin": None,
        "actif": True,
        "ordre": 2,
        "image_url": ""
    }
]

for offre in offres:
    try:
        # Vérifier si existe déjà
        existing = client.table("special_offers").select("id").eq("titre", offre["titre"]).execute()
        if existing.data:
            print(f"   ↩️  '{offre['titre'][:40]}' déjà présente")
        else:
            client.table("special_offers").insert(offre).execute()
            print(f"   ✅ '{offre['titre'][:40]}' insérée")
    except Exception as e:
        print(f"   ❌ Erreur insertion : {e}")

# ── ÉTAPE 3 : Créer le bucket Storage ────────────────────────
print("\n🗂️  Étape 3 — Bucket Storage pukri-media...")
try:
    buckets = client.storage.list_buckets()
    bucket_names = [b.name for b in buckets]
    if BUCKET in bucket_names:
        print(f"   ↩️  Bucket '{BUCKET}' déjà existant")
    else:
        client.storage.create_bucket(BUCKET, options={"public": True})
        print(f"   ✅ Bucket '{BUCKET}' créé (public)")
except Exception as e:
    print(f"   ⚠️  Bucket : {e}")

# ── ÉTAPE 4 : Upload flyer formation ─────────────────────────
print("\n🖼️  Étape 4 — Upload flyer formation...")

def upload_and_update(local_file: str, storage_name: str, offer_title_partial: str):
    if not os.path.exists(local_file):
        print(f"   ⚠️  Fichier '{local_file}' non trouvé dans ce dossier")
        print(f"   → Renomme ton flyer en '{local_file}' et place-le ici")
        return None

    with open(local_file, "rb") as f:
        data = f.read()

    ext      = local_file.split(".")[-1].lower()
    mimetype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")

    try:
        # Supprimer si existe
        client.storage.from_(BUCKET).remove([storage_name])
    except Exception:
        pass

    try:
        client.storage.from_(BUCKET).upload(
            path=storage_name,
            file=data,
            file_options={"content-type": mimetype, "upsert": "true"}
        )
        url = client.storage.from_(BUCKET).get_public_url(storage_name)
        print(f"   ✅ Uploadé → {url[:70]}...")

        # Mettre à jour la DB
        client.table("special_offers").update({"image_url": url}).ilike("titre", f"%{offer_title_partial}%").execute()
        print(f"   ✅ image_url mis à jour en DB")
        return url
    except Exception as e:
        print(f"   ❌ Upload échoué : {e}")
        return None

upload_and_update(FLYER_FORMATION,  "flyer_formation_mai.jpg", "Formation IA")
upload_and_update(FLYER_CONSULTING, "flyer_consulting.jpg",    "Consulting")

# ── ÉTAPE 5 : Vérification finale ────────────────────────────
print("\n🔍 Étape 5 — Vérification finale...")
try:
    res = client.table("special_offers").select("titre, actif, prix, image_url").order("ordre").execute()
    for row in res.data:
        img = "🖼️ " if row.get("image_url") else "📝 "
        status = "✅" if row["actif"] else "⏸️ "
        print(f"   {status} {img} {row['titre'][:45]} | {row['prix']}")
except Exception as e:
    print(f"   ❌ Vérification : {e}")

print("\n" + "=" * 55)
print("🎉 Activation terminée !")
print("\nL'agent peut maintenant :")
print("• 🖼️  Envoyer les flyers automatiquement")
print("• 📝  Partager les descriptions complètes")
print("• 🔗  Donner les liens d'inscription")
print("• 🎯  Détecter qui est intéressé et envoyer la bonne offre")
