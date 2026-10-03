import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

import main
from src.ui.settings import HotkeyCapture
from src.utils import single_instance


class FakeFirewall:
    last_error = ""

    def __init__(self):
        self.rules = []
        self.operations = []

    def clear_rules(self):
        self.operations.append("clear")
        self.rules.clear()

    def get_rule_status(self, ports):
        return "normal" if not self.rules else "blocked"

    def create_and_verify(self, ports):
        self.operations.append(("create", ports))
        self.rules.append(ports)

    def get_last_error(self):
        return self.last_error

    def open_firewall_ui(self):
        return True


class AppFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_debounced_settings_and_reset(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(main, "CONFIG_PATH", os.path.join(folder, "config.ini")):
            fw = FakeFirewall()
            controller = main.AppController(fw)
            controller.save_timer.stop()
            controller.window.combo.setCurrentIndex(2)
            controller.window.auto_recover_checkbox.setChecked(False)
            controller.window.recover_spinbox.setValue(31)
            self.assertTrue(controller.save_timer.isActive())
            QTest.qWait(400)
            self.assertTrue(os.path.exists(main.CONFIG_PATH))
            self.assertEqual(controller.config["Settings"]["udp_index"], "2")
            self.assertEqual(controller.config["Settings"]["auto_recover"], "false")
            self.assertEqual(controller.config["Settings"]["recover_time"], "31")
            controller.clear_config()
            QTest.qWait(100)
            self.assertEqual(controller.config["Settings"]["udp_index"], "0")
            self.assertEqual(controller.config["Settings"]["recover_time"], "20")
            for state, marker in (("STATE_NORMAL", "🟢"),
                                  ("STATE_BLOCKED", "🔴"),
                                  ("STATE_UNKNOWN", "⚪")):
                controller._set_state(state)
                self.assertTrue(controller.tray.status_action.text().startswith(marker))
            controller.worker_thread.quit()
            controller.worker_thread.wait(2000)
            controller.tray.cleanup()

    def test_quit_retry_exit_cancel_choices(self):
        controller = main.AppController.__new__(main.AppController)
        controller.window = None
        calls = []
        controller._quitting = True
        controller.quit_app = lambda: calls.append("retry")
        controller._finish_quit = lambda: calls.append("exit")
        for choice, expected in (("重試", ["retry"]), ("仍要退出", ["exit"]), ("取消", [])):
            calls.clear()
            controller._quitting = True
            class FakeBox:
                Icon = QMessageBox.Icon
                ButtonRole = QMessageBox.ButtonRole

                def __init__(self, *_):
                    self.buttons = {}

                def setIcon(self, *_):
                    pass

                def setWindowTitle(self, *_):
                    pass

                def setText(self, *_):
                    pass

                def setInformativeText(self, *_):
                    pass

                def setDetailedText(self, *_):
                    pass

                def addButton(self, text, *_):
                    self.buttons[text] = object()
                    return self.buttons[text]

                def exec(self):
                    pass

                def clickedButton(self):
                    return self.buttons[choice]

            with patch.object(main, "QMessageBox", FakeBox):
                main.AppController._ask_quit_failure(controller, "error")
            self.assertEqual(calls, expected)

    def test_hotkey_capture_success_cancel_timeout(self):
        capturer = HotkeyCapture()
        captured = []
        capturer.hotkey_captured.connect(captured.append)
        with patch("src.ui.settings.keyboard.hook", return_value="hook"), patch("src.ui.settings.keyboard.unhook"):
            capturer.start_capture()
            capturer._handle_key("alt", "down")
            capturer._handle_key("a", "down")
            self.assertEqual(captured.pop(), "Alt + A")
            capturer.start_capture()
            capturer._handle_key("esc", "down")
            self.assertEqual(captured.pop(), "")
            capturer.start_capture()
            capturer._timer.timeout.emit()
            self.assertEqual(captured.pop(), "")

    def test_uac_preserves_debug_flag(self):
        with patch.object(main.sys, "argv", ["main.py", "--debug"]), patch.object(main, "ctypes") as ctypes_mock:
            ctypes_mock.windll.shell32.ShellExecuteW.return_value = 42
            self.assertTrue(main.restart_as_admin())
            self.assertIn("--debug", ctypes_mock.windll.shell32.ShellExecuteW.call_args.args[3])
            self.assertEqual(ctypes_mock.windll.shell32.ShellExecuteW.restype, ctypes_mock.c_void_p)

    def test_second_instance_notifies_server(self):
        with patch.object(single_instance, "SERVER_NAME", "WarframePairBlockTool-test-" + str(os.getpid())):
            first = single_instance.SingleInstance()
            try:
                self.assertTrue(first.acquire())
                signaled = []
                first.activate_requested.connect(lambda: signaled.append(True))
                second = single_instance.SingleInstance()
                self.assertFalse(second.acquire())
                self.assertTrue(single_instance.notify_existing())
                for _ in range(10):
                    self.app.processEvents()
                self.assertTrue(signaled)
                second.close()
            finally:
                first.close()
            third = single_instance.SingleInstance()
            try:
                self.assertTrue(third.acquire())
            finally:
                third.close()


if __name__ == "__main__":
    unittest.main()
