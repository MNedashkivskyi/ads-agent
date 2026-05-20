"""0049 — implementation partners and requests tables.

Revision ID: 0049
Revises: 0048
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

_SEED_PARTNERS = [
    ("Piotr Kowalski GTM", "piotr@gtmexpert.pl", "https://gtmexpert.pl", "Warszawa", "Mazowieckie",
     ["shopify", "woocommerce", "wordpress", "shoper", "custom"], 120, 48, 4.8, 34),
    ("Anna Nowak Digital", "anna@digitalwdrożenia.pl", None, "Kraków", "Małopolskie",
     ["woocommerce", "wordpress", "shoper"], 100, 72, 4.7, 21),
    ("WebTag Poznań", "kontakt@webtag.pl", "https://webtag.pl", "Poznań", "Wielkopolskie",
     ["shopify", "custom", "wordpress"], 150, 24, 4.9, 58),
    ("GTM Wrocław", "info@gtmwroclaw.pl", None, "Wrocław", "Dolnośląskie",
     ["woocommerce", "shoper", "custom"], 130, 48, 4.6, 15),
    ("Marcin Ślązak Consulting", "marcin@slazak.dev", "https://slazak.dev", "Katowice", "Śląskie",
     ["wordpress", "woocommerce", "shopify", "shoper", "custom"], 100, 36, 4.9, 42),
]


def upgrade() -> None:
    op.create_table(
        "implementation_partners",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.VARCHAR(255), nullable=False),
        sa.Column("email", sa.VARCHAR(255), nullable=False),
        sa.Column("website", sa.VARCHAR(512), nullable=True),
        sa.Column("city", sa.VARCHAR(100), nullable=False),
        sa.Column("voivodeship", sa.VARCHAR(100), nullable=False),
        sa.Column("platforms_supported", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("fixed_price_pln", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("avg_turnaround_hours", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("rating", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("completed_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_implementation_partners_city", "implementation_partners", ["city"])
    op.create_index("ix_implementation_partners_active", "implementation_partners", ["is_active"])

    op.create_table(
        "implementation_requests",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("client_id", sa.VARCHAR(36), nullable=False),
        sa.Column("partner_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.VARCHAR(32), nullable=False, server_default="requested"),
        sa.Column("platform", sa.VARCHAR(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_implementation_requests_client_id", "implementation_requests", ["client_id"])
    op.create_index("ix_implementation_requests_status", "implementation_requests", ["status"])

    # Add marketplace_enabled config flag to existing config if table exists.
    # Use a savepoint so that a failure (e.g. missing config table) does not
    # abort the surrounding Alembic transaction.
    conn = op.get_bind()
    conn.execute(sa.text("SAVEPOINT config_insert"))
    try:
        op.execute(
            "INSERT INTO config (key, value) VALUES ('marketplace_enabled', 'true') "
            "ON CONFLICT (key) DO NOTHING"
        )
        conn.execute(sa.text("RELEASE SAVEPOINT config_insert"))
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT config_insert"))

    # Seed placeholder partners
    for name, email, website, city, voivodeship, platforms, price, hours, rating, jobs in _SEED_PARTNERS:
        import json as _json
        platforms_json = _json.dumps(platforms)
        op.execute(
            sa.text(
                "INSERT INTO implementation_partners "
                "(name, email, website, city, voivodeship, platforms_supported, "
                "fixed_price_pln, avg_turnaround_hours, rating, completed_jobs, is_active) "
                "VALUES (:name, :email, :website, :city, :voivodeship, CAST(:platforms AS json), "
                ":price, :hours, :rating, :jobs, true)"
            ).bindparams(
                name=name, email=email, website=website, city=city,
                voivodeship=voivodeship, platforms=platforms_json,
                price=price, hours=hours, rating=rating, jobs=jobs,
            )
        )


def downgrade() -> None:
    op.drop_index("ix_implementation_requests_status", "implementation_requests")
    op.drop_index("ix_implementation_requests_client_id", "implementation_requests")
    op.drop_table("implementation_requests")
    op.drop_index("ix_implementation_partners_active", "implementation_partners")
    op.drop_index("ix_implementation_partners_city", "implementation_partners")
    op.drop_table("implementation_partners")
