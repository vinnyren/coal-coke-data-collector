import sqlite3
from pathlib import Path

VALID_TABLES = {
    "futures_daily",
    "futures_realtime",
    "spot_basis",
    "position_rank",
    "inventory",
    "index_price",
}


class SqliteStore:
    def __init__(self, db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def init_schema(self, schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    def upsert(self, table, rows, conflict_cols):
        if not rows:
            return 0
        if table not in VALID_TABLES:
            raise ValueError(f"Unknown table: {table!r}")
        cols = list(rows[0].keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)
        update_cols = [c for c in cols if c not in conflict_cols]
        set_clause = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
        conflict = ", ".join(conflict_cols)
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO UPDATE SET {set_clause}"
            if update_cols else
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO NOTHING"
        )
        data = [tuple(r.get(c) for c in cols) for r in rows]
        self.conn.executemany(sql, data)
        self.conn.commit()
        return len(rows)

    def query(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def close(self):
        self.conn.close()
