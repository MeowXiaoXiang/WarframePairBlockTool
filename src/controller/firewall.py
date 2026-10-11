"""Windows 防火牆規則的查詢與修改。"""

import base64
import json
import os
import queue
import subprocess
import threading
import time

from loguru import logger


class FirewallError(Exception):
    pass


class CommandExecutionError(FirewallError):
    pass


class RuleCreationError(FirewallError):
    pass


class RuleDeletionError(FirewallError):
    pass


class FirewallController:
    RULE_NAME = "WarframePairBlockPort"
    RULE_BASE = "netsh advfirewall firewall"
    MMC_COMMAND = "mmc wf.msc"
    STATUS_BLOCKED = "blocked"
    STATUS_NORMAL = "normal"
    STATUS_UNKNOWN = "unknown"
    COMMAND_TIMEOUT = 15

    def __init__(self):
        self.rule_name = self.RULE_NAME
        self.last_error = None
        self._shell = None
        self._shell_output = None
        self._shell_sequence = 0

    def _start_shell(self):
        if self._shell is not None and self._shell.poll() is None:
            return
        self.close()
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._shell = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=creationflags,
        )
        self._shell_output = queue.Queue()
        output = self._shell_output
        process = self._shell

        def read_lines():
            for line in process.stdout:
                output.put(line.rstrip("\r\n"))
            output.put(None)

        threading.Thread(target=read_lines, daemon=True).start()

    def close(self):
        if self._shell is not None:
            if self._shell.poll() is None:
                self._shell.kill()
            self._shell.wait(timeout=2)
            self._shell.stdin.close()
            self._shell.stdout.close()
            self._shell = None
            self._shell_output = None

    def run_command(self, command):
        started = time.monotonic()
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            process = subprocess.run(
                command, shell=isinstance(command, str), capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                startupinfo=startupinfo, timeout=self.COMMAND_TIMEOUT,
            )
            logger.debug("命令結束：code={} elapsed={:.2f}s stdout={!r} stderr={!r}",
                         process.returncode, time.monotonic() - started,
                         process.stdout[:1000], process.stderr[:1000])
            return process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired as exc:
            self.last_error = f"命令逾時（{self.COMMAND_TIMEOUT} 秒）"
            logger.warning("命令逾時：elapsed={:.2f}s", time.monotonic() - started)
            raise CommandExecutionError(self.last_error) from exc
        except OSError as exc:
            self.last_error = str(exc)
            raise CommandExecutionError(f"執行命令失敗：{exc}") from exc

    def list_rules(self):
        # 直接在防火牆服務端依名稱查詢，避免列舉所有本機規則。
        script = (
            self._find_rules_script()
            + "$rules=@(FindRules); "
            "$result=@(foreach($rule in $rules) { "
            "$ports=@($rule | Get-NetFirewallPortFilter -ErrorAction Stop); "
            "[PSCustomObject]@{ Name=$rule.Name; Enabled=[string]$rule.Enabled; "
            "Direction=[string]$rule.Direction; Action=[string]$rule.Action; "
            "Ports=@(foreach($port in $ports) { [PSCustomObject]@{ Protocol=[string]$port.Protocol; LocalPort=@($port.LocalPort) } }) } }); "
            "ConvertTo-Json -InputObject $result -Compress -Depth 6"
        )
        stdout = self._run_powershell(script)
        try:
            data = json.loads(stdout.lstrip("\ufeff"))
            if not isinstance(data, list):
                raise ValueError("規則清單格式錯誤")
            return data
        except (ValueError, TypeError) as exc:
            self.last_error = str(exc)
            raise CommandExecutionError(f"無法解析防火牆規則：{exc}") from exc

    def _find_rules_script(self):
        name = self.rule_name.replace("'", "''")
        return (
            "$ErrorActionPreference='Stop'; "
            "function FindRules { try { "
            f"@(Get-NetFirewallRule -PolicyStore PersistentStore -DisplayName '{name}' -ErrorAction Stop "
            f"| Where-Object {{ $_.DisplayName -ceq '{name}' }}) "
            "} catch { "
            "if ($_.CategoryInfo.Category -eq [System.Management.Automation.ErrorCategory]::ObjectNotFound "
            "-and $_.FullyQualifiedErrorId -like 'CmdletizationQuery_NotFound*') { @() } "
            "else { throw } "
            "} }; "
        )

    def _run_powershell(self, script):
        started = time.monotonic()
        try:
            self._start_shell()
            self._shell_sequence += 1
            sequence = self._shell_sequence
            encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
            command = (
                "$ErrorActionPreference='Stop'; try { "
                f"$source=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded}')); "
                "$result=(Invoke-Expression $source | Out-String); "
                "$payload=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($result)); "
                f"[Console]::Out.WriteLine('WFPBT:{sequence}:OK:'+$payload) "
                "} catch { "
                "$payload=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($_.ToString())); "
                f"[Console]::Out.WriteLine('WFPBT:{sequence}:ERR:'+$payload) "
                "}"
            )
            self._shell.stdin.write(command + "\n")
            self._shell.stdin.flush()
            deadline = started + self.COMMAND_TIMEOUT
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise queue.Empty()
                line = self._shell_output.get(timeout=remaining)
                if line is None:
                    raise CommandExecutionError("PowerShell 程序意外結束")
                prefix = f"WFPBT:{sequence}:"
                if not line.startswith(prefix):
                    logger.debug("PowerShell 其他輸出：{!r}", line[:300])
                    continue
                result, payload = line[len(prefix):].split(":", 1)
                decoded = base64.b64decode(payload).decode("utf-8", errors="replace")
                logger.debug("PowerShell 查詢：result={} elapsed={:.2f}s", result,
                             time.monotonic() - started)
                if result == "ERR":
                    self.last_error = decoded
                    raise CommandExecutionError(decoded)
                return decoded
        except queue.Empty as exc:
            self.last_error = f"命令逾時（{self.COMMAND_TIMEOUT} 秒）"
            self.close()
            raise CommandExecutionError(self.last_error) from exc
        except (OSError, ValueError, AttributeError) as exc:
            self.last_error = str(exc)
            self.close()
            raise CommandExecutionError(f"PowerShell 命令失敗：{exc}") from exc

    @staticmethod
    def _exact_ports(rule, selected):
        filters = rule.get("Ports", [])
        if len(filters) != 1 or str(filters[0].get("Protocol", "")).upper() != "UDP":
            return False
        raw = filters[0].get("LocalPort", [])
        if isinstance(raw, str):
            raw = [raw]
        try:
            ports = [int(piece.strip()) for item in raw for piece in str(item).split(",")]
        except (TypeError, ValueError):
            return False
        return len(ports) == 2 and len(set(ports)) == 2 and set(ports) == set(selected)

    def get_rule_status(self, ports):
        try:
            rules = self.list_rules()
            if not rules:
                self.last_error = None
                return self.STATUS_NORMAL
            if len(rules) != 1:
                self.last_error = "找到多個同名規則"
                return self.STATUS_UNKNOWN
            rule = rules[0]
            if (str(rule.get("Enabled", "")).lower() == "true"
                    and str(rule.get("Direction", "")).lower() == "outbound"
                    and str(rule.get("Action", "")).lower() == "block"
                    and self._exact_ports(rule, ports)):
                self.last_error = None
                return self.STATUS_BLOCKED
            self.last_error = "同名規則未啟用，或方向、動作、協定、UDP 埠與選取值不符"
            return self.STATUS_UNKNOWN
        except CommandExecutionError:
            return self.STATUS_UNKNOWN

    def clear_rules(self):
        """有同名規則時刪除並讀回；沒有時沿用首次查詢結果。"""
        script = (
            self._find_rules_script()
            + "$rules=@(FindRules); "
            "if ($rules.Count -gt 0) { "
            "$names=@($rules | Select-Object -ExpandProperty Name); "
            "Remove-NetFirewallRule -PolicyStore PersistentStore -Name $names -ErrorAction Stop; "
            "$remaining=@(FindRules); "
            "if ($remaining.Count -ne 0) { throw '刪除後仍找到同名規則' } }; "
            "'ok'"
        )
        try:
            self._run_powershell(script)
        except CommandExecutionError as exc:
            raise RuleDeletionError(str(exc)) from exc
        return True

    def create_rule(self, port_a: str, port_b: str):
        ports = (port_a, port_b)
        if (any(not isinstance(port, str) or not port.isascii() or not port.isdecimal()
                or not 1 <= int(port) <= 65535 or str(int(port)) != port for port in ports)
                or port_a == port_b):
            raise RuleCreationError("必須指定兩個不同的有效 UDP 埠")
        command = (f"{self.RULE_BASE} add rule name={self.rule_name} protocol=UDP "
                   f"dir=out localport={port_a},{port_b} action=block enable=yes")
        try:
            code, _, stderr = self.run_command(command)
            if code != 0:
                raise RuleCreationError(f"建立防火牆規則失敗：{stderr}")
            return code
        except CommandExecutionError as exc:
            raise RuleCreationError(str(exc)) from exc

    def create_and_verify(self, ports):
        self.create_rule(str(ports[0]), str(ports[1]))
        if self.get_rule_status(ports) != self.STATUS_BLOCKED:
            raise RuleCreationError("建立後無法確認規則與所選 UDP 埠一致")
        return True

    def delete_rule(self, names=None):
        try:
            if names is None:
                names = [rule["Name"] for rule in self.list_rules()]
            if not names:
                return 0
            literals = ",".join("'" + name.replace("'", "''") + "'" for name in names)
            script = ("$ErrorActionPreference='Stop'; "
                      f"Remove-NetFirewallRule -PolicyStore PersistentStore -Name @({literals}) -ErrorAction Stop")
            self._run_powershell(script)
            return 0
        except CommandExecutionError as exc:
            raise RuleDeletionError(str(exc)) from exc

    def open_firewall_ui(self):
        try:
            subprocess.Popen(self.MMC_COMMAND, shell=True)
            return True
        except OSError as exc:
            self.last_error = str(exc)
            return False

    def get_last_error(self):
        return self.last_error or "無錯誤"
