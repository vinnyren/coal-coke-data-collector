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

# 地区分类关键词表（用于把价格名称归类到 品种/地区类型/地区）
VARIETY_KEYWORDS = {
    "焦煤": ["焦煤", "炼焦煤", "主焦", "肥煤", "瘦煤"],
    "焦炭": ["焦炭", "冶金焦", "准一级", "一级焦", "二级焦"],
    "动力煤": ["动力煤", "电煤"],
}
PORT_NAMES = ["秦皇岛", "京唐", "曹妃甸", "日照", "天津", "连云港",
              "黄骅", "广州", "环渤海"]
PRODUCTION_AREAS = ["山西", "陕西", "内蒙古", "内蒙", "蒙西", "蒙东",
                    "鄂尔多斯", "新疆", "榆林", "大同", "吕梁"]
IMPORT_KEYWORDS = ["进口", "蒙煤", "澳煤", "俄煤", "甘其毛都", "满都拉"]
CONSUMPTION_AREAS = ["唐山", "华北", "华东", "华中", "华南", "西南",
                     "钢厂", "焦化厂"]
