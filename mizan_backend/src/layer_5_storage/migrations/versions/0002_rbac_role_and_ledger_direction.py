"""Add `users.role` and `transaction_ledger.direction`.

Revision ID: 0002_rbac_role_and_ledger_direction
Revises: 0001_initial_schema
Created: 2026-08-09

The two columns RBAC and the Audit API introduced. Both are applied to
tables that already hold rows, so each needs an answer for what those
existing rows should say:

* **`users.role`** is `NOT NULL`, so it is added with a server default
  of `'user'` — every account that predates roles is an ordinary user,
  which is the safe reading. The default is then dropped, because the
  application supplies the value on insert and leaving a default behind
  would show up forever as a difference between the models and the
  database.

* **`transaction_ledger.direction`** is left nullable on purpose. The
  ledger is append-only and the ORM actively rejects an `UPDATE`, so
  historical entries genuinely cannot be backfilled — and for a
  transfer the direction is not recoverable anyway, since both legs
  were written with the same type and the same positive amount. The
  audit service reports such entries as *unverifiable* rather than
  guessing at them, so this migration must not invent values either.
  Rewriting ledger history to make an audit reconcile is precisely what
  an append-only ledger exists to prevent.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_rbac_role_and_ledger_direction"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Mirrors `EntryDirection` in
#: `layer_5_storage/models/transaction_ledger_model.py`. Spelled out
#: here rather than imported: a migration must keep describing the
#: schema it created even after the model moves on, so importing the
#: live enum would silently rewrite history the next time someone adds
#: a value.
_ENTRY_DIRECTION = sa.Enum(
    "CREDIT", "DEBIT", name="entry_direction", native_enum=False
)

_DEFAULT_ROLE = "user"


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "role",
                sa.String(length=32),
                nullable=False,
                server_default=_DEFAULT_ROLE,
            )
        )
        batch_op.create_index(batch_op.f("ix_users_role"), ["role"], unique=False)

    # Existing rows now carry 'user'; drop the default so the database
    # matches the model, which declares none. Left in place, it would
    # register as permanent drift the next `--autogenerate` run.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("role", server_default=None)

    with op.batch_alter_table("transaction_ledger", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("direction", _ENTRY_DIRECTION, nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("transaction_ledger", schema=None) as batch_op:
        batch_op.drop_column("direction")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_role"))
        batch_op.drop_column("role")
