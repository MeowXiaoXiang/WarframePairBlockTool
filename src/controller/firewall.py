import subprocess
import os

class FirewallError(Exception):
    """防火牆操作錯誤基類"""
    pass

class CommandExecutionError(FirewallError):
    """執行命令時發生錯誤"""
    pass

class RuleCreationError(FirewallError):
    """建立規則時發生錯誤"""
    pass

class RuleDeletionError(FirewallError):
    """刪除規則時發生錯誤"""
    pass

class FirewallController:
    RULE_NAME = 'WarframePairBlockPort'
    RULE_BASE = 'netsh advfirewall firewall'
    MMC_COMMAND = 'mmc wf.msc'

    STATUS_BLOCKED = 'blocked'
    STATUS_NORMAL = 'normal'
    STATUS_UNKNOWN = 'unknown'

    def __init__(self):
        self.rule_name = self.RULE_NAME
        self.last_error = None

    def run_command(self, command):
        try:
            # 使用 UTF-8 編碼和環境設定
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            process = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True,
                encoding='utf-8',  # 明確指定 UTF-8 編碼
                errors='replace',  # 處理無法解碼的字元
                startupinfo=startupinfo
            )
            return process.returncode, process.stdout, process.stderr
        except Exception as e:
            self.last_error = str(e)
            raise CommandExecutionError(f"執行命令時發生錯誤：{e}")

    def get_rule_status(self):
        command = f'{self.RULE_BASE} show rule name={self.rule_name} dir=out'
        try:
            code, _, _ = self.run_command(command)
            if code == 0:
                return self.STATUS_BLOCKED
            elif code == 1:
                return self.STATUS_NORMAL
            return self.STATUS_UNKNOWN
        except Exception as e:
            self.last_error = str(e)
            return self.STATUS_UNKNOWN

    def create_rule(self, port_start: str, port_end: str):
        command = f"{self.RULE_BASE} add rule name={self.rule_name} protocol=UDP dir=out localport={port_start}-{port_end} action=block"
        try:
            code, _, stderr = self.run_command(command)
            if code != 0:
                self.last_error = stderr
                raise RuleCreationError(f"建立防火牆規則失敗：{stderr}")
            return code
        except CommandExecutionError as e:
            self.last_error = str(e)
            raise RuleCreationError(f"建立防火牆規則失敗：{e}")

    def enable_rule(self):
        command = f'{self.RULE_BASE} set rule name={self.rule_name} new enable=yes'
        try:
            code, _, stderr = self.run_command(command)
            if code != 0:
                self.last_error = stderr
            return code
        except Exception as e:
            self.last_error = str(e)
            return -1

    def delete_rule(self):
        command = f'{self.RULE_BASE} delete rule name={self.rule_name}'
        try:
            code, _, stderr = self.run_command(command)
            if code != 0:
                self.last_error = stderr
                raise RuleDeletionError(f"刪除防火牆規則失敗：{stderr}")
            return code
        except CommandExecutionError as e:
            self.last_error = str(e)
            raise RuleDeletionError(f"刪除防火牆規則失敗：{e}")

    def open_firewall_ui(self):
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            subprocess.Popen(
                self.MMC_COMMAND, 
                shell=True,
                startupinfo=startupinfo
            )
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def is_rule_present(self):
        return self.get_rule_status() == self.STATUS_BLOCKED

    def get_last_error(self):
        return self.last_error or "無錯誤"


if __name__ == "__main__":
    import ctypes
    import sys
    import time

    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, __file__, None, 1
        )
        sys.exit()

    print("🧪 啟動 FirewallController 測試...")
    fw = FirewallController()

    print("🔍 檢查規則狀態:", fw.get_rule_status())

    print("➕ 建立封鎖規則...")
    code = fw.create_rule("4950", "4955")
    print("create_rule:", "成功" if code == 0 else "失敗", "(代碼:", code, ")")

    print("✅ 啟用規則...")
    code = fw.enable_rule()
    print("enable_rule:", "成功" if code == 0 else "失敗", "(代碼:", code, ")")

    print("⌛ 等待 3 秒...")
    time.sleep(3)

    print("❌ 刪除規則...")
    code = fw.delete_rule()
    print("delete_rule:", "成功" if code == 0 else "失敗", "(代碼:", code, ")")

    print("📂 嘗試開啟防火牆 MMC（視窗應彈出）...")
    fw.open_firewall_ui()
