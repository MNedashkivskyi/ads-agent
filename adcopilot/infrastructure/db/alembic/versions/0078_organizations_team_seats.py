"""Organizations, memberships, invitations + personal-org backfill — T3.4.

Creates the team-seats data model and migrates every existing user to a
personal organization with an OWNER membership. The backfill is idempotent
(guarded by NOT EXISTS) and reversible (downgrade drops the tables). Account
ownership is intentionally NOT changed here — accounts stay owned by user_id;
linking accounts to organizations and rewiring access resolution is a separate,
carefully staged step (see T6.1).

Revision ID: 0078
Revises: 0077
Create Date: 2026-06-16
"""

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from alembic import op  # noqa: E402
from sqlalchemy.dialects.postgresql import UUID  # noqa: E402


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("owner_user_id", sa.String(length=255), nullable=False),
        sa.Column("is_personal", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_organizations_owner_user_id", "organizations", ["owner_user_id"])

    op.create_table(
        "memberships",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="MEMBER"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
    )
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "organization_invitations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="MEMBER"),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("organization_id", "email", name="uq_org_invites_org_email"),
        sa.UniqueConstraint("token", name="uq_org_invites_token"),
    )
    op.create_index(
        "ix_organization_invitations_organization_id",
        "organization_invitations",
        ["organization_id"],
    )
    op.create_index("ix_organization_invitations_email", "organization_invitations", ["email"])
    op.create_index("ix_organization_invitations_token", "organization_invitations", ["token"])

    # --- idempotent backfill: one personal org + OWNER membership per user ---
    op.execute(
        sa.text(
            """
            INSERT INTO organizations (id, name, owner_user_id, is_personal, created_at)
            SELECT gen_random_uuid(), '', u.id::text, true, now()
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM organizations o
                WHERE o.owner_user_id = u.id::text AND o.is_personal = true
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO memberships (id, organization_id, user_id, role, created_at)
            SELECT gen_random_uuid(), o.id, o.owner_user_id, 'OWNER', now()
            FROM organizations o
            WHERE o.is_personal = true
            AND NOT EXISTS (
                SELECT 1 FROM memberships m
                WHERE m.organization_id = o.id AND m.user_id = o.owner_user_id
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("organization_invitations")
    op.drop_table("memberships")
    op.drop_table("organizations")
