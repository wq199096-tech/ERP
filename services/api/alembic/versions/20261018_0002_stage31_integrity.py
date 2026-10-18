"""Stage 3.1 security, order versioning and durable print linkage.

Revision ID: 20261018_0002
Revises: 20261017_0001
"""

import sqlalchemy as sa
from alembic import op

revision = "20261018_0002"
down_revision = "20261017_0001"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add_missing(table: str, columns: list[sa.Column]) -> None:
    existing = _columns(table)
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    _add_missing("users", [sa.Column("role", sa.String(30), nullable=False, server_default="viewer")])
    _add_missing(
        "orders",
        [
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("package_id", sa.String(80), nullable=False, server_default="legacy-package"),
            sa.Column("address_valid", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("stock_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        ],
    )
    _add_missing(
        "print_jobs",
        [
            sa.Column("order_id", sa.String(36), nullable=True),
            sa.Column("erp_order_no", sa.String(40), nullable=True),
            sa.Column("order_version", sa.Integer(), nullable=True),
            sa.Column("package_id", sa.String(80), nullable=True),
            sa.Column("operation", sa.String(20), nullable=False, server_default="NORMAL"),
            sa.Column("agent_job_id", sa.String(36), nullable=True),
            sa.Column("waybill_no", sa.String(100), nullable=True),
            sa.Column("system_job_id", sa.String(100), nullable=True),
        ],
    )
    _add_missing(
        "order_private_data",
        [
            sa.Column("order_id", sa.String(36), nullable=True),
            sa.Column("receiver_name_encrypted", sa.Text(), nullable=True),
            sa.Column("receiver_phone_encrypted", sa.Text(), nullable=True),
            sa.Column("receiver_address_encrypted", sa.Text(), nullable=True),
        ],
    )


def downgrade() -> None:
    # Deliberately non-destructive: Stage 3.1 may contain encrypted address and print audit data.
    pass
