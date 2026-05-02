-- ═══════════════════════════════════════════════════════════════
--  🤖 PUKRI AI SYSTEMS — Table special_offers + Storage
--  Exécuter dans : Supabase → SQL Editor → New Query
-- ═══════════════════════════════════════════════════════════════

-- ── Table des offres spéciales ────────────────────────────────
CREATE TABLE IF NOT EXISTS special_offers (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  titre            TEXT NOT NULL,
  description      TEXT NOT NULL,         -- Message complet à envoyer
  image_url        TEXT DEFAULT '',        -- URL publique de l'image (Supabase Storage)
  lien_inscription TEXT DEFAULT '',        -- Lien Google Form ou autre
  cible            TEXT DEFAULT 'tous',    -- Audience cible (étudiants, entreprises, tous)
  prix             TEXT DEFAULT '',        -- Ex: "19 990 FCFA"
  date_debut       DATE,                   -- Date de début de l'offre
  date_fin         DATE,                   -- Date de fin (null = pas de limite)
  actif            BOOLEAN DEFAULT TRUE,   -- Activer/désactiver depuis Supabase
  ordre            INT DEFAULT 0,          -- Ordre d'affichage (0 = premier)
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Index pour les offres actives
CREATE INDEX IF NOT EXISTS idx_special_offers_actif
  ON special_offers(actif, ordre);

-- RLS
ALTER TABLE special_offers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access"
  ON special_offers FOR ALL USING (true) WITH CHECK (true);

-- ── Bucket Storage pour les images ────────────────────────────
-- (À exécuter séparément dans Supabase Storage UI si la commande SQL ne marche pas)
INSERT INTO storage.buckets (id, name, public)
VALUES ('pukri-media', 'pukri-media', true)
ON CONFLICT (id) DO NOTHING;

-- Politique : lecture publique des images
CREATE POLICY "Public read pukri-media"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'pukri-media');

-- Politique : écriture via service_role
CREATE POLICY "Service write pukri-media"
  ON storage.objects FOR INSERT
  WITH CHECK (bucket_id = 'pukri-media');

-- ── Données initiales ─────────────────────────────────────────

-- OFFRE 1 : Formation Mai 2026
INSERT INTO special_offers (
  titre, description, image_url, lien_inscription,
  cible, prix, date_debut, date_fin, actif, ordre
) VALUES (
  'Formation IA Pratique — Mai 2026',
  '🚨 Étudiants, chercheurs d''emploi, candidats aux concours… cette formation peut changer votre avenir !

Aujourd''hui, beaucoup ratent des opportunités non pas par manque de talent, mais parce qu''ils ne maîtrisent pas encore l''Intelligence Artificielle.

Avec l''IA, vous pouvez :
✅ Étudier plus efficacement
✅ Préparer vos concours intelligemment
✅ Créer un CV professionnel
✅ Rédiger lettres, dossiers et présentations plus vite
✅ Trouver de meilleures opportunités
✅ Développer des compétences recherchées

🎓 PUKRI AI SYSTEMS lance une formation pratique en IA
📅 En ligne : 14 Mai (depuis partout)
📍 En présentiel à Ouagadougou : 15 Mai
💰 Coût : 19 990 FCFA
⚠️ Places limitées pour une meilleure prise en charge — inscription obligatoire

🚀 Prenez de l''avance sur les autres dès maintenant !',
  '',  -- image_url à remplir après upload
  'https://docs.google.com/forms/d/e/1FAIpQLSfkNBq-XEzNItQI_egrZ9bkOkSefrz8ergHKGEdkq9-G_KpIw/viewform?usp=publish-editor',
  'étudiants, chercheurs emploi, concours',
  '19 990 FCFA',
  '2026-05-14',
  '2026-05-15',
  true,
  1
);

-- OFFRE 2 : Consulting IA
INSERT INTO special_offers (
  titre, description, image_url, lien_inscription,
  cible, prix, date_debut, date_fin, actif, ordre
) VALUES (
  'Consulting IA — Offre Spéciale Entreprises',
  '💼 Votre entreprise est-elle prête pour l''IA ?

PUKRI AI SYSTEMS vous propose un accompagnement personnalisé :
✅ Audit de votre activité
✅ Identification des opportunités IA dans votre secteur
✅ Plan d''action concret et réalisable
✅ Recommandations adaptées à votre réalité terrain

🎯 Résultat : Gain de temps, réduction des coûts, plus de performance

📞 Contactez-nous pour une consultation :
WhatsApp : 72 91 80 81 / 75 85 07 12
📧 contact.pukri.ai@gmail.com

🚀 Les entreprises qui intègrent l''IA aujourd''hui domineront leur marché demain !',
  '',  -- image_url à remplir après upload
  '',  -- contact direct, pas de formulaire
  'entreprises, dirigeants, managers',
  'Sur devis',
  NULL,
  NULL,
  true,
  2
);

-- ── Vérification ──────────────────────────────────────────────
SELECT titre, cible, prix, actif, date_debut, date_fin
FROM special_offers
ORDER BY ordre;

SELECT 'Table special_offers créée ✅' AS status;
