CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tenants (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    api_key_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE customers (
    tenant_id UUID REFERENCES tenants(tenant_id),
    customer_id TEXT NOT NULL,
    city TEXT,
    country TEXT,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE products (
    tenant_id UUID REFERENCES tenants(tenant_id),
    product_id TEXT NOT NULL,
    category TEXT,
    product_cost INTEGER,
    stock_quantity INTEGER,
    stock_alert_threshold INTEGER,
    PRIMARY KEY (tenant_id, product_id)
);

CREATE TABLE orders (
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

CREATE TABLE order_items (
    tenant_id UUID REFERENCES tenants(tenant_id),
    order_id TEXT NOT NULL,
    order_item_id INTEGER NOT NULL,
    product_id TEXT NOT NULL,
    item_total INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, order_item_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id)
);

CREATE TABLE fraud_ground_truth (
    tenant_id UUID REFERENCES tenants(tenant_id),
    order_id TEXT NOT NULL,
    is_fraudulent BOOLEAN NOT NULL,
    fraud_type TEXT,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE fraud_decisions (
    tenant_id UUID REFERENCES tenants(tenant_id),
    order_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BLOCK', 'PASS')),
    decided_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE rag_documents (
    id SERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(tenant_id),
    source_type TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(384)
);

CREATE TABLE forecasts (
    tenant_id UUID REFERENCES tenants(tenant_id),
    product_id TEXT NOT NULL,
    forecast_date DATE NOT NULL,
    predicted_units INTEGER,
    PRIMARY KEY (tenant_id, product_id, forecast_date)
);


-- ============================================================
-- VUES DÉCISIONNELLES
-- ============================================================

CREATE OR REPLACE VIEW v_revenue_by_period AS
SELECT
    tenant_id,
    DATE_TRUNC('month', order_purchase_timestamp) AS period,
    SUM(order_total_amount) AS revenue,
    COUNT(DISTINCT order_id) AS order_count
FROM orders
WHERE order_status = 'delivered'
GROUP BY tenant_id, DATE_TRUNC('month', order_purchase_timestamp);


CREATE OR REPLACE VIEW v_average_basket AS
SELECT
    tenant_id,
    AVG(order_total_amount) AS average_basket,
    COUNT(DISTINCT order_id) AS order_count
FROM orders
WHERE order_status = 'delivered'
GROUP BY tenant_id;


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
