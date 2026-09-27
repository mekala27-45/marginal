"""experiments, results, plans and the audit log

Revision ID: 0001
Revises:
Create Date: 2026-09-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("plan_hash", sa.String(), nullable=False),
        sa.Column("design", sa.JSON(), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_experiments_experiment_id", "experiments", ["experiment_id"], unique=True)
    op.create_index("ix_experiments_plan_hash", "experiments", ["plan_hash"])
    op.create_table(
        "experiment_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("experiment_id", sa.String(), sa.ForeignKey("experiments.experiment_id"), nullable=False),
        sa.Column("plan_hash", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("incremental_revenue", sa.Float(), nullable=False),
        sa.Column("standard_error", sa.Float(), nullable=False),
        sa.Column("lower", sa.Float(), nullable=False),
        sa.Column("upper", sa.Float(), nullable=False),
        sa.Column("level", sa.Float(), nullable=False),
        sa.Column("geos", sa.JSON(), nullable=True),
        sa.Column("start_week", sa.Integer(), nullable=False),
        sa.Column("end_week", sa.Integer(), nullable=False),
        sa.Column("truth", sa.Float(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_experiment_results_experiment_id", "experiment_results", ["experiment_id"])
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("backend", sa.String(), nullable=False),
        sa.Column("spec_hash", sa.String(), nullable=False),
        sa.Column("inputs_hash", sa.String(), nullable=False),
        sa.Column("total_budget", sa.Float(), nullable=False),
        sa.Column("allocation", sa.JSON(), nullable=True),
        sa.Column("expected_profit", sa.Float(), nullable=False),
        sa.Column("profit_lower", sa.Float(), nullable=False),
        sa.Column("profit_upper", sa.Float(), nullable=False),
        sa.Column("level", sa.Float(), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=True),
        sa.Column("degenerate", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_plans_plan_id", "plans", ["plan_id"], unique=True)
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
    )
    op.create_index("ix_audit_log_at", "audit_log", ["at"])


def downgrade() -> None:
    for name in ("audit_log", "plans", "experiment_results", "experiments"):
        op.drop_table(name)
