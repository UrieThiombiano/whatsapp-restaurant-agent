"""
upload_pukri_images.py — Upload des images PUKRI vers Supabase Storage.
Exécuter UNE FOIS sur ta machine pour uploader les flyers.

Usage :
  pip install supabase
  python3 upload_pukri_images.py
"""

import os
import sys
from supabase import create_client

SUPABASE_URL = "https://bchzfrtiocizylqiwloh.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")  # Depuis variable d'env ou .env

if not SUPABASE_KEY:
    print("❌ Définis SUPABASE_SERVICE_KEY dans ton environnement")
    sys.exit(1)

client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET = "pukri-media"

def upload_image(local_path: str, storage_name: str) -> str:
    """Upload une image et retourne son URL publique."""
    if not os.path.exists(local_path):
        print(f"❌ Fichier non trouvé : {local_path}")
        return ""

    with open(local_path, "rb") as f:
        data = f.read()

    ext      = local_path.split(".")[-1].lower()
    mimetype = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")

    try:
        # Supprimer si existe déjà
        client.storage.from_(BUCKET).remove([storage_name])
    except Exception:
        pass

    res = client.storage.from_(BUCKET).upload(
        path=storage_name,
        file=data,
        file_options={"content-type": mimetype}
    )
    print(f"  Upload: {res}")

    url = client.storage.from_(BUCKET).get_public_url(storage_name)
    return url


def update_offer_image(titre_partial: str, image_url: str):
    """Met à jour l'image_url d'une offre dans Supabase."""
    res = (
        client.table("special_offers")
        .update({"image_url": image_url})
        .ilike("titre", f"%{titre_partial}%")
        .execute()
    )
    print(f"  DB updated: {res.data}")


print("\n🖼️  Upload images PUKRI → Supabase Storage")
print("=" * 50)

# ── OFFRE 1 : Flyer Formation Mai ────────────────────────────
print("\n📤 Flyer Formation Mai 2026...")
# Mets le vrai nom/chemin de ton fichier ici
url1 = upload_image("flyer_formation_mai.jpg", "flyer_formation_mai.jpg")
if url1:
    print(f"  ✅ URL : {url1}")
    update_offer_image("Formation IA", url1)
    print("  ✅ DB mis à jour")

# ── OFFRE 2 : Flyer Consulting ────────────────────────────────
print("\n📤 Flyer Consulting...")
url2 = upload_image("flyer_consulting.jpg", "flyer_consulting.jpg")
if url2:
    print(f"  ✅ URL : {url2}")
    update_offer_image("Consulting", url2)
    print("  ✅ DB mis à jour")

print("\n" + "=" * 50)
print("✅ Upload terminé !")
print("\nURLs à vérifier dans Supabase → Table Editor → special_offers")
