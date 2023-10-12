import subprocess
import ctypes
import sys
import win32api
import tkinter as tk
from tkinter import messagebox, ttk

class WarframePairBlockTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('WarframePairBlockTool')
        self.geometry('250x325')
        self.create_widgets()
        self.resizable(0, 0)

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
        hint_label = tk.Label(self, text="（若是預設可以不用更動）\n")
        hint_label.pack()

        btn_frame = tk.Frame(self)
        btn_frame.pack(side=tk.TOP)
        btn_check = tk.Button(btn_frame, text='查看防火牆', bg="gray90", height=1, width=30, command=self.check_rule)
        btn_check.grid(row=0, column=0)
        btn_generate = tk.Button(btn_frame, text='阻止配對[封鎖UDP輸出]', bg="firebrick2", fg="white", height=3, width=30, command=self.create_rule)
        btn_generate.grid(row=1, column=0)
        btn_del = tk.Button(btn_frame, text='恢復配對[恢復UDP輸出]', bg="SpringGreen3", fg="black", height=3, width=30, command=self.del_rule)
        btn_del.grid(row=2, column=0)

        author_label = tk.Label(self, text='\n此工具由小翔製作\n Discord: XiaoXiang_Meow#6647')
        author_label.pack()
        self.rule_status()  # 開啟時偵測規則是否存在

    def rule_status(self):
        status = subprocess.run('netsh advfirewall firewall show rule name=WarframePairBlockPort dir=out', shell=True)
        if status.returncode == 1:
            self.status_label['bg'] = 'SpringGreen3'
            self.status_label['fg'] = 'Black'
            self.status_label['text'] = '目前狀態：配對目前正常'
        elif status.returncode == 0:
            self.status_label['bg'] = 'firebrick2'
            self.status_label['fg'] = 'white'
            self.status_label['text'] = '目前狀態：配對已阻斷'

    def create_rule(self):
        WFPORT = self.port_combo.get().split(' & ')
        status = subprocess.run(F"netsh advfirewall firewall add rule name=WarframePairBlockPort protocol=UDP dir=out localport={WFPORT[0]}-{WFPORT[1]} action=block", shell=True)
        if status.returncode == 0:
            subprocess.run("netsh advfirewall firewall set rule name=WarframePairBlockPort new enable=yes", shell=True)
        elif status.returncode == 1:
            messagebox.showinfo('訊息', '請用系統管理員身分執行程式')
        self.rule_status()

    def del_rule(self):
        status = subprocess.run("netsh advfirewall firewall delete rule name=WarframePairBlockPort", shell=True)
        if status.returncode == 0:
            self.rule_status()
        elif status.returncode == 1:
            messagebox.showinfo('訊息', '請用系統管理員身分執行程式\n或目前配對狀態為正常')
            self.rule_status()

    def check_rule(self):
        win32api.ShellExecute(0, 'open', 'wf.msc', '', '', 1)
        self.rule_status()

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
