"""项目全局配置：路径解析、跨模块常量与品种/地区关键词表。

提供 resolve_db_path/resolve_runs_dir（环境变量 COAL_DB_PATH/COAL_RUNS_DIR 优先，
否则回退到项目内默认路径），采集状态常量 STATUS_*、进程退出码 EXIT_*、
回补起始日 BACKFILL_START，以及品种标识 VARIETIES 与地区分类关键词表。
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "db" / "coal_data.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
LOG_DIR = BASE_DIR / "logs"

# 采集器运行状态（base.py 产出，report.py 消费；避免字符串跨模块耦合）
STATUS_OK = "ok"        # 跑通且写入行数 > 0
STATUS_EMPTY = "empty"  # 跑通但写入 0 行（软失败）
STATUS_ERROR = "error"  # fetch 抛异常

# 进程退出码（无人值守调度器据此判断健康度）
EXIT_OK = 0              # 无 error（全 ok/empty）
EXIT_FATAL = 2          # 致命：DB 初始化失败 / 无可运行采集器 / 报告写出失败
EXIT_COLLECTOR_ERROR = 3  # 存在 status=error 的采集器

# 回补默认起始日期（backfill 模式）
BACKFILL_START = "2015-01-01"

# 报告中单条 error 文本的最大长度（防止上游异常携带的敏感串/长文本膨胀报告）
MAX_ERROR_LEN = 500

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


def _env_path(var):
    """读取路径类环境变量：去首尾空白后展开 ~；空串或纯空白视为未设置。"""
    val = os.environ.get(var, "").strip()
    return Path(val).expanduser() if val else None


def resolve_db_path():
    """DB 路径：环境变量 COAL_DB_PATH 优先，回退 DB_PATH。"""
    return _env_path("COAL_DB_PATH") or DB_PATH


def resolve_runs_dir():
    """运行报告目录：环境变量 COAL_RUNS_DIR 优先，回退 <项目>/runs。"""
    return _env_path("COAL_RUNS_DIR") or (BASE_DIR / "runs")
