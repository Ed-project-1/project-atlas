''' 
1.Bank Transaction Simulator
2.Simulates a bank sending real-time transactions to Kafka
3.Each bank has its own topic and transaction patterns
4.Runs continuously — one transaction every few seconds
5. In production this is replaced by:
6.  - Real bank SFTP feeds picked up by ADF
7.   - Real-time payment networks like SWIFT or SEPA
8.  - Azure Event Hubs receiving bank webhooks
'''
import json
import random
import time
import uuid
import os
import logging
from datetime import datetime, timezone
from kafka import KafkaProducer

#logging to see simulator generation
logging.basicConfig(
    level = logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
loggger = logging.getLogger(__name__)

#Kafka simulators

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:29092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "bank.transactions")
BANK_CODE = os.getenv("BANK_CODE", "UNKNOWN")
BANK_NAME = os.getenv("BANK_NAME", "unknown Bank")
SEND_INTERVAL = float(os.getenv("SEND_INTERVAL","2.0"))
FRAUD_RATE = float(os.getenv("SEND_INTERVAL","2.0"))# 5% of transaction are suspicious


MERCHANTS = {
    "grocery":       [("MERCH-001", "Biedronka"),
                      ("MERCH-002", "Lidl"),
                      ("MERCH-003", "Zabka"),
                      ("MERCH-004", "Carrefour"),
                      ("MERCH-005", "Auchan")],
    "fuel":          [("MERCH-010", "Orlen"),
                      ("MERCH-011", "BP"),
                      ("MERCH-012", "Shell")],
    "ecommerce":     [("MERCH-020", "Allegro"),
                      ("MERCH-021", "Amazon"),
                      ("MERCH-022", "Zalando")],
    "entertainment": [("MERCH-030", "Netflix"),
                      ("MERCH-031", "Spotify"),
                      ("MERCH-032", "HBO Max")],
    "transport":     [("MERCH-040", "Uber"),
                      ("MERCH-041", "Bolt"),
                      ("MERCH-042", "PKP Intercity")],
    "restaurant":    [("MERCH-050", "McDonald's"),
                      ("MERCH-051", "KFC"),
                      ("MERCH-052", "Pizza Hut")],
}
# Typical amount ranges per category in PLN
AMOUNT_RANGES = {
    "grocery":       (2.0,  750.0),
    "fuel":          (50.0,  600.0),
    "ecommerce":     (25.0,  2000.0),
    "entertainment": (15.0,  100.0),
    "transport":     (8.0,   50.0),
    "restaurant":    (20.0,  150.0),
}

# Currencies — most PLN but some foreign
CURRENCIES = ["PLN"] * 85 + ["EUR"] * 8 + ["USD"] * 5 + ["GBP"] * 2

# Transaction types
TRANSACTION_TYPES = ["purchase"] * 70 + \
                    ["withdrawal"] * 15 + \
                    ["transfer"] * 10 + \
                    ["subscription"] * 5

# Device types
DEVICE_TYPES = ["card"] * 40 + \
               ["mobile"] * 35 + \
               ["web"] * 20 + \
               ["atm"] * 5


# Legitimate IP ranges
LEGITIMATE_IPS = [
    f"192.168.{random.randint(1,254)}.{random.randint(1,254)}"
    for _ in range(100)
]

# Known fraud IP ranges — Tor exit nodes and suspicious ranges
FRAUD_IPS = [
    "185.220.101.1",
    "185.220.101.2",
    "185.220.101.45",
    "198.96.155.3",
    "23.129.64.100",
]

def generate_normal_transaction(customer_id: str, bank_code:str)->dict:
    #lets generate transactions
    category = random.choice(list(MERCHANTS.keys()))
    merchants_id,merchants_name =random.choice(MERCHANTS[category])

    # Generate amount within normal range for this category
    min_amount, max_amount = AMOUNT_RANGES[category]
    amount = round(random.uniform(min_amount, max_amount), 2)

    return{
        # Unique transaction ID — UUID ensures no duplicates
        "transaction_id":    f"TXN-{bank_code}-{uuid.uuid4().hex[:12].upper()}",
        "customer_id":       customer_id,
        "account_id":        f"ACC-{customer_id}-001",
        "merchant_id":       merchant_id,
        "merchant_name":     merchant_name,
        "merchant_category": category,
        "amount":            str(amount),
        "currency":          random.choice(CURRENCIES),
        "transaction_type":  random.choice(TRANSACTION_TYPES),
        "status":            "completed",
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "bank_code":         bank_code,
        "country":           "PL",
        "device_type":       random.choice(DEVICE_TYPES),
        "ip_address":        random.choice(LEGITIMATE_IPS),
    }


def generate_fraud_transaction(customer_id: str, bank_code: str) -> dict:
    """
    Generate a suspicious transaction
    These should be flagged in the Silver fraud detection layer
    Multiple fraud signals present simultaneously
    """
    # Choose a fraud pattern randomly
    fraud_pattern = random.choice([
        "large_unknown_merchant",   # large amount to unknown merchant
        "foreign_currency",         # unusual currency for Polish customer
        "suspicious_ip",            # known fraud IP address
        "multiple_signals",         # combination of signals
    ])

    base = {
        "transaction_id":    f"TXN-{bank_code}-FRAUD-{uuid.uuid4().hex[:8].upper()}",
        "customer_id":       customer_id,
        "account_id":        f"ACC-{customer_id}-001",
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "bank_code":         bank_code,
        "country":           "PL",
        "status":            "pending",   # fraud often stays pending
    }

    if fraud_pattern == "large_unknown_merchant":
        base.update({
            "merchant_id":       "MERCH-UNKNOWN-001",
            "merchant_name":     "Unknown Merchant",
            "merchant_category": "unknown",
            # Unusually large amount
            "amount":            str(round(random.uniform(5000, 50000), 2)),
            "currency":          "PLN",
            "transaction_type":  "purchase",
            "device_type":       "web",
            "ip_address":        random.choice(LEGITIMATE_IPS),
        })

    elif fraud_pattern == "foreign_currency":
        base.update({
            "merchant_id":       "MERCH-FOREIGN-001",
            "merchant_name":     "Foreign Exchange",
            "merchant_category": "finance",
            "amount":            str(round(random.uniform(1000, 10000), 2)),
            # Unusual currency
            "currency":          random.choice(["RUB", "CNY", "TRY"]),
            "transaction_type":  "transfer",
            "device_type":       "web",
            "ip_address":        random.choice(LEGITIMATE_IPS),
        })

    elif fraud_pattern == "suspicious_ip":
        base.update({
            "merchant_id":       "MERCH-ONLINE-001",
            "merchant_name":     "Online Store",
            "merchant_category": "ecommerce",
            "amount":            str(round(random.uniform(500, 3000), 2)),
            "currency":          "PLN",
            "transaction_type":  "purchase",
            "device_type":       "web",
            # Known fraud IP
            "ip_address":        random.choice(FRAUD_IPS),
        })

    else:  # multiple_signals — worst case
        base.update({
            "merchant_id":       "MERCH-UNKNOWN-999",
            "merchant_name":     "Suspicious Merchant",
            "merchant_category": "unknown",
            # Very large amount
            "amount":            str(round(random.uniform(10000, 100000), 2)),
            # Unusual currency
            "currency":          random.choice(["USD", "EUR"]),
            "transaction_type":  "transfer",
            "device_type":       "web",
            # Fraud IP
            "ip_address":        random.choice(FRAUD_IPS),
        })

    return base


def create_producer() -> KafkaProducer:
    """
    Create Kafka producer with retry logic
    Kafka might not be ready immediately when container starts
    We retry until connection succeeds
    """
    max_retries = 10
    retry_delay = 5  # seconds between retries

    for attempt in range(max_retries):
        try:
            producer = KafkaProducer(
                # Kafka broker address — from environment variable
                bootstrap_servers=[KAFKA_BROKER],
                # Serialize messages as JSON bytes
                # Kafka only understands bytes — not Python dicts
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                # Key serializer — we use customer_id as message key
                # Kafka uses key to determine which partition
                # Same customer always goes to same partition
                # This preserves transaction ordering per customer
                key_serializer=lambda k: k.encode("utf-8"),
                # Wait for all replicas to confirm receipt
                # 'all' = most durable — no message loss
                acks="all",
                # Retry failed sends up to 3 times
                retries=3,
            )
            logger.info(f"Connected to Kafka at {KAFKA_BROKER}")
            return producer

        except Exception as e:
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries} — "
                f"Kafka not ready: {e}"
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

    raise RuntimeError(f"Could not connect to Kafka after {max_retries} attempts")



def run_simulator():
    """
    Main simulation loop
    Generates and sends transactions continuously
    """
    logger.info(f"Starting {BANK_NAME} ({BANK_CODE}) simulator")
    logger.info(f"Kafka topic:    {KAFKA_TOPIC}")
    logger.info(f"Send interval:  {SEND_INTERVAL}s")
    logger.info(f"Fraud rate:     {FRAUD_RATE * 100:.0f}%")

    # Create Kafka producer — retries until Kafka is ready
    producer = create_producer()

    # Generate a pool of fake customers for this bank
    # Each bank has 50 customers who transact regularly
    customers = [f"CUST-{BANK_CODE}-{i:03d}" for i in range(1, 51)]

    message_count = 0

    while True:
        try:
            # Pick a random customer
            customer_id = random.choice(customers)

            # Decide if this is a fraud transaction
            # based on the configured fraud rate
            if random.random() < FRAUD_RATE:
                transaction = generate_fraud_transaction(
                    customer_id, BANK_CODE
                )
                logger.warning(
                    f"FRAUD transaction generated: "
                    f"{transaction['transaction_id']} — "
                    f"{transaction['amount']} {transaction['currency']}"
                )
            else:
                transaction = generate_normal_transaction(
                    customer_id, BANK_CODE
                )

            # Send to Kafka
            # key=customer_id ensures all transactions for one customer
            # go to the same Kafka partition — preserves ordering
            future = producer.send(
                KAFKA_TOPIC,
                key=customer_id,
                value=transaction
            )

            # Wait for confirmation that Kafka received the message
            record_metadata = future.get(timeout=10)

            message_count += 1

            # Log every 10th message to show progress
            if message_count % 10 == 0:
                logger.info(
                    f"{BANK_NAME} sent {message_count} transactions — "
                    f"latest: {transaction['transaction_id']} — "
                    f"partition: {record_metadata.partition} — "
                    f"offset: {record_metadata.offset}"
                )

            # Wait before sending next transaction
            time.sleep(SEND_INTERVAL)

        except KeyboardInterrupt:
            logger.info(f"{BANK_NAME} simulator stopped")
            break

        except Exception as e:
            logger.error(f"Error sending transaction: {e}")
            time.sleep(5)  # wait before retrying

    # Flush any remaining messages before exiting
    producer.flush()
    producer.close()
    logger.info(f"{BANK_NAME} simulator finished — sent {message_count} transactions")


if __name__ == "__main__":
    run_simulator()