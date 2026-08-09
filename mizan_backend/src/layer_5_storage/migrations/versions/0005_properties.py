"""Add the `properties` table.

Revision ID: 0005_properties
Revises: 0004_queue_consultation
Created: 2026-08-09

Storage for Oran Real Estate's listings. A new table, so unlike `0002`
there are no existing rows needing a `server_default` or a backfill and
every column can be `NOT NULL` outright.

`price` is `Numeric(18, 2)`, not a float. A listing at 42,000,000 DZD
rendered as `41999999.99999` would look like a defect to a buyer even
though the error is microscopic, and money in this codebase is `Decimal`
everywhere else for the same reason.

The four amenity booleans get one **composite** index rather than four
separate ones. They are always queried together — "a private pool *and*
a high floor" — and a single index in this column order serves any
subset of that conjunction, whereas four independent indexes leave the
planner to combine them.

The amenity columns are `NOT NULL` deliberately. "We do not know whether
this listing has a pool" is not a state a filter could act on: with a
nullable column, `has_private_pool = true` and `has_private_pool = false`
would no longer partition the listings between them, and a buyer
filtering for a pool would silently lose every unknown listing with
nothing to indicate it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0005_properties'
down_revision: Union[str, None] = '0004_queue_consultation'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('properties',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('price', sa.Numeric(precision=18, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('district', sa.String(length=255), nullable=False),
    sa.Column('bedrooms', sa.Integer(), nullable=False),
    sa.Column('bathrooms', sa.Integer(), nullable=False),
    sa.Column('area_sqm', sa.Integer(), nullable=False),
    sa.Column('is_featured', sa.Boolean(), nullable=False),
    sa.Column('has_private_pool', sa.Boolean(), nullable=False),
    sa.Column('is_high_floor', sa.Boolean(), nullable=False),
    sa.Column('has_king_bed', sa.Boolean(), nullable=False),
    sa.Column('is_non_smoking', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('area_sqm > 0', name='ck_property_area_positive'),
    sa.CheckConstraint('bathrooms >= 0', name='ck_property_bathrooms_non_negative'),
    sa.CheckConstraint('bedrooms >= 0', name='ck_property_bedrooms_non_negative'),
    sa.CheckConstraint('price >= 0', name='ck_property_price_non_negative'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('properties', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_properties_is_featured'), ['is_featured'], unique=False)
        batch_op.create_index('ix_property_amenities', ['has_private_pool', 'is_high_floor', 'has_king_bed', 'is_non_smoking'], unique=False)
        batch_op.create_index('ix_property_district', ['district'], unique=False)
        batch_op.create_index('ix_property_featured_price', ['is_featured', 'price'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('properties', schema=None) as batch_op:
        batch_op.drop_index('ix_property_featured_price')
        batch_op.drop_index('ix_property_district')
        batch_op.drop_index('ix_property_amenities')
        batch_op.drop_index(batch_op.f('ix_properties_is_featured'))

    op.drop_table('properties')
