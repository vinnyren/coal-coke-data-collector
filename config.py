from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "coal_data.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
LOG_DIR = BASE_DIR / "logs"

# 品种 → 各接口所需标识
# main_symbol: 新浪主力连续代码; spot_var: 现货基差/持仓接口的品种缩写
VARIETIES = {
    "焦煤": {"code": "jm", "exchange": "dce", "main_symbol": "JM0",
             "spot_var": "JM", "dce_name": "焦煤", "inventory_name": "焦煤"},
    "焦炭": {"code": "j", "exchange": "dce", "main_symbol": "J0",
             "spot_var": "J", "dce_name": "焦炭", "inventory_name": "焦炭"},
    "动力煤": {"code": "zc", "exchange": "czce", "main_symbol": "ZC0",
               "spot_var": "ZC", "dce_name": None, "inventory_name": "动力煤"},
}
