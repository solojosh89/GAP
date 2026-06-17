"""A tiny, database-free stand-in for the real migration bug, so the GAP skeleton
can actually RUN a proof. Same class of bug as the E-school
migrate_sqlite_to_postgres.py 'rows migrated' count.

migrate() copies (key, value) rows into `destination`. Keys that already exist
are skipped (like ON CONFLICT DO NOTHING) — but the returned count adds every row
it looked at, not just the ones it inserted.
"""


def migrate(rows, destination):
    migrated = 0
    for key, value in rows:
        if key not in destination:      # ON CONFLICT DO NOTHING: skip existing
            destination[key] = value
        migrated += 1                   # BUG: counts attempts, not real inserts
    return migrated
