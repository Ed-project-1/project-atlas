# Project Atlas

Real-time financial transaction pipeline built on the medallion lakehouse architecture. Three Polish banks stream transactions simultaneously through Bronze, Silver, and Gold processing layers using Apache Kafka, Spark Structured Streaming, and Delta Lake.

---

## Architecture

```
PKO Bank ──→ Kafka topic: bank.pko.transactions ──┐
mBank    ──→ Kafka topic: bank.mbank.transactions ─┼──→ Spark Structured Streaming
ING Bank ──→ Kafka topic: bank.ing.transactions  ──┘
                                                          │
                                                          ▼
                                               Bronze Delta Lake
                                               (raw, immutable)
                                                          │
                                                          ▼
                                               Silver Delta Lake
                                          (validated, fraud-scored, EUR)
                                                          │
                                                          ▼
                                               Gold PostgreSQL
                                          (aggregated, Power BI ready)
```

---

## Stack

| Local | Azure | Purpose |
|-------|-------|---------|
| Apache Kafka | Azure Event Hubs | Message broker |
| Apache Spark | Azure Databricks | Data processing |
| Delta Lake | Delta Lake | ACID storage format |
| MinIO | ADLS Gen2 | Object storage |
| MongoDB | Azure Cosmos DB | Audit logging |
| PostgreSQL | Azure Synapse | Gold SQL layer |
| JupyterLab | Databricks notebooks | Development |

---

## Quick Start

**Prerequisites:** Docker Desktop, 16GB RAM, 20GB free disk

```bash
# Clone
git clone https://github.com/Ed-project-1/project-atlas.git
cd project-atlas

# Configure environment
cp .env.example .env
# Edit .env and fill in your values

# Build custom Spark image (includes Kafka + Hadoop AWS JARs)
docker compose build spark-master spark-worker bank-pko bank-mbank bank-ing

# Start full stack
docker compose up -d

# Wait 30 seconds for Kafka to be healthy
sleep 30

# Copy .env into Jupyter container
docker cp .env atlas-jupyter:/home/jovyan/work/.env

# Verify all 12 containers are running
docker compose ps
```

---

## Services

| Service | URL | Notes |
|---------|-----|-------|
| JupyterLab | http://localhost:8888 | Token: `atlas2024` |
| Spark Master | http://localhost:8080 | Cluster status |
| Spark App UI | http://localhost:4040 | Running jobs |
| MinIO Console | http://localhost:9001 | Browse Delta files |
| Kafka UI | http://localhost:8090 | Monitor topics |

---

## Running the Pipeline

Open JupyterLab at `http://localhost:8888` and run notebooks in this order:

### 1. Bronze — `notebooks/02_stream_bronze_ingestion.ipynb`
Reads all three Kafka topics simultaneously. Writes raw transactions to Bronze Delta Lake every 10 seconds. Keep this running.

### 2. Silver — `notebooks/03_stream_silver_processing.ipynb`
Reads Bronze Delta Lake as a stream. Validates records, computes fraud signals, normalises currencies to EUR. Writes to Silver Delta Lake every 30 seconds. Keep this running alongside Bronze.

### 3. Gold — `notebooks/04_gold_aggregation.ipynb`
Reads Silver Delta Lake as a batch. Computes three aggregations and writes to PostgreSQL. Rerun every 5 minutes for fresh metrics.

---

## Medallion Layers

### Bronze — Raw Zone
- All columns StringType — accepts everything including bad data
- Partitioned by `bank_code` and `processing_date`
- Immutable — never modified after write
- Checkpoint at `s3a://bronze/checkpoints/` for exactly-once processing

### Silver — Clean Zone
Seven validation rules applied to every record:

| Rule | Field | Quarantine Reason |
|------|-------|-------------------|
| 1 | transaction_id not null | missing_transaction_id |
| 2 | customer_id not null | missing_customer_id |
| 3 | amount not null | missing_amount |
| 4 | amount is positive decimal | invalid_amount |
| 5 | currency in valid list | invalid_currency |
| 6 | bank_code recognised | unknown_bank_code |
| 7 | timestamp parseable | invalid_timestamp |

Five fraud signals computed per record:

| Signal | Condition |
|--------|-----------|
| `is_large_amount` | amount > EUR 5,000 |
| `is_suspicious_ip` | IP in Tor exit node ranges |
| `is_unknown_merchant` | merchant_category = unknown |
| `is_pending_status` | status = PENDING |
| `is_unusual_currency` | currency not PLN/EUR/USD/GBP |

`fraud_score` = sum of signals (0–5). `risk_level` = low / medium / high.

All amounts normalised to EUR using configurable FX rates.

### Gold — Business Zone
Three aggregations written to PostgreSQL:

- `gold.daily_customer_spending` — spend per customer per day by category
- `gold.fraud_indicators` — flagged transactions with all fraud signals
- `gold.daily_merchant_summary` — revenue per merchant per day

---

## Bank Simulators

| Bank | Topic | Interval | Fraud Rate |
|------|-------|----------|------------|
| PKO Bank Polski | `bank.pko.transactions` | 2s | 5% |
| mBank | `bank.mbank.transactions` | 3s | 8% |
| ING Bank Śląski | `bank.ing.transactions` | 1.5s | 3% |

Combined throughput: ~90 transactions/minute

```bash
# Stop simulators (saves disk space)
docker compose stop bank-pko bank-mbank bank-ing

# Start simulators
docker compose start bank-pko bank-mbank bank-ing
```

---

## Project Structure

```
project-atlas/
├── docker-compose.yml          # Full stack definition
├── Dockerfile.spark            # Custom Spark with Kafka JARs
├── azure-pipelines.yml         # Azure DevOps CI/CD pipeline
├── DEPLOY.md                   # Full deployment guide
├── .env.example                # Environment variable template
├── .gitignore
├── notebooks/
│   ├── 02_stream_bronze_ingestion.ipynb
│   ├── 03_stream_silver_processing.ipynb
│   └── 04_gold_aggregation.ipynb
├── src/
│   ├── simulators/
│   │   ├── bank_simulator.py   # Transaction producer
│   │   ├── requirements.txt    # kafka-python-ng==2.2.2
│   │   └── Dockerfile
│   └── sql/
│       └── 001_create_gold_schema.sql
└── infrastructure/
    └── main.bicep              # Azure IaC template
```

---

## Azure Deployment

The local code maps directly to Azure. Only connection strings change.

```python
# Local → Azure storage path change
"s3a://bronze/delta/transactions/"
→ "abfss://bronze@atlas.dfs.core.windows.net/delta/transactions/"

# Local → Azure Kafka broker change
"kafka:29092"
→ "atlas.servicebus.windows.net:9093"
```

See [DEPLOY.md](DEPLOY.md) for full Azure deployment instructions.

---

## CI/CD

Azure DevOps three-stage pipeline defined in `azure-pipelines.yml`:

```
Validate → Deploy Dev → Deploy Production (manual approval)
```

All secrets stored in Azure Key Vault and loaded via Variable Group. No credentials in the pipeline YAML.

---

## Verify Gold Data

```bash
docker exec -it atlas-postgres psql -U atlasadmin -d atlas_gold -c "
SELECT bank_code,
       COUNT(DISTINCT customer_id) AS customers,
       ROUND(SUM(total_amount_eur)::numeric, 2) AS total_eur,
       SUM(transaction_count) AS transactions
FROM gold.daily_customer_spending
WHERE transaction_date = CURRENT_DATE
GROUP BY bank_code
ORDER BY total_eur DESC;
"
```

---

## Shutdown

```bash
# Stop producers first
docker compose stop bank-pko bank-mbank bank-ing

# Stop all containers — data preserved in volumes
docker compose down

# Full reset — deletes all data
docker compose down -v
```

---

## License

MIT
