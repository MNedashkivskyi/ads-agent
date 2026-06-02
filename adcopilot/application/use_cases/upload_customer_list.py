"""Upload a customer email list to Google Ads as a Customer Match audience."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import structlog

from adcopilot.infrastructure.hashing import hash_email

logger = structlog.get_logger(__name__)


def parse_and_hash_csv(csv_bytes: bytes, email_column: str = "email") -> list[str]:
    """Parse CSV content, extract email column, return SHA-256 hashes."""
    text = csv_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    # Try to find the email column case-insensitively
    fieldnames = reader.fieldnames or []
    col_map = {f.strip().lower(): f for f in fieldnames}
    col = col_map.get(email_column.lower()) or col_map.get("e-mail") or col_map.get("mail")
    if not col:
        raise ValueError(
            f"Nie znaleziono kolumny '{email_column}' w pliku CSV. "
            f"Dostępne kolumny: {', '.join(fieldnames)}"
        )

    hashes: list[str] = []
    for row in reader:
        hashed = hash_email(row.get(col))
        if hashed is not None:
            hashes.append(hashed)

    return hashes


@dataclass
class UploadCustomerListResult:
    user_list_resource_name: str
    uploaded_count: int
    list_name: str


async def upload_customer_list(
    refresh_token: str,
    customer_id: str,
    list_name: str,
    csv_bytes: bytes,
    mutations_adapter,
    email_column: str = "email",
) -> UploadCustomerListResult:
    hashed = parse_and_hash_csv(csv_bytes, email_column)
    if not hashed:
        raise ValueError("Plik CSV nie zawiera prawidłowych adresów e-mail.")

    logger.info("upload_customer_list", customer_id=customer_id, count=len(hashed))
    rn = await mutations_adapter.create_customer_match_user_list(
        refresh_token=refresh_token,
        customer_id=customer_id,
        list_name=list_name,
        hashed_emails=hashed,
    )
    return UploadCustomerListResult(
        user_list_resource_name=rn,
        uploaded_count=len(hashed),
        list_name=list_name,
    )
