# Project Atlas — Deployment Guide

Real-time financial transaction medallion pipeline.  
Bronze → Silver → Gold using Kafka, Spark, Delta Lake, MinIO, MongoDB, PostgreSQL.

---

## Quick Start (Local)

```bash
# Clone the repo
git clone https://github.com/yourname/project-atlas.git
cd project-atlas

# Copy env template and fill in values
cp .env.example .env

# Copy .env into Jupyter container after stack starts
# (see step 3 below)

# Build custom Spark image with Kafka JARs
docker compose build spark-master spark-worker bank-pko bank-mbank bank-ing

# Start full stack
docker compose up -d

# Wait 30 seconds for Kafka to be healthy
sleep 30

# Copy .env into Jupyter
docker cp .env atlas-jupyter:/home/jovyan/work/.env

# Verify all 12 containers are running
docker compose ps
```

---

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| JupyterLab | http://localhost:8888 | token: atlas2024 |
| Spark Master | http://localhost:8080 | — |
| MinIO Console | http://localhost:9001 | atlasadmin / atlaspassword123 |
| Kafka UI | http://localhost:8090 | — |
| Spark App UI | http://localhost:4040 | — |

---

## Notebook Execution

Run notebooks in this order from JupyterLab at http://localhost:8888:

### 1. Bronze Streaming (`02_stream_bronze_ingestion.ipynb`)
Reads from all three Kafka topics simultaneously.  
Writes raw transactions to Bronze Delta Lake every 10 seconds.  
**Keep running** — do not stop between Silver and Gold.

### 2. Silver Streaming (`03_stream_silver_processing.ipynb`)
Reads Bronze Delta Lake as a stream.  
Validates, fraud-scores, normalises to EUR, quarantines bad records.  
Writes clean records to Silver Delta Lake every 30 seconds.  
**Keep running** alongside Bronze.

### 3. Gold Batch (`04_gold_aggregation.ipynb`)
Reads Silver Delta Lake as a batch.  
Computes three aggregations and writes to PostgreSQL.  
**Rerun every 5 minutes** for fresh metrics.

---

## Manage Bank Simulators

```bash
# Stop producers (saves disk space)
docker compose stop bank-pko bank-mbank bank-ing

# Start producers
docker compose start bank-pko bank-mbank bank-ing

# Check producer logs
docker compose logs --tail=20 bank-pko
```

---

## Verify Gold Data in PostgreSQL

```bash
docker exec -it atlas-postgres psql -U atlasadmin -d atlas_gold -c "
SELECT bank_code,
       COUNT(DISTINCT customer_id) as customers,
       ROUND(SUM(total_amount_eur)::numeric, 2) as total_eur
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

# Stop and delete all data (full reset)
docker compose down -v
```

---

## Azure Deployment

### Prerequisites

```bash
# Install Azure CLI
brew install azure-cli

# Install Bicep
az bicep install

# Login
az login

# Create resource group
az group create --name atlas-dev-rg --location westeurope
```

### Deploy Infrastructure with Bicep

```bash
# Deploy all Azure resources
az deployment group create \
  --resource-group atlas-dev-rg \
  --template-file infrastructure/main.bicep \
  --parameters environment=dev projectName=atlas

# Confirm resources created:
# - Storage account (ADLS Gen2) with bronze/silver/gold containers
# - Event Hubs namespace (Kafka-compatible)
# - Cosmos DB account (MongoDB API)
# - Azure Database for PostgreSQL Flexible Server
# - Key Vault for secrets
# - Databricks workspace (optional)
```

### Update Connection Strings for Azure

Change these three values in notebooks to move from local to Azure:

```python
# 1. Storage paths
# Local:
BRONZE_PATH = "s3a://bronze/delta/transactions/"
# Azure:
BRONZE_PATH = "abfss://bronze@atlasstorage.dfs.core.windows.net/delta/transactions/"

# 2. Kafka broker
# Local:
.option("kafka.bootstrap.servers", "kafka:29092")
# Azure:
.option("kafka.bootstrap.servers", "atlas.servicebus.windows.net:9093")
.option("kafka.security.protocol", "SASL_SSL")
.option("kafka.sasl.mechanism", "PLAIN")

# 3. Spark master (Databricks — remove entirely)
# Local:
.master("local[2]")
# Azure: delete this line — Databricks provides the session
```

### Azure DevOps Pipeline Setup

```bash
# 1. Create Azure DevOps project at dev.azure.com
# 2. Connect to your GitHub repo
# 3. Create service connection to Azure subscription
#    Project Settings → Service connections → New → Azure Resource Manager
#    Name it: atlas-service-connection
# 4. Create variable group
#    Pipelines → Library → Variable groups → atlas-variable-group
#    Link to Key Vault for secrets
# 5. Push azure-pipelines.yml to repo
# 6. Pipeline triggers automatically on push to main
```

---

## Troubleshooting

### Containers not starting

```bash
# Check logs for specific service
docker compose logs kafka
docker compose logs spark-master

# Restart individual service
docker compose restart kafka
```

### Kafka connection refused

```bash
# Kafka needs 30 seconds to fully start
# Wait and retry, or check health
docker compose ps | grep kafka
# Should show: healthy
```

### Spark session dead (ConnectionRefusedError)

```bash
# Restart Jupyter kernel in JupyterLab:
# Kernel menu → Restart Kernel and Clear All Outputs
# Then rerun all cells from Cell 1
```

### Bronze/Silver data not appearing in MinIO

```bash
# Check MinIO buckets were created
docker exec atlas-minio-setup ls /dev/null || true
# Open http://localhost:9001 and check bronze bucket
# Look for delta/transactions/ folder
```

### PostgreSQL schema missing

```bash
docker exec -it atlas-postgres psql -U atlasadmin -d atlas_gold \
  -c "DROP SCHEMA IF EXISTS gold CASCADE; CREATE SCHEMA gold;"

# Then run the SQL init file manually
docker exec -i atlas-postgres psql -U atlasadmin -d atlas_gold \
  < src/sql/001_create_gold_schema.sql
```

---

## Architecture Summary

```
Bank simulators (PKO / mBank / ING)
  ↓ Kafka topics (one per bank, 3 partitions each)
Apache Kafka  →  ~90 transactions/minute
  ↓ Spark Structured Streaming (10s micro-batch)
Bronze Delta Lake  →  s3a://bronze/delta/transactions/
  ↓ Spark Structured Streaming (30s micro-batch)
  ↓ 7 validation rules, 5 fraud signals, EUR normalisation
Silver Delta Lake  →  s3a://silver/delta/transactions/
  ↓ Bad records  →  s3a://quarantine/silver/transactions/
  ↓ Spark batch aggregation (every 5 minutes)
PostgreSQL Gold  →  gold.daily_customer_spending
                    gold.fraud_indicators
                    gold.daily_merchant_summary
  ↓ Power BI connects here
```

---

## Azure Mapping

| Local | Azure | Notes |
|-------|-------|-------|
| Apache Kafka | Azure Event Hubs | Same Kafka protocol |
| MinIO | ADLS Gen2 | Change s3a:// to abfss:// |
| Spark local[2] | Azure Databricks | Remove .master() line |
| MongoDB | Cosmos DB | Change connection string |
| PostgreSQL | Azure Synapse | Change connection string |
| .env | Azure Key Vault | dbutils.secrets.get() |
| docker-compose | Bicep templates | Deploy with az CLI |
| Manual notebooks | Azure Data Factory | ADF Databricks Activity |
