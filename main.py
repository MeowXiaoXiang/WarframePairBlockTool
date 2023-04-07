import customtkinter as ctk
from CTkMessagebox import CTkMessagebox
import subprocess, ctypes, sys, os, win32api

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.geometry("250x325")
        self.title("WarframePairBlockTool")
        self.my_font = ctk.CTkFont(family="Microsoft JhengHei", size=14) 

        self.headerLabel = ctk.CTkLabel(self, text="Warframe 配對限制器(強制主機)\n[封鎖UDP輸出埠]", font=self.my_font)
        self.headerLabel.grid(row=0, column=0, padx=25, pady=0)

        self.statusLabel = ctk.CTkLabel(self ,font=ctk.CTkFont(family="Microsoft JhengHei", size=18), anchor="center")
        self.statusLabel.grid(row=1, column=0, pady=5, sticky="nsew")

        self.tipLabel = ctk.CTkLabel(master=self,text="選擇您 Warframe 的 UDP 埠",font=self.my_font, anchor="center")
        self.tipLabel.grid(row=2, column=0, padx=25, pady=1)

        self.portComboBox = ctk.CTkComboBox(
            self,
            values=[
                "4950 & 4955", 
                "4960 & 4965",
                "4970 & 4975",
                "4980 & 4985",
                "4990 & 4995",
                "3074 & 3080"
            ],
            height=30,
            width=200,
            corner_radius=10)
        self.portComboBox.grid(row=3, column=0, padx=10, pady=1)

        self.checkBtn = ctk.CTkButton(
            self,
            text='查看防火牆',
            height = 35,
            width = 200,
            command=self.checkFireWall,
            font=ctk.CTkFont(family="Microsoft JhengHei")
        )
        self.checkBtn.grid(row=4, column=0, pady=3)

        self.blockBtn = ctk.CTkButton(
            self, 
            text='阻止配對[封鎖UDP輸出]', 
            fg_color="firebrick2", 
            text_color="white", 
            height = 50,
            width = 200,
            command=self.createRule,
            font=ctk.CTkFont(family="Microsoft JhengHei") 
        )
        self.blockBtn.grid(row=5, column=0, pady=1)

        self.restoreBtn = ctk.CTkButton(
            self, 
            text='恢復配對[恢復UDP輸出]', 
            fg_color="SpringGreen3", 
            text_color="black", 
            height = 50,
            width = 200,
            command=self.deleteRule,
            font=ctk.CTkFont(family="Microsoft JhengHei") 
        )
        self.restoreBtn.grid(row=6, column=0, pady=1)

        self.footerLabel = ctk.CTkLabel(master=self,text="此工具由小翔製作\nDiscord: XiaoXiang_Meow#6647",font=self.my_font, anchor="center") 
        self.footerLabel.grid(row=7, column=0, pady=2, sticky="nsew")
        
    def ruleStatus(self):
        status = subprocess.run('netsh advfirewall firewall show rule name=WarframePairBlockPort dir=out', shell=True)
        if status.returncode == 1:
            self.statusLabel.configure(text="目前狀態：配對目前正常", text_color="black", fg_color= "SpringGreen3")
        elif status.returncode == 0:
            self.statusLabel.configure(text="目前狀態：配對已阻斷", text_color="white", fg_color= "firebrick2")

    def createRule(self):
        WFPORT = self.portComboBox.get().split(' & ')
        status = subprocess.run(F"netsh advfirewall firewall add rule name=WarframePairBlockPort protocol=UDP dir=out localport={WFPORT[0]}-{WFPORT[1]} action=block", shell=True)
        if status.returncode == 0:
            subprocess.run("netsh advfirewall firewall set rule name=WarframePairBlockPort new enable=yes", shell=True)
        elif status.returncode == 1:
            CTkMessagebox(title="警告", message="目前配對已阻斷\n請勿重複點按", icon="warning", option_1="關閉", font=self.my_font)
        self.ruleStatus()
        
    def deleteRule(self):
        status = subprocess.run("netsh advfirewall firewall delete rule name=WarframePairBlockPort", shell=True)
        if status.returncode == 0:
            self.ruleStatus()
        elif status.returncode == 1:
            CTkMessagebox(title="警告", message="目前配對狀態為正常\n請勿重複點按", icon="warning", option_1="關閉", font=self.my_font)
            self.ruleStatus()

    def checkFireWall(self):
        win32api.ShellExecute(0, 'open', 'wf.msc', '', '', 1)
        self.ruleStatus()

if __name__ == "__main__":
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            app = App()
            app.ruleStatus()
            app.mainloop()
        else:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, os.path.abspath(sys.argv[0]), None, 1)
    except:
        pass
