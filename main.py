import subprocess
import ctypes
import sys
import tkinter as tk
from tkinter import messagebox, ttk

RULE_NAME = 'WarframePairBlockPort'
RULE_COMMAND = f'netsh advfirewall firewall show rule name={RULE_NAME} dir=out'
ADD_RULE_COMMAND = f"netsh advfirewall firewall add rule name={RULE_NAME} protocol=UDP dir=out localport={{}}-{{}} action=block"
SET_RULE_COMMAND = f"netsh advfirewall firewall set rule name={RULE_NAME} new enable=yes"
DEL_RULE_COMMAND = f"netsh advfirewall firewall delete rule name={RULE_NAME}"
ADMIN_MESSAGE = '請用系統管理員身分執行程式'
NORMAL_STATUS = '目前狀態：配對目前正常'
BLOCKED_STATUS = '目前狀態：配對已阻斷'

class WarframePairBlockTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('WarframePairBlockTool')
        self.geometry('250x320')
        self.create_widgets()
        self.resizable(0, 0)

        self.auto_recover_timer = None  # 追蹤計時器

        self.protocol("WM_DELETE_WINDOW", self.on_close)  # 監聽關閉事件
        self.rule_status()  # 開啟時偵測規則是否存在

    def create_widgets(self):
        header_label = tk.Label(self, text='Warframe 配對限制器（強制主機）\n[ 封鎖 UDP 輸出 Port ]')
        header_label.pack()

        self.status_label = tk.Label(self, font="Arial,12")
        self.status_label.pack()

        tip_label = tk.Label(self, text="選擇您Warframe內的UDP埠")
        tip_label.pack()

        self.port_combo = ttk.Combobox(self,
            values=[
                "4950 & 4955",
                "4960 & 4965",
                "4970 & 4975",
                "4980 & 4985",
                "4990 & 4995",
                "3074 & 3080"])
        self.port_combo.pack()
        self.port_combo.current(0)

        hint_label = tk.Label(self, text="（若是預設可以不用更動）")
        hint_label.pack()

        auto_recover_frame = tk.Frame(self)
        auto_recover_frame.pack()

        self.auto_recover_var = tk.IntVar(value=1)
        auto_recover_check = tk.Checkbutton(auto_recover_frame, text='自動恢復配對（秒）', variable=self.auto_recover_var, command=self.toggle_auto_recover)
        auto_recover_check.pack(side=tk.LEFT)

        self.delay_var = tk.IntVar(value=20)
        self.delay_spin = tk.Spinbox(auto_recover_frame, from_=1, to=999, width=5, textvariable=self.delay_var)
        self.delay_spin.pack(side=tk.LEFT)

        btn_frame = tk.Frame(self)
        btn_frame.pack(side=tk.TOP)
        btn_check = tk.Button(btn_frame, text='查看防火牆', bg="gray90", height=1, width=30, command=self.check_rule)
        btn_check.grid(row=0, column=0)
        btn_generate = tk.Button(btn_frame, text='阻止配對[封鎖UDP輸出]', bg="firebrick2", fg="white", height=3, width=30, command=self.create_rule)
        btn_generate.grid(row=1, column=0)
        btn_del = tk.Button(btn_frame, text='恢復配對[恢復UDP輸出]', bg="SpringGreen3", fg="black", height=3, width=30, command=self.del_rule)
        btn_del.grid(row=2, column=0)

        author_label = tk.Label(self, text='此工具由小翔製作\n Discord: xiaoxiang_meow')
        author_label.pack()

    def rule_status(self):
        status = self.run_command(RULE_COMMAND)
        if status == 1:
            self.update_status('SpringGreen3', 'Black', NORMAL_STATUS)
        elif status == 0:
            self.update_status('firebrick2', 'white', BLOCKED_STATUS)

    def create_rule(self):
        WFPORT = self.port_combo.get().split(' & ')
        status = self.run_command(ADD_RULE_COMMAND.format(WFPORT[0], WFPORT[1]))
        if status == 0:
            self.run_command(SET_RULE_COMMAND)

            # 取消舊的計時器
            if self.auto_recover_timer:
                self.after_cancel(self.auto_recover_timer)
                self.auto_recover_timer = None

            # 如果開啟「自動恢復」，才啟動計時器
            if self.auto_recover_var.get() == 1:
                delay = int(self.delay_spin.get()) * 1000
                self.auto_recover_timer = self.after(delay, self.del_rule)
        elif status == 1:
            messagebox.showinfo('訊息', ADMIN_MESSAGE)
        self.rule_status()

    def toggle_auto_recover(self):
        if self.auto_recover_var.get() == 1:
            self.delay_spin['state'] = 'normal'
        else:
            self.delay_spin['state'] = 'disabled'
            # **立即取消現有計時器**
            if self.auto_recover_timer:
                self.after_cancel(self.auto_recover_timer)
                self.auto_recover_timer = None

    def del_rule(self):
        # 取消計時器，確保不會執行已排程的自動恢復
        if self.auto_recover_timer:
            self.after_cancel(self.auto_recover_timer)
            self.auto_recover_timer = None

        # 先確認規則是否存在，避免不必要的刪除動作
        status = self.run_command(RULE_COMMAND)
        if status == 0:  # 只有當規則存在時才執行刪除
            self.run_command(DEL_RULE_COMMAND)
            self.rule_status()
        elif status == 1:
            messagebox.showinfo('訊息', f'{ADMIN_MESSAGE}\n或{NORMAL_STATUS}')
            self.rule_status()

    def check_rule(self):
        subprocess.Popen('mmc wf.msc', shell=True)
        self.rule_status()

    def run_command(self, command):
        return subprocess.run(command, shell=True).returncode

    def update_status(self, bg, fg, text):
        self.status_label['bg'] = bg
        self.status_label['fg'] = fg
        self.status_label['text'] = text

    def on_close(self):
        """ 確保程式關閉時，只有當規則存在時才執行移除 """
        status = self.run_command(RULE_COMMAND)
        if status == 0:  # 只有當規則存在時才執行刪除
            self.del_rule()
        self.destroy()

if __name__ == "__main__":
    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    if is_admin():
        app = WarframePairBlockTool()
        app.mainloop()
    else:
        if sys.version_info[0] == 3:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, sys.argv[0], None, 1)
