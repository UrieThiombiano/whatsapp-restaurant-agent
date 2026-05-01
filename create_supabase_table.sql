-- ─────────────────────────────────────────────────────────────────
--  🤖 PUKRI AI SYSTEMS — Table conversations Supabase
--  À exécuter dans : Supabase Dashboard → SQL Editor → New query
-- ─────────────────────────────────────────────────────────────────

-- Table principale
CREATE TABLE IF NOT EXISTS conversations (
  id         UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  phone      TEXT NOT NULL,
  name       TEXT DEFAULT '',
  role       TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
  content    TEXT NOT NULL,
  topics     TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index pour accélérer les requêtes par numéro de téléphone
CREATE INDEX IF NOT EXISTS idx_conversations_phone
  ON conversations(phone);

-- Index pour le tri chronologique
CREATE INDEX IF NOT EXISTS idx_conversations_phone_date
  ON conversations(phone, created_at DESC);

-- Politique RLS (Row Level Security) — accès uniquement via service_role
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- Autoriser toutes les opérations pour le service_role (backend)
CREATE POLICY "Service role full access"
  ON conversations
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- ─── Vérification ───────────────────────────────────────────────
SELECT 'Table conversations créée avec succès ✅' AS status;
