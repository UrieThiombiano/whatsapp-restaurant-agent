-- ═══════════════════════════════════════════════════════════════════
--  PUKRI AI SYSTEMS — Tables relance + qualification leads
--  Exécuter dans : Supabase → SQL Editor → New Query
-- ═══════════════════════════════════════════════════════════════════

-- ── Table de qualification des leads ─────────────────────────────
-- Enrichit les leads avec budget, délai, rôle, score
CREATE TABLE IF NOT EXISTS lead_qualification (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  phone         TEXT NOT NULL UNIQUE,
  nom           TEXT DEFAULT '',
  service_vise  TEXT DEFAULT '',   -- formation / consulting / agent_ia / autre
  budget        TEXT DEFAULT '',   -- "moins de 30k" / "30k-100k" / "plus de 100k" / "non précisé"
  delai_achat   TEXT DEFAULT '',   -- "immédiat" / "ce mois" / "3 mois" / "pas encore décidé"
  role          TEXT DEFAULT '',   -- "étudiant" / "entrepreneur" / "salarié" / "dirigeant" / "autre"
  taille_struct TEXT DEFAULT '',   -- "individuel" / "TPE" / "PME" / "grande entreprise"
  score         INT  DEFAULT 0,    -- Score 0-100 (calculé automatiquement)
  statut        TEXT DEFAULT 'nouveau', -- nouveau / chaud / tiède / froid / converti / perdu
  nb_contacts   INT  DEFAULT 0,    -- Nombre de fois qu'on a essayé de le recontacter
  notes         TEXT DEFAULT '',
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lq_phone  ON lead_qualification(phone);
CREATE INDEX IF NOT EXISTS idx_lq_score  ON lead_qualification(score DESC);
CREATE INDEX IF NOT EXISTS idx_lq_statut ON lead_qualification(statut);

ALTER TABLE lead_qualification ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access lq" ON lead_qualification FOR ALL USING (true) WITH CHECK (true);

-- ── Table des relances planifiées ─────────────────────────────────
CREATE TABLE IF NOT EXISTS followups (
  id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  phone         TEXT NOT NULL,
  nom           TEXT DEFAULT '',
  message       TEXT NOT NULL,        -- Message à envoyer
  sequence      INT  DEFAULT 1,       -- J+1, J+3, J+7
  statut        TEXT DEFAULT 'pending', -- pending / sent / cancelled
  scheduled_at  TIMESTAMPTZ NOT NULL,  -- Quand envoyer
  sent_at       TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fu_pending   ON followups(statut, scheduled_at) WHERE statut = 'pending';
CREATE INDEX IF NOT EXISTS idx_fu_phone     ON followups(phone);

ALTER TABLE followups ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access fu" ON followups FOR ALL USING (true) WITH CHECK (true);

-- Vérification
SELECT 'Tables créées ✅' AS status;
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('lead_qualification','followups');
