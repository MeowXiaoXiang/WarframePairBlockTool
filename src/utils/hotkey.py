"""全域快捷鍵註冊與 UI 訊號。"""

import keyboard
from loguru import logger
from PySide6.QtCore import QObject, Signal


class HotkeyManager(QObject):
    toggle_signal = Signal(bool)

    def __init__(self):
        super().__init__()
        self._handle = None

    def register_hotkey(self, hotkey, callback):
        self.unregister_hotkey()
        if not hotkey:
            return False
        try:
            self._handle = keyboard.add_hotkey(hotkey, callback, suppress=False)
            logger.info("快捷鍵已註冊：{}", hotkey)
            return True
        except Exception as exc:
            logger.error("快捷鍵註冊失敗：{}", exc)
            return False

    def unregister_hotkey(self):
        if self._handle is None:
            return False
        try:
            keyboard.remove_hotkey(self._handle)
            return True
        except Exception as exc:
            logger.error("快捷鍵取消註冊失敗：{}", exc)
            return False
        finally:
            self._handle = None

    def emit_toggle(self, from_hotkey=True):
        self.toggle_signal.emit(from_hotkey)

    @staticmethod
    def format_hotkey_display(hotkey):
        if not hotkey:
            return ""
        return " + ".join(part.strip().capitalize() for part in hotkey.split("+"))
