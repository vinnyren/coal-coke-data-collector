"""SQLite 存储层：封装连接、schema 初始化与幂等 upsert。

SqliteStore 提供 init_schema（执行建表脚本）、upsert（基于 ON CONFLICT 的
幂等写入，表名经 VALID_TABLES 白名单校验以防注入）、query 与 close。
"""
import sqlite3
from pathlib import Path

VALID_TABLES = {
    "futures_daily",
    "futures_realtime",
    "spot_basis",
    "position_rank",
    "inventory",
    "index_price",
    "spot_regional",
    "spot_regional_stats",
}


class SqliteStore:
    """SQLite 存储封装：连接管理、schema 初始化与幂等 upsert/查询。"""

    def __init__(self, db_path):
        """打开（必要时创建父目录与文件）SQLite 连接，行工厂设为 sqlite3.Row。"""
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def init_schema(self, schema_path):
        """执行 schema_path 中的建表脚本并提交（幂等，供每次启动调用）。"""
        with open(schema_path, "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        self.conn.commit()

    def upsert(self, table, rows, conflict_cols):
        """按 conflict_cols 幂等写入 rows，返回处理行数；table 经白名单校验。"""
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
        """执行只读查询，返回行字典列表（每行以列名为键）。"""
        cur = self.conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def close(self):
        """关闭底层 SQLite 连接。"""
        self.conn.close()
