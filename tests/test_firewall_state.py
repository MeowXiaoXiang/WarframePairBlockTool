import json
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from src.controller.firewall import (
    CommandExecutionError, FirewallController, RuleCreationError, RuleDeletionError,
)
from src.controller.worker import FirewallWorker


PORTS = (4950, 4955)


def rule(ports=(4950, 4955), **changes):
    value = {"Name": "local-id", "Enabled": "True", "Direction": "Outbound",
             "Action": "Block", "Ports": [{"Protocol": "UDP", "LocalPort": list(ports)}]}
    value.update(changes)
    return value


class FakeFirewall(FirewallController):
    def __init__(self, responses):
        super().__init__()
        self.responses = iter(responses)
        self.commands = []

    def run_command(self, command):
        self.commands.append(command)
        return self._next_response()

    def _run_powershell(self, script):
        self.commands.append(script)
        code, stdout, stderr = self._next_response()
        if code != 0:
            self.last_error = stderr
            raise CommandExecutionError(stderr)
        return stdout

    def _next_response(self):
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class FirewallStateTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "需要 Windows PowerShell")
    def test_powershell_session_is_reused(self):
        fw = FirewallController()
        try:
            command = "[System.Diagnostics.Process]::GetCurrentProcess().Id"
            first = fw._run_powershell(command).strip()
            second = fw._run_powershell(command).strip()
            self.assertEqual(first, second)
            self.assertTrue(first.isdecimal())
            fw.COMMAND_TIMEOUT = 0.1
            with self.assertRaisesRegex(CommandExecutionError, "逾時"):
                fw._run_powershell("Start-Sleep -Seconds 1")
            fw.COMMAND_TIMEOUT = 15
            self.assertEqual(fw._run_powershell("'ready'").strip(), "ready")
        finally:
            fw.close()

    def test_status_requires_exact_rule(self):
        cases = [([], "normal"), ([rule()], "blocked"),
                 ([rule(ports=(4950, 4951, 4955))], "unknown"),
                 ([rule(Enabled="False")], "unknown"),
                 ([rule(Direction="Inbound")], "unknown"),
                 ([rule(Action="Allow")], "unknown"),
                 ([rule(Ports=[{"Protocol": "TCP", "LocalPort": [4950, 4955]}])], "unknown"),
                 ([rule(), rule()], "unknown")]
        for rules, expected in cases:
            with self.subTest(expected=expected, rules=rules):
                fw = FakeFirewall([(0, json.dumps(rules), "")])
                self.assertEqual(fw.get_rule_status(PORTS), expected)

    def test_query_failure_is_unknown(self):
        fw = FakeFirewall([(1, "", "access denied")])
        self.assertEqual(fw.get_rule_status(PORTS), "unknown")
        self.assertEqual(fw.get_last_error(), "access denied")

    def test_query_filters_by_name_before_loading_ports(self):
        fw = FakeFirewall([(0, "[]", "")])
        self.assertEqual(fw.list_rules(), [])
        script = fw.commands[0]
        self.assertIn("-DisplayName 'WarframePairBlockPort'", script)
        self.assertIn("Get-NetFirewallPortFilter", script)
        self.assertIn("ErrorCategory]::ObjectNotFound", script)

    def test_command_timeout(self):
        fw = FirewallController()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 15)):
            with self.assertRaises(CommandExecutionError):
                fw.run_command("echo test")

    def test_startup_removes_all_exact_name_rules_and_verifies(self):
        fw = FakeFirewall([(0, "ok", "")])
        self.assertTrue(fw.clear_rules())
        self.assertEqual(len(fw.commands), 1)
        script = fw.commands[0]
        self.assertIn("-DisplayName 'WarframePairBlockPort'", script)
        self.assertIn("Remove-NetFirewallRule", script)
        self.assertIn("$remaining=@(FindRules)", script)
        self.assertNotIn("Get-NetFirewallRule -PolicyStore PersistentStore -ErrorAction Stop |", script)

    def test_delete_failure_and_remaining_rule(self):
        for response in ((1, "", "denied"), (1, "", "刪除後仍找到同名規則")):
            with self.subTest(response=response):
                with self.assertRaises(RuleDeletionError):
                    FakeFirewall([response]).clear_rules()

    def test_create_verification_failure(self):
        fw = FakeFirewall([(0, "", ""), (0, json.dumps([rule(Enabled="False")]), "")])
        with self.assertRaises(RuleCreationError):
            fw.create_and_verify(PORTS)
        self.assertIn("enable=yes", fw.commands[0])

    def test_worker_serial_operations_report_result(self):
        fw = FakeFirewall([(0, "[]", ""), (0, "[]", "")])
        worker = FirewallWorker(fw)
        results = []
        worker.completed.connect(lambda *args: results.append(args))
        worker.execute("startup", PORTS)
        self.assertEqual(results[0][:3], ("startup", True, "normal"))

    def test_worker_reports_all_success_and_failure_operations(self):
        for operation in ("startup", "check", "create", "delete", "quit", "reset"):
            for failure in (False, True):
                with self.subTest(operation=operation, failure=failure):
                    fw = Mock(spec=FirewallController)
                    fw.get_rule_status.return_value = "unknown" if failure else "blocked"
                    fw.get_last_error.return_value = "query failed"
                    if failure:
                        fw.clear_rules.side_effect = RuleDeletionError("delete failed")
                        fw.create_and_verify.side_effect = RuleCreationError("verify failed")
                    worker = FirewallWorker(fw)
                    results = []
                    worker.completed.connect(lambda *args: results.append(args))
                    worker.execute(operation, PORTS)
                    expected = "blocked" if operation in ("check", "create") else "normal"
                    self.assertEqual(len(results), 1)
                    self.assertEqual(results[0][:3],
                                     (operation, not failure, "unknown" if failure else expected))
                    self.assertEqual(bool(results[0][3]), failure)


if __name__ == "__main__":
    unittest.main()
