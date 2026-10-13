-- =============================================================================
-- Seed DataFlow360 — Création du tenant de démo
-- Exécuté automatiquement au premier démarrage du conteneur Postgres.
-- =============================================================================

INSERT INTO tenants (tenant_id, name, api_key_hash, email, company_name, contact_name, country)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'Boutique démo',
  encode(sha256('demo-key-change-me-123'::bytea), 'hex'),
  'demo@dataflow360.com',
  'Boutique Démo SARL',
  'Cheikhouna Ba',
  'SN'
)
ON CONFLICT (tenant_id) DO UPDATE SET
  name = EXCLUDED.name,
  email = EXCLUDED.email,
  company_name = EXCLUDED.company_name,
  contact_name = EXCLUDED.contact_name,
  country = EXCLUDED.country;
