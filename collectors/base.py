import time
import logging
import config


def get_logger(name):
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fh = logging.FileHandler(config.LOG_DIR / "collector.log", encoding="utf-8")
        sh = logging.StreamHandler()
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        fh.setFormatter(fmt); sh.setFormatter(fmt)
        logger.addHandler(fh); logger.addHandler(sh)
    return logger


def with_retry(fn, retries=3, backoff=2):
    last = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise last


class BaseCollector:
    name = "base"

    def __init__(self, store):
        self.store = store
        self.log = get_logger(f"collector.{self.name}")

    def fetch(self, **kwargs):
        raise NotImplementedError

    def run(self, **kwargs):
        start = time.monotonic()
        try:
            rows = self.fetch(**kwargs)
            rows = int(rows or 0)
            status = config.STATUS_OK if rows > 0 else config.STATUS_EMPTY
            error = None
            self.log.info("%s 写入 %s 行", self.name, rows)
        except Exception as e:  # noqa: BLE001
            rows = 0
            status = config.STATUS_ERROR
            # 报告里只留类型 + 限长摘要（仅截断，非脱敏）；完整堆栈仅进文件日志
            error = f"{type(e).__name__}: {str(e)[:config.MAX_ERROR_LEN]}"
            self.log.warning("%s 采集失败: %s", self.name, e, exc_info=True)
        return {
            "name": self.name, "status": status, "rows": rows,
            "error": error,
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
