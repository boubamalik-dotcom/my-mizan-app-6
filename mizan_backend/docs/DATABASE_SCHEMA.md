# Database schema and migrations

The schema is defined twice, on purpose, and the two must agree:

- **The ORM models** (`src/layer_5_storage/models/`) are what the
  application reads and writes through.
- **The Alembic migrations** (`src/layer_5_storage/migrations/versions/`)
  are what actually shapes a real database.

`tests/layer_5_storage_tests/test_migrations.py::test_migrations_match_the_models`
builds a database from the migrations alone and diffs it against the
models. If they disagree, that test fails — which is the only reason
it is safe to have both.

## Running migrations

From `mizan_backend/`:

```bash
alembic upgrade head          # apply everything pending
alembic current               # which revision this database is on
alembic history --verbose     # the full chain
alembic downgrade -1          # undo the most recent revision
```

The database URL comes from `DATABASE_URL` (via `config.Settings`), the
same setting the application uses, so the two cannot be pointed at
different databases by updating one and forgetting the other. Override
it for a one-off run with `-x url=...`.

To review the SQL before it touches a production database rather than
letting Alembic apply it:

```bash
alembic upgrade head --sql
```

## Why not `create_all`?

`init_models()` calls `Base.metadata.create_all`, which creates tables
that do not exist and **silently skips every table that does**. It
cannot add a column, change a type, or drop anything. Run it against a
database on an older schema and it does nothing, reports success, and
leaves you to discover the missing column when a query fails at
runtime — which is exactly what happened when RBAC added `users.role`.

It is therefore off by default. Set `AUTO_CREATE_SCHEMA=true` only for
a disposable local database where running migrations first is friction
rather than safety.

## Onboarding a database that predates Alembic

Revision `0001_initial_schema` is a **baseline**: it describes the
schema as it stood before Alembic existed, which is what already-
deployed databases contain. Such a database must not be asked to create
tables it already has, so tell Alembic where it already is, then
upgrade:

```bash
alembic stamp 0001_initial_schema   # "this database is already here"
alembic upgrade head                # apply 0002 onwards
```

A brand-new database skips the stamp and just runs `alembic upgrade
head`.

## Adding a migration

1. Change the model.
2. `alembic revision --autogenerate -m "what changed"`.
3. **Read what it produced.** Autogenerate is a first draft: it does not
   know that a new `NOT NULL` column needs a `server_default` or a
   backfill for existing rows, and it will happily generate a migration
   that fails the moment it meets a table with data in it.
4. Check `downgrade()` is genuinely the inverse. A migration you cannot
   reverse is one you cannot safely deploy.
5. Run the tests. The drift test will tell you if the model and the
   migration still disagree.

Two constraints worth knowing before writing one by hand:

- **Use `op.batch_alter_table` for anything that alters or drops a
  column.** SQLite cannot do either in place; batch mode recreates the
  table and copies the rows. Development runs on SQLite and production
  on PostgreSQL, so skipping this produces a migration that passes in
  one and fails in the other.
- **Do not import live enums or models into a migration.** A migration
  must keep describing the schema it created even after the model moves
  on; importing the current definition silently rewrites history the
  next time someone edits it. Spell the values out (see `0002`).

## The current chain

| Revision | What it does |
| --- | --- |
| `0001_initial_schema` | Baseline: users, wallets, the append-only transaction ledger, and chat threads/participants/messages. |
| `0002_rbac_role_and_ledger_direction` | Adds `users.role` (RBAC) and `transaction_ledger.direction` (audit reconciliation). |

### A note on `transaction_ledger.direction`

It is nullable, and `0002` deliberately does **not** backfill it.

The ledger is append-only — the ORM rejects an `UPDATE` outright — so
historical entries cannot be rewritten. For a transfer the direction is
not recoverable anyway: both legs were written with the same type and
the same positive amount, which is the defect that motivated the column
in the first place. The audit service reports such entries as
*unverifiable* and refuses to call a wallet balanced while any remain.
A migration that guessed would put a fabricated number in an audit
report, which is worse than admitting the gap.
