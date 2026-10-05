import os
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from PySide6.QtCore import QObject, Signal, Slot

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


class ControlledWorker(QObject):
    completed = Signal(str, bool, str, str)

    def __init__(self, firewall):
        super().__init__()
        self.requests = []

    @Slot(str, object)
    def execute(self, operation, ports):
        self.requests.append((operation, ports))


class AppFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @contextmanager
    def checking_controller(self, initial_config=None):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(main, "CONFIG_PATH", os.path.join(folder, "config.ini")), \
                patch.object(main, "FirewallWorker", ControlledWorker), \
                patch.object(main.AppController, "_show_error") as error:
            if initial_config is not None:
                with open(main.CONFIG_PATH, "wb") as stream:
                    stream.write(initial_config)
            controller = main.AppController(FakeFirewall())
            try:
                self.wait_until(lambda: bool(controller.worker.requests))
                yield controller, error
            finally:
                controller.save_timer.stop()
                controller.auto_recover_timer.stop()
                controller.worker_thread.quit()
                controller.worker_thread.wait(2000)
                controller.tray.cleanup()
                controller.window.closeEvent = lambda event: event.accept()
                controller.window.close()

    def wait_until(self, predicate):
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate(), "Background operation did not arrive")

    def complete(self, controller, operation, success=True, state="normal"):
        self.wait_until(lambda: controller.worker.requests[-1][0] == operation)
        count = len(controller.worker.requests)
        controller.worker.completed.emit(operation, success, state, "failure" if not success else "")
        self.wait_until(lambda: controller._active_operation != operation
                        or len(controller.worker.requests) > count)
        if controller._busy:
            self.wait_until(lambda: controller.worker.requests[-1][0] == controller._active_operation)

    def test_checking_accepts_one_intent_and_preserves_hotkey(self):
        with self.checking_controller() as (controller, error):
            self.assertEqual(controller.worker.requests, [("startup", (4950, 4955))])
            self.assertTrue(controller.window.toggle_btn.isEnabled())
            self.assertTrue(controller.tray.toggle_action.isEnabled())
            controller.toggle_firewall(True)
            controller.toggle_firewall(False)
            self.assertFalse(controller.window.toggle_btn.isEnabled())
            self.assertFalse(controller.tray.toggle_action.isEnabled())
            self.assertEqual(len(controller.worker.requests), 1)
            self.assertFalse(controller.auto_recover_timer.isActive())
            self.complete(controller, "startup")
            self.assertEqual(controller.worker.requests[-1], ("create", (4950, 4955)))
            self.assertTrue(controller._operation_source_hotkey)
            controller.toggle_firewall()
            self.assertIsNone(controller._pending_action)
            self.complete(controller, "create", state="blocked")
            self.assertTrue(controller.auto_recover_timer.isActive())
            self.assertEqual(len(controller.worker.requests), 2)
            error.assert_not_called()

    def test_check_failure_cancels_intent_and_retries_startup_cleanup(self):
        with self.checking_controller() as (controller, error):
            controller.toggle_firewall()
            self.complete(controller, "startup", success=False)
            self.assertIsNone(controller._pending_action)
            self.assertEqual(controller.window.current_state, "STATE_UNKNOWN")
            self.assertTrue(controller.window.toggle_btn.isEnabled())
            error.assert_not_called()
            controller.toggle_firewall()
            self.wait_until(lambda: len(controller.worker.requests) == 2)
            self.assertEqual(controller.worker.requests[-1][0], "startup")
            self.complete(controller, "startup")
            self.assertEqual(len(controller.worker.requests), 2)
            controller._set_state("STATE_UNKNOWN")
            controller.toggle_firewall()
            controller.toggle_firewall()
            self.complete(controller, "check", success=False)
            self.assertIsNone(controller._pending_action)
            self.assertEqual(controller.window.current_state, "STATE_UNKNOWN")
            self.assertEqual(len(controller.worker.requests), 3)
            error.assert_not_called()

    def test_recheck_does_not_reverse_an_already_satisfied_intent(self):
        with self.checking_controller() as (controller, error):
            self.complete(controller, "startup")
            controller._set_state("STATE_UNKNOWN")
            controller.toggle_firewall()
            controller.tray.toggle_action.trigger()
            self.complete(controller, "check", state="blocked")
            self.assertEqual(controller.worker.requests[-1][0], "check")
            self.assertEqual(controller.window.current_state, "STATE_BLOCKED")
            controller._request("check")
            controller.window.toggle_btn.click()
            self.complete(controller, "check", state="blocked")
            self.assertEqual(controller.worker.requests[-1][0], "delete")
            controller.toggle_firewall()
            self.assertIsNone(controller._pending_action)
            self.complete(controller, "delete")
            error.assert_not_called()

    def test_quit_cancels_pending_action(self):
        with self.checking_controller() as (controller, error):
            controller.toggle_firewall()
            controller.quit_app()
            controller.toggle_firewall()
            self.assertIsNone(controller._pending_action)
            self.assertFalse(controller.window.toggle_btn.isEnabled())
            self.complete(controller, "startup")
            self.assertEqual(controller.worker.requests[-1][0], "quit")
            self.assertEqual(len(controller.worker.requests), 2)

    def test_reset_cancels_pending_action(self):
        with self.checking_controller() as (controller, error):
            controller.toggle_firewall()
            controller.clear_config()
            self.complete(controller, "startup")
            self.assertEqual(len(controller.worker.requests), 1)
            self.assertIsNone(controller._pending_action)

    def test_all_pairs_accept_button_tray_and_hotkey_only_once(self):
        pairs = ((4950, 4955), (4960, 4965), (4970, 4975),
                 (4980, 4985), (4990, 4995), (3074, 3080))
        for index, ports in enumerate(pairs):
            with self.subTest(ports=ports), self.checking_controller() as (controller, error):
                self.complete(controller, "startup")
                controller.window.combo.setCurrentIndex(index)
                if not controller._busy:
                    controller._request("check")
                actions = (controller.window.toggle_btn.click,
                           controller.tray.toggle_action.trigger,
                           lambda: controller.toggle_firewall(True))
                for offset in range(3):
                    actions[(index + offset) % 3]()
                self.complete(controller, "check")
                self.assertEqual(controller.worker.requests[-1], ("create", ports))
                self.complete(controller, "create", state="blocked")
                self.assertEqual(sum(op == "create" for op, _ in controller.worker.requests), 1)
                error.assert_not_called()

    def test_pending_create_respects_changed_recovery_setting(self):
        with self.checking_controller() as (controller, error):
            controller.window.toggle_btn.click()
            controller.window.auto_recover_checkbox.setChecked(False)
            controller.window.recover_spinbox.setValue(37)
            self.complete(controller, "startup")
            self.complete(controller, "create", state="blocked")
            self.assertFalse(controller.auto_recover_timer.isActive())
            controller.window.auto_recover_checkbox.setChecked(True)
            self.assertEqual(controller.auto_recover_timer.interval(), 37000)

    def test_create_and_delete_failures_require_recheck_without_queue(self):
        for operation in ("create", "delete"):
            with self.subTest(operation=operation), self.checking_controller() as (controller, error):
                self.complete(controller, "startup")
                if operation == "delete":
                    controller._set_state("STATE_BLOCKED")
                controller.toggle_firewall()
                controller.toggle_firewall()
                self.assertIsNone(controller._pending_action)
                self.complete(controller, operation, success=False)
                self.assertEqual(controller.window.current_state, "STATE_UNKNOWN")
                self.assertFalse(controller.auto_recover_timer.isActive())
                error.assert_called_once()
                controller.toggle_firewall()
                self.complete(controller, "check")
                self.assertEqual(controller.window.current_state, "STATE_NORMAL")

    def test_reset_during_create_cleans_original_ports_before_applying_defaults(self):
        with self.checking_controller() as (controller, error):
            self.complete(controller, "startup")
            controller.window.combo.setCurrentIndex(1)
            self.complete(controller, "check")
            controller.toggle_firewall(True)
            self.wait_until(lambda: controller.worker.requests[-1][0] == "create")
            controller.clear_config()
            self.assertEqual(controller._ports(), (4960, 4965))
            with patch.object(controller.tray, "show_message") as notification:
                self.complete(controller, "create", state="blocked")
                notification.assert_not_called()
            self.assertEqual(controller.worker.requests[-1], ("reset", (4960, 4965)))
            self.assertFalse(controller.window.toggle_btn.isEnabled())
            self.complete(controller, "reset")
            self.assertEqual(controller._ports(), (4950, 4955))
            self.assertEqual(controller.window.current_state, "STATE_NORMAL")
            error.assert_not_called()

    def test_port_change_during_check_discards_old_result(self):
        with self.checking_controller() as (controller, error):
            self.complete(controller, "startup")
            controller.window.combo.setCurrentIndex(1)
            self.wait_until(lambda: controller.worker.requests[-1][0] == "check")
            controller.toggle_firewall()
            controller.window.combo.setCurrentIndex(2)
            self.complete(controller, "check", state="blocked")
            self.assertEqual(controller.window.current_state, "STATE_UNKNOWN")
            self.assertEqual(controller.worker.requests[-1], ("check", (4970, 4975)))
            self.complete(controller, "check")
            self.assertEqual(controller.window.current_state, "STATE_NORMAL")
            self.assertIsNone(controller._pending_action)

    def test_recovery_due_during_check_has_priority_over_pending_action(self):
        for success, state in ((True, "blocked"), (False, "unknown"), (True, "normal")):
            with self.subTest(success=success, state=state), self.checking_controller() as (controller, error):
                self.complete(controller, "startup")
                controller.toggle_firewall()
                self.complete(controller, "create", state="blocked")
                controller._request("check")
                controller.toggle_firewall()
                controller.auto_recover_timer.stop()
                controller._on_recover_timeout()
                self.assertTrue(controller._recover_due)
                self.complete(controller, "check", success=success, state=state)
                self.assertIsNone(controller._pending_action)
                if state == "normal":
                    self.assertFalse(controller._busy)
                else:
                    self.assertEqual(controller.worker.requests[-1][0], "delete")
                    self.complete(controller, "delete")
                self.assertFalse(controller.auto_recover_timer.isActive())
                error.assert_not_called()

    def test_disabling_recovery_cancels_due_deletion(self):
        with self.checking_controller() as (controller, error):
            self.complete(controller, "startup")
            controller.toggle_firewall()
            self.complete(controller, "create", state="blocked")
            controller._request("check")
            controller._on_recover_timeout()
            controller.window.auto_recover_checkbox.setChecked(False)
            self.complete(controller, "check", state="blocked")
            self.assertFalse(controller._busy)
            self.assertFalse(controller._recover_due)
            self.assertFalse(controller.auto_recover_timer.isActive())

    def test_repeated_quit_and_cancel_allow_retry(self):
        with self.checking_controller() as (controller, error):
            self.complete(controller, "startup")
            controller.quit_app()
            controller.quit_app()
            self.assertFalse(controller._quit_requested)
            def cancel(_):
                controller._quitting = False
                controller._set_state("STATE_UNKNOWN")
            with patch.object(controller, "_ask_quit_failure", side_effect=cancel):
                self.complete(controller, "quit", success=False)
            self.assertTrue(controller.window.toggle_btn.isEnabled())
            controller.toggle_firewall()
            self.complete(controller, "check")
            self.assertEqual(controller.window.current_state, "STATE_NORMAL")

    def test_quit_failure_choices_with_actual_controller_state(self):
        for choice in (0, 1, 2):
            with self.subTest(choice=choice), self.checking_controller() as (controller, error):
                self.complete(controller, "startup")
                controller.quit_app()
                buttons = [object(), object(), object()]
                box = Mock()
                box.addButton.side_effect = buttons
                box.clickedButton.return_value = buttons[choice]
                box.exec.side_effect = controller.quit_app
                box_type = Mock(return_value=box)
                box_type.Icon = QMessageBox.Icon
                box_type.ButtonRole = QMessageBox.ButtonRole
                with patch.object(main, "QMessageBox", box_type), \
                        patch.object(controller, "_finish_quit") as finish:
                    self.complete(controller, "quit", success=False)
                    self.assertFalse(controller._quit_requested)
                    if choice == 0:
                        self.assertTrue(controller._busy)
                        self.assertEqual([op for op, _ in controller.worker.requests].count("quit"), 2)
                        self.complete(controller, "quit")
                        finish.assert_called_once()
                    elif choice == 1:
                        finish.assert_called_once()
                    else:
                        finish.assert_not_called()
                        self.assertFalse(controller._quitting)
                        self.assertTrue(controller.window.toggle_btn.isEnabled())
                        self.assertTrue(controller.tray.toggle_action.isEnabled())
                        controller.toggle_firewall()
                        self.complete(controller, "check")
                    error.assert_not_called()

    def test_quit_has_priority_over_due_recovery(self):
        with self.checking_controller() as (controller, error):
            self.complete(controller, "startup")
            controller.toggle_firewall()
            self.complete(controller, "create", state="blocked")
            controller._request("check")
            controller._on_recover_timeout()
            controller.quit_app()
            self.complete(controller, "check", state="blocked")
            self.assertEqual(controller.worker.requests[-1][0], "quit")
            self.assertFalse(controller._recover_due)
            self.assertFalse(controller.auto_recover_timer.isActive())

    def test_quit_during_create_failure_skips_extra_error_dialog(self):
        with self.checking_controller() as (controller, error):
            self.complete(controller, "startup")
            controller.toggle_firewall()
            controller.quit_app()
            self.complete(controller, "create", success=False)
            self.assertEqual(controller.worker.requests[-1][0], "quit")
            self.assertFalse(controller.window.toggle_btn.isEnabled())
            error.assert_not_called()

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
            self.wait_until(lambda: not controller._reset_requested)
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

    def test_corrupted_config_starts_with_defaults_without_registering_hotkey(self):
        contents = [b"not an ini file", b"\xff\xfeinvalid",
                    b"[Settings]\nnotifications=true\nnotifications=false\n"]
        for key in ("notifications", "auto_recover", "udp_index", "recover_time"):
            contents.append(f"[Settings]\nhotkey=alt+a\n{key}=invalid\n".encode())
        for content in contents:
            with self.subTest(content=content), \
                    patch("src.utils.hotkey.keyboard.add_hotkey") as register, \
                    self.checking_controller(content) as (controller, error):
                self.complete(controller, "startup")
                self.assertEqual(controller.window.combo.currentIndex(), 0)
                self.assertEqual(controller.window.get_auto_recover_time(), 20)
                self.assertTrue(controller.window.is_auto_recover_enabled())
                self.assertTrue(controller.notifications_enabled)
                self.assertEqual(controller.hotkey, "")
                self.assertEqual(controller.window.current_state, "STATE_NORMAL")
                register.assert_not_called()
                error.assert_not_called()
                with open(main.CONFIG_PATH, "rb") as stream:
                    self.assertEqual(stream.read(), content)

    def test_config_values_are_validated_and_valid_partial_settings_are_preserved(self):
        for index in (-1, 6, 999):
            content = f"[Settings]\nudp_index={index}\nrecover_time=37\nauto_recover=false\n".encode()
            with self.subTest(index=index), self.checking_controller(content) as (controller, error):
                self.complete(controller, "startup")
                self.assertEqual(controller._ports(), (4950, 4955))
                self.assertEqual(controller.window.get_auto_recover_time(), 37)
                self.assertFalse(controller.window.is_auto_recover_enabled())
                error.assert_not_called()
        with self.checking_controller(b"[Settings]\nudp_index=5\nnotifications=false\n") as (controller, error):
            self.complete(controller, "startup")
            self.assertEqual(controller._ports(), (3074, 3080))
            self.assertEqual(controller.window.get_auto_recover_time(), 20)
            self.assertFalse(controller.notifications_enabled)

    def test_config_read_error_uses_defaults(self):
        with self.checking_controller() as (controller, error):
            with patch("builtins.open", side_effect=PermissionError("denied")):
                controller._load_config()
            self.assertEqual(dict(controller.config["Settings"]), main.DEFAULTS)
            error.assert_not_called()

    def test_reset_during_capture_cancels_hook_and_ignores_late_events(self):
        for source in ("controller", "settings"):
            with self.subTest(source=source), self.checking_controller() as (controller, error), \
                    patch("src.ui.settings.keyboard.hook", return_value="hook"), \
                    patch("src.ui.settings.keyboard.unhook") as unhook, \
                    patch("src.utils.hotkey.keyboard.add_hotkey", return_value="registered") as register, \
                    patch("src.utils.hotkey.keyboard.remove_hotkey"), \
                    patch("src.ui.settings.QMessageBox.question", return_value=QMessageBox.Yes), \
                    patch("src.ui.settings.QMessageBox.information"):
                self.complete(controller, "startup")
                controller.set_hotkey("alt+a")
                controller.open_settings()
                settings = controller.settings_window
                try:
                    settings._start_hotkey_capture()
                    register.reset_mock()
                    if source == "controller":
                        controller.clear_config()
                    else:
                        settings._on_clear_clicked()
                    self.assertIsNone(settings.hotkey_capturer._hook)
                    self.assertFalse(settings.hotkey_capturer._timer.isActive())
                    unhook.assert_called_once_with("hook")
                    self.complete(controller, "reset")
                    settings.hotkey_capturer._key_seen.emit("b", "down")
                    settings.hotkey_capturer._handle_key("esc", "down")
                    settings.hotkey_capturer._timer.timeout.emit()
                    settings.close()
                    self.assertEqual(controller.hotkey, "")
                    self.assertEqual(settings.hotkey_display.text(), "目前設定：無")
                    self.assertEqual(settings.hotkey_btn.text(), "設定快捷鍵")
                    register.assert_not_called()
                    settings._start_hotkey_capture()
                    settings.hotkey_capturer._handle_key("c", "down")
                    self.assertEqual(controller.hotkey, "C")
                    error.assert_not_called()
                finally:
                    settings.close()

    def test_blocked_reset_success_and_failure_preserve_rule_lifecycle(self):
        for success in (True, False):
            with self.subTest(success=success), self.checking_controller() as (controller, error):
                self.complete(controller, "startup")
                controller.window.combo.setCurrentIndex(1)
                self.complete(controller, "check")
                controller.toggle_firewall()
                self.complete(controller, "create", state="blocked")
                controller.clear_config()
                controller.toggle_firewall()
                self.assertEqual(controller._ports(), (4960, 4965))
                self.assertIsNone(controller._pending_action)
                self.complete(controller, "reset", success=success)
                self.assertFalse(controller._reset_requested)
                if success:
                    self.assertEqual(controller._ports(), (4950, 4955))
                    self.assertEqual(controller.window.current_state, "STATE_NORMAL")
                    self.assertFalse(controller.auto_recover_timer.isActive())
                    error.assert_not_called()
                else:
                    self.assertEqual(controller._ports(), (4960, 4965))
                    self.assertEqual(controller.window.current_state, "STATE_UNKNOWN")
                    error.assert_called_once()
                    controller.clear_config()
                    self.complete(controller, "reset")
                    self.assertEqual(controller._ports(), (4950, 4955))

    def test_reset_after_failed_create_or_check_still_cleans_rules(self):
        for operation in ("create", "check"):
            with self.subTest(operation=operation), self.checking_controller() as (controller, error):
                self.complete(controller, "startup")
                controller._request(operation)
                controller.clear_config()
                self.complete(controller, operation, success=False)
                self.assertEqual(controller.worker.requests[-1][0], "reset")
                error.assert_not_called()
                self.complete(controller, "reset")
                self.assertEqual(controller.window.current_state, "STATE_NORMAL")

    def test_quit_cancels_pending_reset(self):
        with self.checking_controller() as (controller, error):
            self.complete(controller, "startup")
            controller.window.recover_spinbox.setValue(37)
            controller.clear_config()
            controller.quit_app()
            self.complete(controller, "reset")
            self.assertEqual(controller.worker.requests[-1][0], "quit")
            self.assertEqual(controller.window.get_auto_recover_time(), 37)
            self.assertFalse(controller._reset_requested)

    def test_percent_hotkey_round_trips_without_interpolation(self):
        with self.checking_controller() as (controller, error), \
                patch("src.utils.hotkey.keyboard.add_hotkey", return_value="handle"), \
                patch("src.utils.hotkey.keyboard.remove_hotkey"):
            for hotkey in ("shift+%", "%(missing)s"):
                controller.hotkey = hotkey
                controller._save_config()
                controller.hotkey_handler.unregister_hotkey()
                controller._load_config()
                self.assertEqual(controller.hotkey, hotkey)
                self.assertEqual(controller.config["Settings"]["hotkey"], hotkey)
            controller.hotkey_handler.unregister_hotkey()
            controller.hotkey = ""
            error.assert_not_called()

    def test_recovery_seconds_out_of_range_use_defaults_before_qt_conversion(self):
        for seconds in (-1, 0, 1000, 2**31, 10**30):
            with self.subTest(seconds=seconds), \
                    self.checking_controller(f"[Settings]\nrecover_time={seconds}\n".encode()) as (controller, error):
                self.complete(controller, "startup")
                self.assertEqual(controller.window.get_auto_recover_time(), 20)
                error.assert_not_called()

    def test_successful_capture_registers_once_and_cancel_restores_original(self):
        with self.checking_controller() as (controller, error), \
                patch("src.ui.settings.keyboard.hook", return_value="hook"), \
                patch("src.ui.settings.keyboard.unhook"), \
                patch("src.utils.hotkey.keyboard.add_hotkey", return_value="handle") as register, \
                patch("src.utils.hotkey.keyboard.remove_hotkey"):
            controller.open_settings()
            settings = controller.settings_window
            try:
                settings._start_hotkey_capture()
                register.reset_mock()
                settings.hotkey_capturer._handle_key("b", "down")
                self.assertEqual(register.call_count, 1)
                self.assertEqual(controller.hotkey, "B")
                self.assertIsNotNone(controller.hotkey_handler._handle)
                settings._start_hotkey_capture()
                register.reset_mock()
                settings.hotkey_capturer.cancel()
                self.assertEqual(register.call_count, 1)
                self.assertEqual(controller.hotkey, "B")
                settings._start_hotkey_capture()
                register.reset_mock()
                register.side_effect = [RuntimeError("failed"), "old-handle"]
                settings.hotkey_capturer._handle_key("c", "down")
                self.assertEqual(register.call_count, 2)
                self.assertEqual(controller.hotkey, "B")
                self.assertEqual(controller.hotkey_handler._handle, "old-handle")
                error.assert_called_once()
            finally:
                settings.close()
                controller.hotkey_handler.unregister_hotkey()


    def test_quit_retry_exit_cancel_choices(self):
        controller = main.AppController.__new__(main.AppController)
        controller.window = None
        calls = []
        controller._quitting = True
        controller.quit_app = lambda: calls.append("retry")
        controller._finish_quit = lambda: calls.append("exit")
        controller._set_state = lambda *_: None
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
