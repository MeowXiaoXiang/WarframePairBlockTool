"""Warframe 配對阻斷器入口與視窗控制。"""

import configparser
import ctypes
import os
import subprocess
import sys

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from loguru import logger

from src.controller import FirewallController
from src.controller.worker import FirewallWorker
from src.ui import SettingsUI, TrayManager, WarframeMainUI
from src.utils import HotkeyManager
from src.utils.single_instance import SingleInstance, notify_existing


def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(relative_path):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(get_base_dir(), relative_path)


def get_app_data_dir():
    path = os.path.join(os.getenv("APPDATA") or get_base_dir(), "WarframePairBlockTool")
    os.makedirs(path, exist_ok=True)
    return path


BASE_DIR = get_base_dir()
APP_DATA_DIR = get_app_data_dir()
CONFIG_PATH = os.path.join(APP_DATA_DIR, "WarframePairBlockTool.ini")
LOG_PATH = os.path.join(APP_DATA_DIR, "WarframePairBlockTool.log")
ICON_PATH = get_resource_path("assets/logo.ico")
BLOCKED_ICON_PATH = get_resource_path("assets/logo_blocked.ico")
DEFAULTS = {"udp_index": "0", "auto_recover": "true", "recover_time": "20",
            "notifications": "true", "hotkey": ""}


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def restart_as_admin(args=None):
    flags = [arg for arg in (sys.argv[1:] if args is None else args)
             if arg in ("--debug", "-debug")]
    parameters = flags if getattr(sys, "frozen", False) else [os.path.abspath(__file__), *flags]
    shell_execute = ctypes.windll.shell32.ShellExecuteW
    shell_execute.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                              ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int)
    shell_execute.restype = ctypes.c_void_p
    result = shell_execute(
        None, "runas", sys.executable, subprocess.list2cmdline(parameters), None, 1)
    return bool(result and result > 32)


def set_logger(args=None):
    debug = any(arg in ("--debug", "-debug") for arg in
                (sys.argv[1:] if args is None else args))
    logger.remove()
    level = "DEBUG" if debug else "INFO"
    log_format = "{time:YYYY-MM-DD HH:mm:ss} | pid={process.id} | {level:<8} | {file}:{function}:{line} - {message}"
    logger.add(LOG_PATH, level=level, format=log_format, encoding="utf-8",
               rotation="5 MB", retention="7 days")
    if sys.stderr:
        logger.add(sys.stderr, level=level, format=log_format)
    logger.info("日誌初始化：{}", LOG_PATH)


class FirewallDispatcher(QObject):
    requested = Signal(str, object)


class AppController(QObject):
    def __init__(self, firewall=None):
        super().__init__()
        self.firewall = firewall or FirewallController()
        self.config = configparser.ConfigParser()
        self.notifications_enabled = True
        self.hotkey = ""
        self.settings_window = None
        self._loading = True
        self._busy = False
        self._quitting = False
        self._quit_requested = False
        self._operation_source_hotkey = False

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(300)
        self.save_timer.timeout.connect(self._save_config)
        self.auto_recover_timer = QTimer(self)
        self.auto_recover_timer.setSingleShot(True)
        self.auto_recover_timer.timeout.connect(self._on_recover_timeout)
        self.hotkey_handler = HotkeyManager()
        self.hotkey_handler.toggle_signal.connect(self._safe_toggle_firewall)

        self.window = WarframeMainUI(
            toggle_callback=self.toggle_firewall,
            auto_recover_callback=self.on_auto_recover_changed,
            open_firewall_callback=self.open_firewall_ui,
            open_settings_callback=self.open_settings,
            state_labels={"STATE_BLOCKED": "配對已阻斷", "STATE_NORMAL": "配對正常",
                          "STATE_UNKNOWN": "重新檢查"},
            resolve_path=get_resource_path,
        )
        self.window.closeEvent = self._on_window_close
        self.tray = TrayManager(resolve_path=get_resource_path)
        self.tray.show_window_signal.connect(self.show_window)
        self.tray.toggle_firewall_signal.connect(self.toggle_firewall)
        self.tray.open_firewall_signal.connect(self.open_firewall_ui)
        self.tray.open_settings_signal.connect(self.open_settings)
        self.tray.quit_app_signal.connect(self.quit_app)
        self.tray.setup(parent_window=self.window)

        self._load_config()
        self._apply_config_to_ui()
        self.window.combo.currentIndexChanged.connect(self._on_port_changed)
        self.window.recover_spinbox.valueChanged.connect(self._schedule_save)
        self._loading = False
        self._set_state("STATE_UNKNOWN")

        self.dispatcher = FirewallDispatcher(self)
        self.worker_thread = QThread(self)
        self.worker = FirewallWorker(self.firewall)
        self.worker.moveToThread(self.worker_thread)
        self.dispatcher.requested.connect(self.worker.execute)
        self.worker.completed.connect(self._on_operation_complete)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.start()
        QTimer.singleShot(0, lambda: self._request("startup"))

    def _load_config(self):
        self.config["Settings"] = dict(DEFAULTS)
        if os.path.exists(CONFIG_PATH):
            self.config.read(CONFIG_PATH, encoding="utf-8")
        settings = self.config["Settings"]
        self.notifications_enabled = settings.getboolean("notifications", fallback=True)
        self.hotkey = settings.get("hotkey", "")
        if self.hotkey:
            self._register_hotkey()

    def _apply_config_to_ui(self):
        settings = self.config["Settings"]
        self._loading = True
        try:
            self.window.set_selected_udp_index(settings.getint("udp_index", fallback=0))
            self.window.set_auto_recover_enabled(settings.getboolean("auto_recover", fallback=True))
            self.window.set_auto_recover_time(settings.getint("recover_time", fallback=20))
        finally:
            self._loading = False

    def _schedule_save(self, *_):
        if not self._loading:
            self.save_timer.start()

    def _save_config(self):
        settings = self.config["Settings"]
        settings["udp_index"] = str(self.window.combo.currentIndex())
        settings["auto_recover"] = str(self.window.is_auto_recover_enabled()).lower()
        settings["recover_time"] = str(self.window.get_auto_recover_time())
        settings["notifications"] = str(self.notifications_enabled).lower()
        settings["hotkey"] = self.hotkey or ""
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as stream:
                self.config.write(stream)
            logger.debug("設定已儲存")
        except OSError as exc:
            self._show_error(f"無法儲存設定：{exc}")

    def _ports(self):
        return tuple(int(port.strip()) for port in self.window.get_selected_udp_ports().split("&"))

    def _set_state(self, state):
        previous = self.window.current_state
        self.window.set_toggle_state(state)
        self.window.toggle_btn.setEnabled(not self._busy)
        self.window.combo.setEnabled(not self._busy and state != "STATE_BLOCKED")
        self.tray.update_status(state, busy=self._busy)
        logger.debug("狀態轉移：{} -> {}，busy={}", previous, state, self._busy)

    def _request(self, operation):
        if self._busy:
            return False
        self._busy = True
        if operation in ("startup", "quit"):
            self.auto_recover_timer.stop()
        self.window.toggle_btn.setEnabled(False)
        self.window.combo.setEnabled(False)
        self.tray.update_status(self.window.current_state, busy=True)
        self.dispatcher.requested.emit(operation, self._ports())
        return True

    def _on_operation_complete(self, operation, success, state, error):
        self._busy = False
        if success:
            self._set_state("STATE_BLOCKED" if state == "blocked" else "STATE_NORMAL")
            if self._operation_source_hotkey and self.notifications_enabled and operation in ("create", "delete"):
                self.tray.show_message(
                    "配對已阻斷" if operation == "create" else "配對已恢復",
                    f"UDP 埠 {self._ports()[0]}、{self._ports()[1]} 已封鎖" if operation == "create"
                    else "UDP 配對封鎖已解除",
                    icon=QIcon(BLOCKED_ICON_PATH if operation == "create" else ICON_PATH),
                )
            if operation == "create" and self.window.is_auto_recover_enabled():
                seconds = self.window.get_auto_recover_time()
                self.auto_recover_timer.start(seconds * 1000)
                logger.debug("自動恢復計時器啟動：{} 秒", seconds)
            elif operation in ("delete", "startup", "quit"):
                self.auto_recover_timer.stop()
        else:
            self.auto_recover_timer.stop()
            self._set_state("STATE_UNKNOWN")
            logger.error("{} 失敗：{}", operation, error)
            if operation != "quit":
                self._show_error(f"無法確認防火牆狀態：{error}")
        if operation == "quit":
            if success:
                self._finish_quit()
            else:
                self._ask_quit_failure(error)
        self._operation_source_hotkey = False
        if self._quit_requested and operation != "quit":
            self._quit_requested = False
            self.quit_app()

    def _on_port_changed(self, *_):
        self._schedule_save()
        if not self._loading and not self._busy:
            self._set_state("STATE_UNKNOWN")
            self._request("check")

    def _safe_toggle_firewall(self, from_hotkey=False):
        if self._busy or self._quitting:
            return
        state = self.window.current_state
        if state == "STATE_UNKNOWN":
            self._request("check")
        elif state == "STATE_BLOCKED":
            self._request("delete")
        else:
            self._request("create")
        self._operation_source_hotkey = from_hotkey

    def toggle_firewall(self, from_hotkey=False):
        self._safe_toggle_firewall(from_hotkey)

    def _on_recover_timeout(self):
        logger.debug("自動恢復計時器觸發")
        if self.window.current_state == "STATE_BLOCKED":
            self._request("delete")

    def on_auto_recover_changed(self, enabled):
        if not enabled:
            self.auto_recover_timer.stop()
            logger.debug("自動恢復計時器停止")
        elif self.window.current_state == "STATE_BLOCKED" and not self._loading:
            self.auto_recover_timer.start(self.window.get_auto_recover_time() * 1000)
        self._schedule_save()

    def open_firewall_ui(self):
        self.firewall.open_firewall_ui()

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = SettingsUI(
                notify_callback=self.toggle_notifications,
                hotkey_callback=self.set_hotkey,
                clear_config_callback=self.clear_config,
                capture_start_callback=self.hotkey_handler.unregister_hotkey,
                capture_end_callback=self._register_hotkey,
            )
        self.settings_window.notify_checkbox.blockSignals(True)
        self.settings_window.notify_checkbox.setChecked(self.notifications_enabled)
        self.settings_window.notify_checkbox.blockSignals(False)
        self.settings_window.hotkey_display.setText(
            f"目前設定：{HotkeyManager.format_hotkey_display(self.hotkey) if self.hotkey else '無'}")
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def toggle_notifications(self, enabled):
        self.notifications_enabled = enabled
        self._schedule_save()

    def set_hotkey(self, hotkey):
        previous = self.hotkey
        self.hotkey_handler.unregister_hotkey()
        self.hotkey = hotkey
        if hotkey and not self._register_hotkey():
            self.hotkey = previous
            self._register_hotkey()
            self._show_error("快捷鍵註冊失敗，已保留原設定")
            return False
        self._schedule_save()
        return True

    def _register_hotkey(self):
        if not self.hotkey:
            return True
        return self.hotkey_handler.register_hotkey(
            self.hotkey, lambda: self.hotkey_handler.emit_toggle(True))

    def clear_config(self):
        self.save_timer.stop()
        self.hotkey_handler.unregister_hotkey()
        self.hotkey = ""
        self.notifications_enabled = True
        self.config["Settings"] = dict(DEFAULTS)
        self._apply_config_to_ui()
        self._save_config()
        if self.settings_window:
            self.settings_window.hotkey_display.setText("目前設定：無")
            self.settings_window.notify_checkbox.blockSignals(True)
            self.settings_window.notify_checkbox.setChecked(True)
            self.settings_window.notify_checkbox.blockSignals(False)
        self._set_state("STATE_UNKNOWN")
        self._request("check")

    def show_window(self):
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _on_window_close(self, event):
        event.ignore()
        self.window.hide()
        if self.notifications_enabled:
            self.tray.show_message("Warframe 配對阻斷器", "程式仍在系統匣執行，可從系統匣結束。")

    def _show_error(self, message):
        logger.error(message)
        QMessageBox.warning(self.window, "錯誤", message)

    def quit_app(self):
        if self._busy:
            self._quit_requested = True
            return
        if self._quitting:
            return
        self._quitting = True
        self._request("quit")

    def _ask_quit_failure(self, error):
        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("無法清理防火牆規則")
        box.setText(f"無法確認同名規則已刪除：{error}")
        retry = box.addButton("重試", QMessageBox.ButtonRole.AcceptRole)
        exit_anyway = box.addButton("仍要退出", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() == retry:
            self._quitting = False
            self.quit_app()
        elif box.clickedButton() == exit_anyway:
            self._finish_quit()
        else:
            self._quitting = False

    def _finish_quit(self):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._save_config()
        self.hotkey_handler.unregister_hotkey()
        self.tray.cleanup()
        self.worker_thread.quit()
        self.worker_thread.wait(2000)
        self.firewall.close()
        QApplication.quit()

    def run(self):
        self.window.show()


def main():
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Warframe 配對阻斷器")
    app.setWindowIcon(QIcon(ICON_PATH))
    if notify_existing():
        return 0
    if not is_admin():
        return 0 if restart_as_admin() else 1
    instance = SingleInstance()
    if not instance.acquire():
        return 0
    app.aboutToQuit.connect(instance.close)
    set_logger()
    controller = AppController()
    instance.activate_requested.connect(controller.show_window)
    controller.run()
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        logger.exception("啟動失敗")
        QMessageBox.critical(None, "啟動失敗", f"應用程式無法啟動：{exc}")
        sys.exit(1)
