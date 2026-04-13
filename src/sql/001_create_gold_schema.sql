-- ─────────────────────────────────────────────────────────────
-- Project Atlas — Gold Layer Schema
-- All amounts in EUR — normalised from source currencies
-- Updated to match Silver transformation output
-- ─────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.daily_customer_spending (
    id                      SERIAL PRIMARY KEY,
    transaction_date        DATE          NOT NULL,
    customer_id             VARCHAR(20)   NOT NULL,
    bank_code               VARCHAR(20)   NOT NULL,
    total_amount_eur        DECIMAL(15,2),
    transaction_count       INTEGER,
    avg_transaction_eur     DECIMAL(15,2),
    max_transaction_eur     DECIMAL(15,2),
    grocery_spend_eur       DECIMAL(15,2) DEFAULT 0,
    ecommerce_spend_eur     DECIMAL(15,2) DEFAULT 0,
    fuel_spend_eur          DECIMAL(15,2) DEFAULT 0,
    entertainment_spend_eur DECIMAL(15,2) DEFAULT 0,
    transport_spend_eur     DECIMAL(15,2) DEFAULT 0,
    top_category            VARCHAR(50),
    pipeline_run_id         VARCHAR(50),
    created_at              TIMESTAMP     DEFAULT NOW(),
    UNIQUE(transaction_date, customer_id, bank_code)
);

CREATE TABLE IF NOT EXISTS gold.fraud_indicators (
    id                  SERIAL PRIMARY KEY,
    transaction_id      VARCHAR(50)   NOT NULL UNIQUE,
    customer_id         VARCHAR(20)   NOT NULL,
    transaction_date    DATE          NOT NULL,
    amount_eur          DECIMAL(15,2),
    is_large_amount     BOOLEAN       DEFAULT FALSE,
    is_suspicious_ip    BOOLEAN       DEFAULT FALSE,
    is_unknown_merchant BOOLEAN       DEFAULT FALSE,
    is_pending_status   BOOLEAN       DEFAULT FALSE,
    is_unusual_currency BOOLEAN       DEFAULT FALSE,
    fraud_score         INTEGER       DEFAULT 0,
    risk_level          VARCHAR(10),
    pipeline_run_id     VARCHAR(50),
    created_at          TIMESTAMP     DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gold.daily_merchant_summary (
    id                  SERIAL PRIMARY KEY,
    transaction_date    DATE          NOT NULL,
    merchant_id         VARCHAR(50)   NOT NULL,
    merchant_name       VARCHAR(200),
    merchant_category   VARCHAR(50),
    total_revenue_eur   DECIMAL(15,2),
    transaction_count   INTEGER,
    unique_customers    INTEGER,
    avg_transaction_eur DECIMAL(15,2),
    pipeline_run_id     VARCHAR(50),
    created_at          TIMESTAMP     DEFAULT NOW(),
    UNIQUE(transaction_date, merchant_id)
);

CREATE TABLE IF NOT EXISTS gold.pipeline_runs (
    id               SERIAL PRIMARY KEY,
    run_id           VARCHAR(50)   NOT NULL UNIQUE,
    pipeline_name    VARCHAR(100),
    processing_date  DATE,
    status           VARCHAR(20),
    records_written  INTEGER       DEFAULT 0,
    completed_at     TIMESTAMP,
    created_at       TIMESTAMP     DEFAULT NOW()
);

SELECT 'Gold schema created successfully' AS status;
