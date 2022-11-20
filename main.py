import os
import tkinter as tk
from tkinter import messagebox,ttk
import ctypes, sys

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False
if is_admin():
    window = tk.Tk()
    window.title('WarframePairBlockTool')
    window.geometry('250x325')
    def rule_status():
        if os.system('netsh advfirewall firewall show rule name=WarframePairBlockPort dir=out') == 1:
            status_label['bg'] = 'SpringGreen3'
            status_label['fg'] = 'Black'
            status_label['text'] = '目前狀態：配對目前正常'
        elif os.system('netsh advfirewall firewall show rule name=WarframePairBlockPort dir=out') == 0:
            status_label['bg'] = 'firebrick2'
            status_label['fg'] = 'white'
            status_label['text'] = '目前狀態：配對已阻斷'

    '''此功能用以偵測程序的目標位置 本工具版本不使用這個而註解
    def Process_path(processname):
        WMI = GetObject('winmgmts:')
        processes = WMI.InstancesOf('Win32_Process')        #get list of all process
        for p in processes:                                 #for each process :
            if p.Properties_("Name").Value == processname : #if the process name is the one we wanted
                return p.Properties_[7].Value               #return the path and break the funcion
        return 'no such process'     
    '''

    def create_rule():
        WFPORT = port_combo.get().split(' & ')
        if os.system(f'start /B netsh advfirewall firewall add rule name=WarframePairBlockPort protocol=UDP dir=out localport={WFPORT[0]}-{WFPORT[1]} action=block') == 0:
            os.system("start /B netsh advfirewall firewall set rule name=WarframePairBlockPort new enable=yes")
            messagebox.showinfo('訊息', '已成功新增防火牆輸出規則！')
        elif os.system(f'start /B netsh advfirewall firewall add rule name=WarframePairBlockPort protocol=UDP dir=out localport={WFPORT[0]}-{WFPORT[1]} action=block') == 1:
            messagebox.showinfo('訊息', '請用系統管理員身分執行程式')
        rule_status()
        
    def del_rule():
        if os.system('start /B netsh advfirewall firewall delete rule name=WarframePairBlockPort') == 0:
            messagebox.showinfo('訊息', '已成功刪除防火牆輸出規則！')
        elif os.system('start /B netsh advfirewall firewall delete rule name=WarframePairBlockPort') == 1:
            messagebox.showinfo('訊息', '請用系統管理員身分執行程式或\n找不到要刪除的規則(或許不存在 可以使用)')
        rule_status()
        
    def check_rule():
        os.system('start /B C:\Windows\system32\wf.msc')
        rule_status()

    header_label = tk.Label(window, text='Warframe 配對限制器（強制主機）\n[ 封鎖 UDP 輸出 Port ]')
    header_label.pack()

    status_label = tk.Label(window, font="Arial,12")
    status_label.pack()

    tip_label = tk.Label(window, text = "選擇您Warframe內的UDP埠")
    tip_label.pack()

    port_combo = ttk.Combobox(window, 
                                values=[
                                        "4950 & 4955", 
                                        "4960 & 4965",
                                        "4970 & 4975",
                                        "4980 & 4985",
                                        "4990 & 4995",
                                        "3074 & 3080"])
    port_combo.pack()
    port_combo.current(0)
    hint_label = tk.Label(window, text = "（若是預設可以不用更動）\n")
    hint_label.pack()

    btn_frame = tk.Frame(window)
    btn_frame.pack(side=tk.TOP)
    btn_check = tk.Button(btn_frame, text='查看防火牆', bg="gray90",height = 1 ,width = 30,command=check_rule)
    btn_check.grid(row=0, column=0)
    btn_generate = tk.Button(btn_frame, text='阻止配對[封鎖UDP輸出]', bg="firebrick2", fg="white", height = 3 ,width = 30,command=create_rule)
    btn_generate.grid(row=1, column=0)
    btn_del = tk.Button(btn_frame, text='恢復配對[恢復UDP輸出]', bg="SpringGreen3", fg="black", height = 3 ,width = 30,command=del_rule)
    btn_del.grid(row=2, column=0)

    author_label = tk.Label(window, text='\n此工具由小翔製作\n Discord: XiaoXiang_Meow#6647')
    author_label.pack()
    rule_status() #開啟時偵測規則是否存在
    window.resizable(0,0)
    window.mainloop()
else:
    if sys.version_info[0] == 3:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
