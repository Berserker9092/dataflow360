-- ============================================================
-- DATAFLOW360 : SCHEMA POSTGRESQL
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- 1. TENANTS
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    api_key_hash TEXT NOT NULL UNIQUE,
    email TEXT UNIQUE,
    company_name TEXT,
    contact_name TEXT,
    phone TEXT,
    country TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. CLIENTS
CREATE TABLE IF NOT EXISTS customers (
    tenant_id UUID REFERENCES tenants(tenant_id),
    customer_id TEXT NOT NULL,
    city TEXT,
    country TEXT,
    full_name TEXT,
    email TEXT,
    phone TEXT,
    PRIMARY KEY (tenant_id, customer_id)
);

-- 3. PRODUITS
CREATE TABLE IF NOT EXISTS products (
    tenant_id UUID REFERENCES tenants(tenant_id),
    product_id TEXT NOT NULL,
    product_name TEXT,
    category TEXT,
    product_cost INTEGER,
    stock_quantity INTEGER,
    stock_alert_threshold INTEGER,
    PRIMARY KEY (tenant_id, product_id)
);

-- Migration pour les bases existantes
ALTER TABLE products ADD COLUMN IF NOT EXISTS product_name TEXT;
-- 4. COMMANDES
CREATE TABLE IF NOT EXISTS orders (
    tenant_id UUID REFERENCES tenants(tenant_id),
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    order_status TEXT,
    order_purchase_timestamp TIMESTAMP,
    order_total_amount INTEGER,
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id)
);

-- 5. LIGNES DE COMMANDE
CREATE TABLE IF NOT EXISTS order_items (
    tenant_id UUID REFERENCES tenants(tenant_id),
    order_id TEXT NOT NULL,
    order_item_id INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    item_total INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, order_item_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id)
);

-- Compatibilité avec les bases déjà créées
ALTER TABLE order_items
ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1;

-- 6. VÉRITÉ TERRAIN POUR LA FRAUDE
CREATE TABLE IF NOT EXISTS fraud_ground_truth (
    tenant_id UUID REFERENCES tenants(tenant_id),
    order_id TEXT NOT NULL,
    is_fraudulent BOOLEAN NOT NULL,
    fraud_type TEXT,
    PRIMARY KEY (tenant_id, order_id)
);

-- 7. DÉCISIONS DE FRAUDE
CREATE TABLE IF NOT EXISTS fraud_decisions (
    tenant_id UUID REFERENCES tenants(tenant_id),
    order_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BLOCK', 'PASS')),
    decided_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

-- 8. DOCUMENTS POUR LE RAG
CREATE TABLE IF NOT EXISTS rag_documents (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(tenant_id),
    source_type TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(384)
);

-- 9. PRÉVISIONS
CREATE TABLE IF NOT EXISTS forecasts (
    tenant_id UUID REFERENCES tenants(tenant_id),
    product_id TEXT NOT NULL,
    forecast_date DATE NOT NULL,
    predicted_units INTEGER,
    PRIMARY KEY (tenant_id, product_id, forecast_date)
);

-- 10. AVIS CLIENTS
CREATE TABLE IF NOT EXISTS order_reviews (
    tenant_id UUID NOT NULL,
    review_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    review_score INTEGER,
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date TIMESTAMP,
    PRIMARY KEY (tenant_id, review_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id)
);

-- 11. TICKETS DU SUPPORT CLIENT
CREATE TABLE IF NOT EXISTS support_tickets (
    tenant_id UUID NOT NULL,
    ticket_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    ticket_category TEXT,
    ticket_subject TEXT,
    ticket_message TEXT,
    ticket_status TEXT,
    created_at TIMESTAMP,
    PRIMARY KEY (tenant_id, ticket_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id)
);

-- ============================================================
-- VUES DÉCISIONNELLES
-- ============================================================

-- Chiffre d'affaires mensuel
CREATE OR REPLACE VIEW v_revenue_by_period AS
SELECT
    tenant_id,
    DATE_TRUNC('month', order_purchase_timestamp) AS period,
    SUM(order_total_amount) AS revenue,
    COUNT(DISTINCT order_id) AS order_count
FROM orders
WHERE order_status = 'delivered'
GROUP BY tenant_id, DATE_TRUNC('month', order_purchase_timestamp);

-- Panier moyen
CREATE OR REPLACE VIEW v_average_basket AS
SELECT
    tenant_id,
    AVG(order_total_amount) AS average_basket,
    COUNT(DISTINCT order_id) AS order_count
FROM orders
WHERE order_status = 'delivered'
GROUP BY tenant_id;

-- Produits les plus rentables
CREATE OR REPLACE VIEW v_top_products AS
SELECT
    oi.tenant_id,
    oi.product_id,
    SUM(oi.item_total) AS revenue,
    COUNT(DISTINCT oi.order_id) AS order_count
FROM order_items oi
JOIN orders o
    ON o.tenant_id = oi.tenant_id
    AND o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
GROUP BY oi.tenant_id, oi.product_id;
