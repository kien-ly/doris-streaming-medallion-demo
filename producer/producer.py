import json
import os
import random
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.schema_registry import Schema, SchemaRegistryClient
from faker import Faker
from fastavro import parse_schema
from fastavro.validation import validate as avro_validate


fake = Faker()
RUNNING = True
EVENT_TYPES = (
    "page_view",
    "add_to_cart",
    "checkout_started",
    "order_created",
    "order_paid",
    "order_cancelled",
)
PAYMENT_METHODS = ("card", "paypal", "bank_transfer", "cash_on_delivery")
DEVICES = ("web", "ios", "android")
SOURCES = ("direct", "email", "ads", "organic")
STATUSES = {
    "page_view": "viewed",
    "add_to_cart": "carted",
    "checkout_started": "checkout_started",
    "order_created": "created",
    "order_paid": "paid",
    "order_cancelled": "cancelled",
}
EVENT_SCHEMA = """
{
  "type": "record",
  "name": "ecommerce_event",
  "namespace": "demo.streaming",
  "fields": [
    {"name": "schema_id", "type": "int"},
    {"name": "schema_version", "type": "int"},
    {"name": "event_id", "type": "string"},
    {
      "name": "event_type",
      "type": {
        "type": "enum",
        "name": "event_type_enum",
        "symbols": [
          "page_view",
          "add_to_cart",
          "checkout_started",
          "order_created",
          "order_paid",
          "order_cancelled"
        ]
      }
    },
    {"name": "event_time", "type": "string"},
    {"name": "user_id", "type": "string"},
    {"name": "session_id", "type": "string"},
    {"name": "order_id", "type": ["null", "string"], "default": null},
    {"name": "product_id", "type": ["null", "string"], "default": null},
    {"name": "quantity", "type": ["null", "int"], "default": null},
    {"name": "price", "type": ["null", "double"], "default": null},
    {"name": "currency", "type": "string"},
    {
      "name": "status",
      "type": {
        "type": "enum",
        "name": "status_enum",
        "symbols": ["viewed", "carted", "checkout_started", "created", "paid", "cancelled"]
      }
    },
    {"name": "payment_method", "type": "string"},
    {"name": "device", "type": "string"},
    {"name": "source", "type": "string"},
    {"name": "ingested_at", "type": "string"},
    {"name": "campaign_id", "type": ["null", "string"], "default": null},
    {"name": "voucher_code", "type": ["null", "string"], "default": null},
    {"name": "shipping_city", "type": ["null", "string"], "default": null},
    {"name": "raw_payload", "type": "string"}
  ]
}
"""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def build_event(force_duplicate: bool = False, previous_ids: list[str] | None = None) -> dict:
    event_type = random.choice(EVENT_TYPES)
    event_time = now_utc() - timedelta(seconds=random.randint(0, 30))
    order_id = f"ord_{uuid.uuid4().hex[:12]}" if event_type != "page_view" else None
    product_id = f"sku_{random.randint(1000, 9999)}" if event_type != "page_view" else None
    quantity = random.randint(1, 5) if event_type in {"add_to_cart", "order_created", "order_paid", "order_cancelled"} else None
    price = round(random.uniform(10, 500), 2) if event_type in {"add_to_cart", "order_created", "order_paid", "order_cancelled"} else None
    event_id = random.choice(previous_ids) if force_duplicate and previous_ids else f"evt_{uuid.uuid4().hex}"

    event = {
        "event_id": event_id,
        "event_type": event_type,
        "event_time": isoformat(event_time),
        "user_id": f"user_{random.randint(1, 500)}",
        "session_id": f"sess_{uuid.uuid4().hex[:12]}",
        "order_id": order_id,
        "product_id": product_id,
        "quantity": quantity,
        "price": price,
        "currency": "USD",
        "status": STATUSES[event_type],
        "payment_method": random.choice(PAYMENT_METHODS),
        "device": random.choice(DEVICES),
        "source": random.choice(SOURCES),
        "ingested_at": isoformat(now_utc()),
    }
    return event


def maybe_add_optional_fields(event: dict, enabled: bool) -> None:
    if not enabled:
        return

    if random.random() < 0.4:
        event["campaign_id"] = f"cmp_{uuid.uuid4().hex[:8]}"
    if random.random() < 0.3:
        event["voucher_code"] = random.choice(["WELCOME10", "SPRING15", "VIP20"])
    if random.random() < 0.3:
        event["shipping_city"] = fake.city()


def delivery_report(err, msg) -> None:
    if err is not None:
        print(f"delivery failed: {err}", file=sys.stderr)


def ensure_topic(brokers: str, topic: str) -> None:
    admin = AdminClient({"bootstrap.servers": brokers})
    metadata = admin.list_topics(timeout=10)
    if topic in metadata.topics:
        return

    futures = admin.create_topics(
        [
            NewTopic(
                topic=topic,
                num_partitions=1,
                replication_factor=1,
                config={
                    "retention.bytes": str(50 * 1024 * 1024),
                    "retention.ms": str(6 * 60 * 60 * 1000),
                },
            )
        ]
    )
    futures[topic].result()


def handle_signal(signum, frame) -> None:
    del signum, frame
    global RUNNING
    RUNNING = False


def ensure_schema_registry(schema_registry_url: str, topic: str) -> tuple[int, int]:
    schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})
    subject = f"{topic}-value"
    schema_id = schema_registry_client.register_schema(subject, Schema(EVENT_SCHEMA, "AVRO"))
    latest = schema_registry_client.get_latest_version(subject)
    return schema_id, latest.version


def main() -> int:
    brokers = os.getenv("REDPANDA_BROKERS", "redpanda:9092")
    topic = os.getenv("REDPANDA_TOPIC", "ecommerce_events")
    schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL", "http://redpanda:8081")
    events_per_second = max(float(os.getenv("EVENTS_PER_SECOND", "2")), 0.1)
    schema_evolution = env_bool("ENABLE_SCHEMA_EVOLUTION", False)
    duplicate_mode = env_bool("ENABLE_DUPLICATE_MODE", False)
    delay_seconds = 1.0 / events_per_second

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    ensure_topic(brokers, topic)

    producer = Producer({"bootstrap.servers": brokers, "client.id": "ecommerce-producer"})
    schema_id, schema_version = ensure_schema_registry(schema_registry_url, topic)
    parsed_schema = parse_schema(json.loads(EVENT_SCHEMA))
    emitted_ids: list[str] = []

    while RUNNING:
        event = build_event(force_duplicate=duplicate_mode and random.random() < 0.1, previous_ids=emitted_ids)
        maybe_add_optional_fields(event, schema_evolution)
        event["schema_id"] = schema_id
        event["schema_version"] = schema_version
        event["raw_payload"] = json.dumps(event, separators=(",", ":"), sort_keys=True)
        avro_validate(event, parsed_schema, raise_errors=True)

        producer.produce(
            topic=topic,
            key=event["event_id"],
            value=json.dumps(event, separators=(",", ":"), sort_keys=True),
            callback=delivery_report,
        )
        producer.poll(0)

        emitted_ids.append(event["event_id"])
        if len(emitted_ids) > 1000:
            emitted_ids = emitted_ids[-1000:]

        time.sleep(delay_seconds)

    producer.flush(10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
