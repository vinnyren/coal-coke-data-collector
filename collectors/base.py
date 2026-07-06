"""采集器基础设施：日志器、重试封装与 BaseCollector 基类。

不采集具体数据，为各 collector 提供统一的日志、重试与运行封装；
run() 捕获异常并返回结构化 RunResult dict（name/status/rows/error/duration_ms）。
"""
import time
import logging
import config


class UpstreamBlocked(Exception):
    """上游对本请求施加了已知的访问限制（如反爬 WAF 需浏览器渲染），非本项目代码缺陷。

    run() 据此把状态标为 skipped 而非 error：这类失败与采集器 bug 语义不同，
    不应触发 exit 3 造成无人值守告警疲劳。异常消息应说明限制来源与可行的启用方式。
    """


def get_logger(name):
    """返回带文件与流双处理器的 logger（日志写入 config.LOG_DIR/collector.log）。"""
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
    """调用 fn 并在异常时线性退避重试，最多 retries 次；全部失败则抛最后一次异常。"""
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
    """采集器基类：子类实现 fetch() 拉取并写库，run() 负责统一封装与错误处理。"""

    name = "base"

    def __init__(self, store):
        self.store = store
        self.log = get_logger(f"collector.{self.name}")

    def fetch(self, **kwargs):
        """由子类实现：拉取数据并写库，返回写入行数（int）。"""
        raise NotImplementedError

    def run(self, **kwargs):
        """执行 fetch 并返回 RunResult dict（name/status/rows/error/duration_ms），异常不外抛。"""
        start = time.monotonic()
        try:
            rows = self.fetch(**kwargs)
            rows = int(rows or 0)
            status = config.STATUS_OK if rows > 0 else config.STATUS_EMPTY
            error = None
            self.log.info("%s 写入 %s 行", self.name, rows)
        except UpstreamBlocked as e:
            # 已知外部限制：标 skipped（非 error），error 字段留原因摘要供人工判读
            rows = 0
            status = config.STATUS_SKIPPED
            error = f"{type(e).__name__}: {str(e)[:config.MAX_ERROR_LEN]}"
            self.log.warning("%s 跳过（上游限制）: %s", self.name, e)
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
