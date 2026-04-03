import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error
import pyarrow as pa
import pymysql
from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError, NoSuchTableError, TableAlreadyExistsError


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)


ARROW_SCHEMA = pa.schema(
    [
        ("event_id", pa.large_string()),
        ("event_type", pa.large_string()),
        ("event_time", pa.timestamp("us")),
        ("user_id", pa.large_string()),
        ("session_id", pa.large_string()),
        ("order_id", pa.large_string()),
        ("product_id", pa.large_string()),
        ("quantity", pa.int32()),
        ("price", pa.float64()),
        ("currency", pa.large_string()),
        ("status", pa.large_string()),
        ("payment_method", pa.large_string()),
        ("device", pa.large_string()),
        ("source", pa.large_string()),
        ("ingested_at", pa.timestamp("us")),
        ("raw_payload", pa.large_string()),
    ]
)


@dataclass
class Settings:
    doris_host: str = os.getenv("DORIS_HOST", "localhost")
    doris_port: int = int(os.getenv("DORIS_PORT", "9030"))
    doris_user: str = os.getenv("DORIS_USER", "root")
    doris_password: str = os.getenv("DORIS_PASSWORD", "")
    checkpoint_job_name: str = os.getenv("CHECKPOINT_JOB_NAME", "optional_iceberg_sink")
    source_table: str = os.getenv("SOURCE_TABLE", "dwh.bronze_events")
    target_table: str = os.getenv("TARGET_TABLE", "lakehouse.raw_events")
    window_minutes: int = int(os.getenv("WINDOW_MINUTES", "5"))
    iceberg_enabled: bool = os.getenv("ICEBERG_ENABLED", "false").lower() in {"1", "true", "yes"}
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "lakehouse")
    iceberg_catalog_name: str = os.getenv("ICEBERG_CATALOG_NAME", "demo_catalog")
    iceberg_catalog_uri: str = os.getenv(
        "ICEBERG_CATALOG_URI",
        "sqlite:////workspace/jobs/.iceberg/demo_catalog.db",
    )
    iceberg_warehouse: str = os.getenv("ICEBERG_WAREHOUSE", "s3://lakehouse/warehouse")
    iceberg_s3_region: str = os.getenv("ICEBERG_S3_REGION", "us-east-1")

    @property
    def target_namespace(self) -> str:
        namespace, _, _ = self.target_table.partition(".")
        return namespace

    @property
    def target_table_name(self) -> str:
        _, _, table_name = self.target_table.partition(".")
        return table_name

    @property
    def target_identifier(self) -> tuple[str, str]:
        return (self.target_namespace, self.target_table_name)

    @property
    def target_location(self) -> str:
        warehouse = self.iceberg_warehouse.rstrip("/")
        return f"{warehouse}/{self.target_namespace}/{self.target_table_name}"


def get_connection(settings: Settings):
    return pymysql.connect(
        host=settings.doris_host,
        port=settings.doris_port,
        user=settings.doris_user,
        password=settings.doris_password,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def fetch_checkpoint(cursor, settings: Settings):
    cursor.execute(
        """
        SELECT last_success_end
        FROM meta.batch_job_checkpoint
        WHERE job_name = %s AND source_table = %s AND target_table = %s
        """,
        (settings.checkpoint_job_name, settings.source_table, settings.target_table),
    )
    return cursor.fetchone()


def compute_window(last_success_end: datetime | None, window_minutes: int):
    if last_success_end is None:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        return now - timedelta(minutes=window_minutes), now
    return last_success_end, last_success_end + timedelta(minutes=window_minutes)


def resolve_initial_window(cursor, settings: Settings) -> tuple[datetime, datetime]:
    cursor.execute(f"SELECT MAX(ingested_at) AS max_ingested_at FROM {settings.source_table}")
    result = cursor.fetchone()
    max_ingested_at = result["max_ingested_at"] if result else None
    if max_ingested_at is None:
        return compute_window(None, settings.window_minutes)

    window_end = max_ingested_at.replace(second=0, microsecond=0) + timedelta(minutes=1)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    return window_end - timedelta(minutes=settings.window_minutes), window_end


def ensure_catalog_storage(settings: Settings) -> None:
    catalog_uri = settings.iceberg_catalog_uri
    if catalog_uri.startswith("sqlite:///"):
        sqlite_path = catalog_uri.removeprefix("sqlite:///")
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)


def ensure_bucket(settings: Settings) -> None:
    endpoint = settings.minio_endpoint.removeprefix("http://").removeprefix("https://")
    minio_client = Minio(
        endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_endpoint.startswith("https://"),
        region=settings.iceberg_s3_region,
    )

    if minio_client.bucket_exists(settings.minio_bucket):
        LOGGER.info("MinIO bucket %s already exists", settings.minio_bucket)
        return

    try:
        minio_client.make_bucket(settings.minio_bucket)
        LOGGER.info("Created MinIO bucket %s", settings.minio_bucket)
    except S3Error:
        if not minio_client.bucket_exists(settings.minio_bucket):
            raise
        LOGGER.info("MinIO bucket %s already exists", settings.minio_bucket)


def load_iceberg_catalog(settings: Settings):
    ensure_catalog_storage(settings)
    return load_catalog(
        settings.iceberg_catalog_name,
        type="sql",
        uri=settings.iceberg_catalog_uri,
        warehouse=settings.iceberg_warehouse,
        **{
            "s3.endpoint": settings.minio_endpoint,
            "s3.access-key-id": settings.minio_access_key,
            "s3.secret-access-key": settings.minio_secret_key,
            "s3.region": settings.iceberg_s3_region,
            "s3.path-style-access": "true",
        },
    )


def ensure_table(catalog, settings: Settings):
    namespace = (settings.target_namespace,)
    try:
        catalog.create_namespace(namespace)
        LOGGER.info("Created Iceberg namespace %s", settings.target_namespace)
    except NamespaceAlreadyExistsError:
        pass

    try:
        table = catalog.create_table(
            settings.target_identifier,
            schema=ARROW_SCHEMA,
            location=settings.target_location,
            properties={
                "format-version": "2",
                "write.parquet.compression-codec": "zstd",
            },
        )
        LOGGER.info("Created Iceberg table %s at %s", settings.target_table, settings.target_location)
        return table
    except TableAlreadyExistsError:
        table = catalog.load_table(settings.target_identifier)
        current_schema = table.schema().as_arrow()
        if current_schema != ARROW_SCHEMA:
            return recreate_table(catalog, settings)
        return table


def fetch_source_rows(cursor, settings: Settings, start_ts: datetime, end_ts: datetime) -> list[dict]:
    cursor.execute(
        f"""
        SELECT
            event_id,
            event_type,
            event_time,
            user_id,
            session_id,
            order_id,
            product_id,
            quantity,
            price,
            currency,
            status,
            payment_method,
            device,
            source,
            ingested_at,
            raw_payload
        FROM {settings.source_table}
        WHERE ingested_at >= %s AND ingested_at < %s
        ORDER BY ingested_at ASC, event_id ASC
        """,
        (start_ts, end_ts),
    )
    return list(cursor.fetchall())


def normalize_row(row: dict) -> dict:
    normalized = dict(row)
    price = normalized.get("price")
    if isinstance(price, Decimal):
        normalized["price"] = float(price)
    elif price is not None and not isinstance(price, float):
        normalized["price"] = float(price)
    return normalized


def build_arrow_table(rows: list[dict]) -> pa.Table:
    normalized_rows = [normalize_row(row) for row in rows]
    if not normalized_rows:
        return ARROW_SCHEMA.empty_table()
    return pa.Table.from_pylist(normalized_rows, schema=ARROW_SCHEMA)


def count_iceberg_rows(table) -> int:
    try:
        return table.scan().to_arrow().num_rows
    except NoSuchTableError:
        return 0


def recreate_table(catalog, settings: Settings):
    try:
        catalog.drop_table(settings.target_identifier)
        LOGGER.warning("Dropped existing Iceberg table %s due to schema mismatch", settings.target_table)
    except NoSuchTableError:
        pass

    table = catalog.create_table(
        settings.target_identifier,
        schema=ARROW_SCHEMA,
        location=settings.target_location,
        properties={
            "format-version": "2",
            "write.parquet.compression-codec": "zstd",
        },
    )
    LOGGER.info("Recreated Iceberg table %s at %s", settings.target_table, settings.target_location)
    return table


def update_checkpoint(cursor, settings: Settings, start_ts: datetime, end_ts: datetime, row_count: int, status: str):
    checkpoint_key = (
        settings.checkpoint_job_name,
        settings.source_table,
        settings.target_table,
    )
    cursor.execute(
        """
        UPDATE meta.batch_job_checkpoint
        SET
            last_success_start = %s,
            last_success_end = %s,
            status = %s,
            row_count = %s,
            updated_at = NOW()
        WHERE job_name = %s AND source_table = %s AND target_table = %s
        """,
        (start_ts, end_ts, status, row_count, *checkpoint_key),
    )
    if cursor.rowcount > 0:
        return

    cursor.execute(
        """
        INSERT INTO meta.batch_job_checkpoint (
            job_name, source_table, target_table, last_success_start, last_success_end, status, row_count, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (*checkpoint_key, start_ts, end_ts, status, row_count),
    )


def main() -> int:
    settings = Settings()
    if not settings.iceberg_enabled:
        LOGGER.info("Optional Iceberg sink is disabled. Set ICEBERG_ENABLED=true to enable this path.")
        return 0

    parsed_warehouse = urlparse(settings.iceberg_warehouse)
    if parsed_warehouse.scheme != "s3":
        raise ValueError(f"Unsupported ICEBERG_WAREHOUSE value: {settings.iceberg_warehouse}")
    if parsed_warehouse.netloc != settings.minio_bucket:
        raise ValueError(
            "ICEBERG_WAREHOUSE bucket must match MINIO_BUCKET for the local demo "
            f"({parsed_warehouse.netloc} != {settings.minio_bucket})"
        )

    connection = get_connection(settings)
    try:
        ensure_bucket(settings)
        catalog = load_iceberg_catalog(settings)
        table = ensure_table(catalog, settings)

        with connection.cursor() as cursor:
            checkpoint = fetch_checkpoint(cursor, settings)
            last_success_end = checkpoint["last_success_end"] if checkpoint else None
            if last_success_end is None:
                window_start, window_end = resolve_initial_window(cursor, settings)
            else:
                window_start, window_end = compute_window(last_success_end, settings.window_minutes)
            rows = fetch_source_rows(cursor, settings, window_start, window_end)
            row_count = len(rows)

            LOGGER.info(
                "Selected window %s to %s from %s with %s rows",
                window_start,
                window_end,
                settings.source_table,
                row_count,
            )

            if row_count > 0:
                arrow_table = build_arrow_table(rows)
                table.append(arrow_table)
                table = catalog.load_table(settings.target_identifier)
                LOGGER.info(
                    "Appended %s rows into %s. Current Iceberg row count: %s",
                    row_count,
                    settings.target_table,
                    count_iceberg_rows(table),
                )
            else:
                LOGGER.info("No rows found in the selected window. Table metadata remains unchanged.")

            update_checkpoint(cursor, settings, window_start, window_end, row_count, "SUCCESS")
            connection.commit()
            LOGGER.info("Checkpoint advanced for %s to %s", settings.checkpoint_job_name, window_end)
        return 0
    except Exception:
        connection.rollback()
        LOGGER.exception("Optional Iceberg sink failed. Checkpoint was not advanced.")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
