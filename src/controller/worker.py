"""在單一背景執行緒中依序執行防火牆作業。"""

import time

from PySide6.QtCore import QObject, Signal, Slot
from loguru import logger


class FirewallWorker(QObject):
    completed = Signal(str, bool, str, str)

    def __init__(self, firewall):
        super().__init__()
        self.firewall = firewall

    @Slot(str, object)
    def execute(self, operation, ports):
        started = time.monotonic()
        try:
            logger.debug("防火牆作業開始：{} ports={}", operation, ports)
            if operation in ("startup", "delete", "quit"):
                self.firewall.clear_rules()
                state = "normal"
            elif operation == "create":
                self.firewall.create_and_verify(ports)
                state = "blocked"
            elif operation == "check":
                state = self.firewall.get_rule_status(ports)
                if state == "unknown":
                    raise RuntimeError(self.firewall.get_last_error())
            else:
                raise ValueError(f"未知的防火牆作業：{operation}")
            logger.info("防火牆作業完成：{} state={} elapsed={:.2f}s",
                        operation, state, time.monotonic() - started)
            self.completed.emit(operation, True, state, "")
        except Exception as exc:
            logger.exception("防火牆作業失敗：{} elapsed={:.2f}s", operation,
                             time.monotonic() - started)
            self.completed.emit(operation, False, "unknown", str(exc))
