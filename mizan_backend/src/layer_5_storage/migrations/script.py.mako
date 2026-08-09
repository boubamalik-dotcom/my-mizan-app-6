"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Created: ${create_date}

Review checklist before merging a migration:

* Is `downgrade()` genuinely the inverse of `upgrade()`? A migration
  you cannot reverse is a migration you cannot safely deploy.
* Does it work on an existing table with rows in it, not just an empty
  one? A new `NOT NULL` column needs a `server_default` or a backfill.
* Does it work on both SQLite (development) and PostgreSQL
  (production)? Use `op.batch_alter_table` for anything that alters or
  drops a column.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
