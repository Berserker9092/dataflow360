-- =============================================================================
-- Migrations DataFlow360
-- Exécuté automatiquement au premier démarrage du conteneur Postgres.
-- =============================================================================

-- Colonnes supplémentaires pour la table tenants
ALTER TABLE tenants
  ADD COLUMN IF NOT EXISTS email TEXT UNIQUE,
  ADD COLUMN IF NOT EXISTS company_name TEXT,
  ADD COLUMN IF NOT EXISTS contact_name TEXT,
  ADD COLUMN IF NOT EXISTS phone TEXT,
  ADD COLUMN IF NOT EXISTS country TEXT,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- Colonnes supplémentaires pour la table customers
ALTER TABLE customers
  ADD COLUMN IF NOT EXISTS full_name TEXT,
  ADD COLUMN IF NOT EXISTS email TEXT,
  ADD COLUMN IF NOT EXISTS phone TEXT;

-- Index pour accélérer les recherches
CREATE INDEX IF NOT EXISTS idx_tenants_email ON tenants(email);
CREATE INDEX IF NOT EXISTS idx_customers_full_name ON customers(full_name);
