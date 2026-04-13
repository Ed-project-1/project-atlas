# ─────────────────────────────────────────────────────────────
# Bank Transaction Simulator — fixed version
# Exit code 0 means script completed — we need it to loop forever
# Added better startup handling and explicit infinite loop guard
# ─────────────────────────────────────────────────────────────

import json
import random
import time
import uuid
import os
import sys
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s — %(name)s — %(levelname)s — %(message)s'
)
logger = logging.getLogger(__name__)

KAFKA_BROKER  = os.getenv("KAFKA_BROKER",  "kafka:29092")
KAFKA_TOPIC   = os.getenv("KAFKA_TOPIC",   "bank.transactions")
BANK_CODE     = os.getenv("BANK_CODE",     "UNKNOWN")
BANK_NAME     = os.getenv("BANK_NAME",     "Unknown Bank")
SEND_INTERVAL = float(os.getenv("SEND_INTERVAL", "2.0"))
FRAUD_RATE    = float(os.getenv("FRAUD_RATE",    "0.05"))

MERCHANTS = {
    "grocery":       [("MERCH-001", "Biedronka"), ("MERCH-002", "Lidl"), ("MERCH-003", "Zabka")],
    "fuel":          [("MERCH-010", "Orlen"), ("MERCH-011", "BP")],
    "ecommerce":     [("MERCH-020", "Allegro"), ("MERCH-021", "Amazon")],
    "entertainment": [("MERCH-030", "Netflix"), ("MERCH-031", "Spotify")],
    "transport":     [("MERCH-040", "Uber"), ("MERCH-041", "Bolt")],
    "restaurant":    [("MERCH-050", "McDonalds"), ("MERCH-051", "KFC")],
}

AMOUNT_RANGES = {
    "grocery":       (15.0,  350.0),
    "fuel":          (80.0,  300.0),
    "ecommerce":     (25.0,  2000.0),
    "entertainment": (15.0,  60.0),
    "transport":     (8.0,   150.0),
    "restaurant":    (20.0,  120.0),
}

CURRENCIES   = ["PLN"] * 85 + ["EUR"] * 8 + ["USD"] * 5 + ["GBP"] * 2
DEVICE_TYPES = ["card"] * 40 + ["mobile"] * 35 + ["web"] * 20 + ["atm"] * 5
FRAUD_IPS    = ["185.220.101.1", "185.220.101.2", "198.96.155.3"]
LEGIT_IPS    = [f"192.168.{random.randint(1,254)}.{random.randint(1,254)}" for _ in range(50)]


def generate_transaction(customer_id: str, is_fraud: bool) -> dict:
    """Generate one transaction — normal or fraudulent"""
    if is_fraud:
        return {
            "transaction_id":    f"TXN-{BANK_CODE}-FRAUD-{uuid.uuid4().hex[:8].upper()}",
            "customer_id":       customer_id,
            "account_id":        f"ACC-{customer_id}-001",
            "merchant_id":       "MERCH-UNKNOWN-999",
            "merchant_name":     "Suspicious Merchant",
            "merchant_category": "unknown",
            "amount":            str(round(random.uniform(5000, 50000), 2)),
            "currency":          random.choice(["USD", "EUR"]),
            "transaction_type":  "transfer",
            "status":            "pending",
            "timestamp":         datetime.now(timezone.utc).isoformat(),
            "bank_code":         BANK_CODE,
            "country":           "PL",
            "device_type":       "web",
            "ip_address":        random.choice(FRAUD_IPS),
        }
    else:
        category = random.choice(list(MERCHANTS.keys()))
        merchant_id, merchant_name = random.choice(MERCHANTS[category])
        min_amt, max_amt = AMOUNT_RANGES[category]
        return {
            "transaction_id":    f"TXN-{BANK_CODE}-{uuid.uuid4().hex[:12].upper()}",
            "customer_id":       customer_id,
            "account_id":        f"ACC-{customer_id}-001",
            "merchant_id":       merchant_id,
            "merchant_name":     merchant_name,
            "merchant_category": category,
            "amount":            str(round(random.uniform(min_amt, max_amt), 2)),
            "currency":          random.choice(CURRENCIES),
            "transaction_type":  "purchase",
            "status":            "completed",
            "timestamp":         datetime.now(timezone.utc).isoformat(),
            "bank_code":         BANK_CODE,
            "country":           "PL",
            "device_type":       random.choice(DEVICE_TYPES),
            "ip_address":        random.choice(LEGIT_IPS),
        }


def wait_for_kafka():
    """
    Wait until Kafka is reachable before starting
    Exit code 0 was happening because kafka-python was
    not installed — this confirms the import works
    """
    logger.info(f"Waiting for Kafka at {KAFKA_BROKER}...")
    max_wait = 120  # wait up to 2 minutes
    waited   = 0

    while waited < max_wait:
        try:
            from kafka.admin import KafkaAdminClient
            admin = KafkaAdminClient(bootstrap_servers=[KAFKA_BROKER])
            admin.close()
            logger.info("Kafka is ready")
            return True
        except Exception as e:
            logger.info(f"Kafka not ready yet — waiting 5s ({e})")
            time.sleep(5)
            waited += 5

    logger.error("Kafka never became ready — exiting")
    sys.exit(1)


def main():
    logger.info(f"Starting {BANK_NAME} ({BANK_CODE}) simulator")
    logger.info(f"Topic: {KAFKA_TOPIC} | Interval: {SEND_INTERVAL}s | Fraud rate: {FRAUD_RATE}")

    # Wait for Kafka to be ready
    wait_for_kafka()

    # Import here — after confirming kafka-python is available
    from kafka import KafkaProducer

    # Create producer
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_BROKER],
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
        acks="all",
        retries=3,
    )

    logger.info("Producer created — starting transaction loop")

    # Generate customer pool for this bank
    customers = [f"CUST-{BANK_CODE}-{i:03d}" for i in range(1, 51)]
    count = 0

    # Infinite loop — this must never exit
    while True:
        try:
            customer_id = random.choice(customers)
            is_fraud    = random.random() < FRAUD_RATE
            transaction = generate_transaction(customer_id, is_fraud)

            future = producer.send(
                KAFKA_TOPIC,
                key=customer_id,
                value=transaction
            )
            metadata = future.get(timeout=10)
            count += 1

            if count % 10 == 0:
                flag = "FRAUD" if is_fraud else "OK"
                logger.info(
                    f"{BANK_NAME} [{flag}] sent {count} txns — "
                    f"partition={metadata.partition} offset={metadata.offset}"
                )

            time.sleep(SEND_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Simulator stopped by user")
            break
        except Exception as e:
            logger.error(f"Error: {e} — retrying in 5s")
            time.sleep(5)

    producer.flush()
    producer.close()


# ─────────────────────────────────────────────────────────────
# Entry point — this is what runs when container starts
# Without this block the script does nothing when imported
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
