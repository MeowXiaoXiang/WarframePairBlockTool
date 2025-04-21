import sys
import os
import ctypes
import configparser

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer, QObject
from PySide6.QtGui import QIcon

from loguru import logger
from src.controller import FirewallController, RuleCreationError, RuleDeletionError
from src.ui import WarframeMainUI, SettingsUI, TrayManager
from src.utils import HotkeyManager

# 設定基本路徑
def get_base_dir():
    # 如果是 PyInstaller 打包後的執行環境
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # 開發環境下使用檔案位置
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(get_base_dir(), relative_path)

def get_app_data_dir():
    """取得應用程式資料目錄 (AppData/Roaming)"""
    app_data = os.path.join(os.getenv('APPDATA'), "WarframePairBlockTool")
    # 確保目錄存在
    if not os.path.exists(app_data):
        os.makedirs(app_data)
    return app_data

BASE_DIR = get_base_dir()
APP_DATA_DIR = get_app_data_dir()
CONFIG_PATH = os.path.join(APP_DATA_DIR, "WarframePairBlockTool.ini")
LOG_PATH = os.path.join(APP_DATA_DIR, "WarframePairBlockTool.log")
ICON_PATH = get_resource_path("assets/logo.ico")
BLOCKED_ICON_PATH = get_resource_path("assets/logo_blocked.ico")

def is_admin():
    """檢查是否有管理員權限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def restart_as_admin():
    """用管理員權限重新啟動"""
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, __file__, None, 1
    )

class AppController:
    def __init__(self):
        """初始化應用程式 Controller"""
        logger.info("初始化 AppController")
        
        # 基本元件初始化
        self.firewall = FirewallController()
        self.config = configparser.ConfigParser()
        self.auto_recover_timer = QTimer()
        self.auto_recover_timer.setSingleShot(True)
        self.auto_recover_timer.timeout.connect(self._on_recover_timeout)
        
        # 設定標誌
        self.notifications_enabled = True
        self.hotkey = None
        self.settings_window = None
        
        # 快捷鍵處理
        self.hotkey_handler = HotkeyManager()
        self.hotkey_handler.toggle_signal.connect(self._safe_toggle_firewall)
        
        # 初始化主視窗
        self.window = WarframeMainUI(
            toggle_callback=self.toggle_firewall,
            auto_recover_callback=self.on_auto_recover_changed,
            open_firewall_callback=self.open_firewall_ui,
            open_settings_callback=self.open_settings,
            state_labels={
                "STATE_BLOCKED": "配對已阻斷",
                "STATE_NORMAL": "配對正常"
            },
            resolve_path=get_resource_path
        )
        
        # 設定窗口關閉事件
        self.window.closeEvent = self._on_window_close
        
        # 初始化系統Tray，並與主介面關聯
        self.tray = TrayManager(resolve_path=get_resource_path)
        
        # 連接Tray訊號
        self.tray.show_window_signal.connect(self.window.show)
        self.tray.toggle_firewall_signal.connect(self.toggle_firewall)
        self.tray.open_firewall_signal.connect(self.open_firewall_ui)
        self.tray.open_settings_signal.connect(self.open_settings)
        self.tray.quit_app_signal.connect(self.quit_app)
        
        # 設定Tray並關聯到主介面
        self.tray.setup(parent_window=self.window)
        
        # 載入設定 (Tray初始化完成後再載入)
        self._load_config()
        
        # 初始化UI狀態
        self._init_ui_state()
        
        # 根據目前狀態更新Tray圖示
        self._update_tray_status()

    def _load_config(self):
        """載入設定檔，若不存在則建立預設設定"""
        try:
            # 如果設定檔不存在，建立一份
            if not os.path.exists(CONFIG_PATH):
                logger.warning("找不到設定檔，將建立預設設定檔")
                self.config["Settings"] = {
                    "udp_index": "0",
                    "auto_recover": "true",
                    "recover_time": "20",
                    "notifications": "true",
                    "hotkey": ""
                }
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    self.config.write(f)
                logger.info("已建立預設設定檔")

            # 載入設定檔
            self.config.read(CONFIG_PATH)

            if "Settings" not in self.config:
                self.config["Settings"] = {
                    "udp_index": "0",
                    "auto_recover": "true",
                    "recover_time": "20",
                    "notifications": "true",
                    "hotkey": ""
                }

            # 讀取通知設定
            s = self.config["Settings"]
            if "notifications" in s:
                self.notifications_enabled = s.getboolean("notifications")

            # 讀取並設定快捷鍵
            if "hotkey" in s:
                self.hotkey = s.get("hotkey")
                if self.hotkey:
                    self._register_hotkey()

            logger.info("設定檔載入完成")

        except Exception as e:
            logger.error(f"載入設定檔時發生錯誤: {e}")
            self._show_error(f"載入設定時發生錯誤: {e}\n已使用預設設定。")
            # 確保有預設設定
            self.config["Settings"] = {
                "udp_index": "0",
                "auto_recover": "true",
                "recover_time": "20",
                "notifications": "true",
                "hotkey": ""
            }

    def _save_config(self):
        """儲存設定檔"""
        try:
            with open(CONFIG_PATH, "w") as f:
                self.config.write(f)
            logger.info("設定已保存")
        except Exception as e:
            logger.error(f"保存設定檔時發生錯誤: {e}")
            self._show_error(f"無法保存設定: {e}")

    def _init_ui_state(self):
        """初始化UI狀態"""
        s = self.config["Settings"]
        self.window.set_selected_udp_index(int(s.get("udp_index", 0)))
        self.window.set_auto_recover_enabled(s.get("auto_recover", "true") == "true")
        self.window.set_auto_recover_time(int(s.get("recover_time", 20)))

        status = self.firewall.get_rule_status()
        if status == self.firewall.STATUS_BLOCKED:
            self.window.set_toggle_state("STATE_BLOCKED")
        else:
            self.window.set_toggle_state("STATE_NORMAL")

    def _update_tray_status(self):
        """更新系統Tray狀態圖示和文字"""
        try:
            is_blocked = (self.window.current_state == "STATE_BLOCKED")
            logger.debug(f"更新Tray狀態: {'阻斷中' if is_blocked else '正常'}")
            self.tray.update_status(is_blocked)
            logger.debug(f"Tray狀態更新完成")
        except Exception as e:
            logger.error(f"更新Tray狀態時發生錯誤: {e}")
            logger.exception("詳細錯誤")

    def _on_window_close(self, event):
        """窗口關閉事件處理"""
        event.ignore()
        self.window.hide()
        
        # 窗口最小化時顯示通知
        if self.notifications_enabled:
            self.tray.show_message(
                title="Warframe 配對阻斷器",
                msg="程式已縮小到右下角系統列，點擊圖示可再次開啟",
                icon=QIcon(ICON_PATH),
                timeout=5000
            )

    def run(self):
        """啟動應用程式"""
        self.window.show()
        logger.info("應用程式已啟動")

    def toggle_firewall(self, from_hotkey=False):
        """
        切換防火牆狀態
        檢查呼叫來源，確保 UI 操作在主線程進行
        """
        try:
            # 檢查目前線程是否為 UI 線程
            if QApplication.instance().thread() != QObject.thread(QApplication.instance()):
                # 如果不是，透過訊號發送到主線程
                logger.debug("從非主線程調用toggle_firewall，重新導向至主線程")
                # 設置from_hotkey標記
                self.hotkey_handler.emit_toggle(True)
                return
                
            logger.debug("在主線程中執行toggle_firewall")
            self._safe_toggle_firewall(from_hotkey)
        except Exception as e:
            logger.error(f"toggle_firewall方法發生錯誤: {e}")
            logger.exception("詳細錯誤")
    
    def _safe_toggle_firewall(self, from_hotkey=False):
        """防火牆切換的實際操作函數"""
        try:
            state = self.window.current_state
            port_text = self.window.get_selected_udp_ports().replace(" ", "")
            port_start, port_end = port_text.split("&")

            # 記錄切換前的狀態
            prev_state = state
            logger.debug(f"切換防火牆前狀態: {prev_state}")
            
            # 檢查是否由快捷鍵觸發
            if from_hotkey:
                logger.debug(f"由快捷鍵觸發防火牆切換，將顯示通知: {self.notifications_enabled}")
            else:
                logger.debug("由UI觸發防火牆切換，不會顯示通知")

            if state == "STATE_BLOCKED":
                try:
                    logger.info(f"解除阻斷 UDP 埠 {port_start}-{port_end}")
                    self.firewall.delete_rule()
                    self.window.set_toggle_state("STATE_NORMAL")
                    if self.auto_recover_timer.isActive():
                        logger.debug("取消自動恢復計時器")
                        self.auto_recover_timer.stop()
                    
                    # 快捷鍵觸發時顯示
                    if from_hotkey and self.notifications_enabled:
                        logger.debug("發送解除阻斷的通知")
                        self.tray.show_message(
                            title="配對已恢復",
                            msg="已解除對 Warframe 配對的阻斷",
                            icon=QIcon(ICON_PATH),
                            timeout=5000
                        )
                except RuleDeletionError as e:
                    logger.error(f"移除防火牆規則失敗: {e}")
                    self._show_error(f"無法移除防火牆規則: {e}")
                    return
                except Exception as e:
                    logger.error(f"解除阻斷時發生未知錯誤: {e}")
                    self._show_error(f"發生未知錯誤: {e}")
                    return
            else:
                try:
                    logger.info(f"阻斷 UDP 埠 {port_start}-{port_end}")
                    self.firewall.create_rule(port_start, port_end)
                    self.firewall.enable_rule()
                    self.window.set_toggle_state("STATE_BLOCKED")
                    
                    # 快捷鍵觸發時顯示
                    if from_hotkey and self.notifications_enabled:
                        logger.debug("發送阻斷的通知")
                        self.tray.show_message(
                            title="配對已阻斷",
                            msg=f"已阻斷 UDP 埠 {port_start}-{port_end}",
                            icon=QIcon(BLOCKED_ICON_PATH),
                            timeout=5000
                        )
                    
                    if self.window.is_auto_recover_enabled():
                        seconds = max(self.window.get_auto_recover_time(), 1)
                        self.auto_recover_timer.start(seconds * 1000)
                        logger.info(f"已設定 {seconds} 秒後自動恢復")
                except RuleCreationError as e:
                    logger.error(f"建立防火牆規則失敗: {e}")
                    self._show_error(f"無法建立防火牆規則: {e}")
                    return
                except Exception as e:
                    logger.error(f"阻斷配對時發生未知錯誤: {e}")
                    self._show_error(f"發生未知錯誤: {e}")
                    return

            # 記錄切換後的狀態
            current_state = self.window.current_state
            logger.debug(f"切換防火牆後狀態: {current_state}")
            
            # 確保狀態有變更時才更新Tray
            if prev_state != current_state:
                logger.debug("狀態已變更，更新Tray圖示")
                # 更新Tray圖示狀態
                self._update_tray_status()
            else:
                logger.debug("狀態未變更，強制更新Tray圖示")
                # 強制更新Tray圖示
                self._update_tray_status()

            # 保存設定
            s = self.config["Settings"]
            s["udp_index"] = str(self.window.combo.currentIndex())
            s["auto_recover"] = str(self.window.is_auto_recover_enabled()).lower()
            s["recover_time"] = str(self.window.get_auto_recover_time())
            self._save_config()
            
            logger.debug("防火牆狀態切換完成")
        except Exception as e:
            logger.error(f"_safe_toggle_firewall方法發生錯誤: {e}")
            logger.exception("詳細錯誤")
            self._show_error(f"切換防火牆狀態時發生錯誤: {e}")

    def _on_recover_timeout(self):
        """自動恢復計時器超時處理"""
        try:
            logger.debug("自動恢復計時器觸發")
            if self.window.current_state == "STATE_BLOCKED":
                try:
                    logger.info("自動恢復防火牆規則")
                    # 記錄切換前的狀態
                    prev_state = self.window.current_state
                    
                    # 執行防火牆規則刪除
                    self.firewall.delete_rule()
                    self.window.set_toggle_state("STATE_NORMAL")
                    
                    # 記錄切換後的狀態
                    current_state = self.window.current_state
                    logger.debug(f"自動恢復切換後狀態: {current_state}")
                    
                    # 確保無論如何都更新Tray圖示
                    logger.debug("自動恢復：更新Tray圖示")
                    # 更新Tray圖示狀態
                    self._update_tray_status()
                    
                    # 自動恢復時顯示通知
                    if self.notifications_enabled:
                        self.tray.show_message(
                            title="Warframe 配對已恢復",
                            msg="UDP 配對封鎖已自動解除，已恢復為正常連線狀態。",
                            icon=QIcon(ICON_PATH),
                            timeout=5000
                        )
                    
                    # 額外檢查Tray圖示是否正常更新
                    is_blocked = (self.window.current_state == "STATE_BLOCKED")
                    logger.debug(f"自動恢復後再次檢查狀態: {'阻斷中' if is_blocked else '正常'}")
                    
                except RuleDeletionError as e:
                    logger.error(f"自動恢復時刪除規則失敗: {e}")
                    self._show_error(f"自動恢復失敗: {e}\n請手動檢查防火牆")
                except Exception as e:
                    logger.error(f"自動恢復時發生未知錯誤: {e}")
                    logger.exception("詳細錯誤")
                    self._show_error(f"自動恢復時發生錯誤: {e}")
        except Exception as e:
            logger.error(f"處理自動恢復計時器時發生錯誤: {e}")
            logger.exception("詳細錯誤")

    def on_auto_recover_changed(self, enabled: bool):
        """自動恢復設定變更處理"""
        try:
            logger.debug(f"自動恢復設定變更為: {enabled}")
            if not enabled and self.auto_recover_timer.isActive():
                logger.debug("取消自動恢復計時器")
                self.auto_recover_timer.stop()
        except Exception as e:
            logger.error(f"處理自動恢復設定變更時發生錯誤: {e}")
            logger.exception("詳細錯誤")

    def open_firewall_ui(self):
        """開啟防火牆UI"""
        self.firewall.open_firewall_ui()

    def open_settings(self):
        """開啟設定視窗"""
        try:
            logger.debug("開啟設定視窗")
            if not self.settings_window:
                logger.debug("初始化設定視窗")
                self.settings_window = SettingsUI(
                    notify_callback=self.toggle_notifications,
                    hotkey_callback=self.set_hotkey,
                    clear_config_callback=self.clear_config
                )
                # 設定初始狀態
                self.settings_window.notify_checkbox.setChecked(self.notifications_enabled)
                if self.hotkey:
                    formatted_hotkey = HotkeyManager.format_hotkey_display(self.hotkey)
                    self.settings_window.hotkey_display.setText(f"目前設定：{formatted_hotkey}")
            else:
                # 更新設定視窗狀態以確保它反映最新的設定
                logger.debug("更新現有設定視窗狀態")
                self.settings_window.notify_checkbox.setChecked(self.notifications_enabled)
                if self.hotkey:
                    formatted_hotkey = HotkeyManager.format_hotkey_display(self.hotkey)
                    self.settings_window.hotkey_display.setText(f"目前設定：{formatted_hotkey}")
        
            self.settings_window.show()
            self.settings_window.activateWindow()
            logger.debug("設定視窗已顯示")
        except Exception as e:
            logger.error(f"開啟設定視窗時發生錯誤: {e}")
            logger.exception("詳細錯誤")
            self._show_error(f"無法開啟設定視窗: {e}")

    def toggle_notifications(self, enabled):
        """切換通知設定"""
        self.notifications_enabled = enabled
        s = self.config["Settings"]
        s["notifications"] = str(enabled).lower()
        self._save_config()
        logger.info(f"通知設定已更改為: {enabled}")

    def set_hotkey(self, hotkey):
        """設定快捷鍵"""
        try:
            # 先取消之前的快捷鍵
            self._unregister_hotkey()
            
            # 設定新的快捷鍵
            self.hotkey = hotkey
            self.config["Settings"]["hotkey"] = hotkey
            self._save_config()
            
            # 註冊新快捷鍵
            if hotkey:
                self._register_hotkey()
            
            formatted_hotkey = HotkeyManager.format_hotkey_display(hotkey) if hotkey else "無"
            logger.info(f"快捷鍵已更新: {formatted_hotkey}")
        except Exception as e:
            logger.error(f"設定快捷鍵時發生錯誤: {e}")
            logger.exception("詳細錯誤")
            self._show_error(f"設定快捷鍵失敗: {e}")

    def _register_hotkey(self):
        """註冊全局快捷鍵"""
        try:
            if not self.hotkey:
                logger.debug("沒有配置快捷鍵，跳過註冊")
                return
                
            def hotkey_callback():
                # 使用訊號在不同線程間安全通信，標記為來自快捷鍵
                logger.debug("快捷鍵觸發，發送訊號並標記為快捷鍵來源")
                self.hotkey_handler.emit_toggle(True)
                
            result = self.hotkey_handler.register_hotkey(self.hotkey, hotkey_callback)
            if result:
                # 顯示格式化的快捷鍵
                formatted_hotkey = HotkeyManager.format_hotkey_display(self.hotkey)
                logger.debug(f"已註冊快捷鍵: {formatted_hotkey}")
                
                # 註冊快捷鍵時直接顯示通知 (確保Tray已存在)
                if hasattr(self, 'tray') and self.tray and self.notifications_enabled:
                    try:
                        self.tray.show_message(
                            title="快捷鍵已啟用",
                            msg=f"已設定 {formatted_hotkey} 為切換阻斷狀態的快捷鍵",
                            icon=QIcon(ICON_PATH),
                            timeout=3000
                        )
                    except Exception as e:
                        logger.error(f"顯示快捷鍵註冊通知時發生錯誤: {e}")
        except Exception as e:
            logger.error(f"註冊快捷鍵時發生錯誤: {e}")
            logger.exception("詳細錯誤")

    def _unregister_hotkey(self):
        """取消註冊全局快捷鍵"""
        try:
            if self.hotkey:
                logger.debug(f"取消註冊快捷鍵: {self.hotkey}")
                self.hotkey_handler.unregister_hotkey()
        except Exception as e:
            logger.error(f"取消註冊快捷鍵時發生錯誤: {e}")
            logger.exception("詳細錯誤")

    def clear_config(self):
        """清除所有設定"""
        try:
            # 取消註冊快捷鍵
            self._unregister_hotkey()
            
            # 重置設定
            self.config["Settings"] = {
                "udp_index": "0",
                "auto_recover": "true", 
                "recover_time": "20",
                "notifications": "true",
                "hotkey": ""
            }
            self._save_config()
            
            # 重新初始化UI
            self._init_ui_state()
            self.hotkey = ""
            self.notifications_enabled = True
            
            # 如果設定視窗是開啟的，也要更新它的狀態
            if self.settings_window and self.settings_window.isVisible():
                self.settings_window.hotkey_display.setText("目前設定：無")
                self.settings_window.notify_checkbox.setChecked(True)
            
            logger.info("所有設定已清除")
        except Exception as e:
            logger.error(f"清除設定時發生錯誤: {e}")
            logger.exception("詳細錯誤")
            self._show_error(f"清除設定失敗: {e}")

    def _show_error(self, msg):
        """顯示錯誤訊息"""
        logger.error(msg)
        QMessageBox.warning(self.window, "錯誤", msg)

    def quit_app(self):
        """退出應用程式"""
        logger.info("應用程式關閉中")
        # 確保取消註冊快捷鍵
        self._unregister_hotkey()
        # 恢復防火牆規則（如果被阻斷）
        if self.window.current_state == "STATE_BLOCKED":
            try:
                self.firewall.delete_rule()
                logger.info("程式關閉前已恢復防火牆規則")
            except Exception as e:
                logger.error(f"程式關閉時恢復防火牆規則失敗: {e}")

        # 清理Tray圖示資源
        try:
            logger.info("清理Tray圖示資源")
            self.tray.cleanup()
        except Exception as e:
            logger.error(f"清理Tray資源時發生錯誤: {e}")
            
        # 退出應用程式
        QApplication.quit()

def set_logger():
    """初始化 Loguru，設定輸出到 AppData/Roaming 目錄（支援打包）"""
    
    log_filename = LOG_PATH  # 使用全局變數中定義的路徑
    
    # 確保日誌目錄存在
    log_dir = os.path.dirname(log_filename)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 清空舊內容（保證每次啟動乾淨）
    try:
        with open(log_filename, "w", encoding="utf-8") as f:
            f.write("")  # 寫入空字符串而非不帶參數調用
    except Exception as e:
        print(f"[Loguru] 無法清空 log 檔案：{e}")

    # 移除預設 log handler
    logger.remove()

    # 加入終端機輸出（DEBUG 級）
    if sys.stderr:
        logger.add(
            sys.stderr,
            level="DEBUG",
            format="{time:HH:mm:ss} | <level>{level:<8}</level> | <cyan>{file}:{function}:{line}</cyan> - <level>{message}</level>",
            colorize=True
        )
    else:
        print("[Loguru] 無法初始化終端輸出（sys.stderr is None）")

    # 加入 log 檔案輸出（INFO 級）
    logger.add(
        log_filename,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {file}:{function}:{line} - {message}",
        encoding="utf-8"
    )

    print(f"[Loguru] Log 初始化完成，輸出位置：{log_filename}")

if __name__ == "__main__":
    # 初始化 loguru
    set_logger()
    try:
        if not is_admin():
            restart_as_admin()
            sys.exit()

        # 啟動應用程式
        app = QApplication(sys.argv)
        app.setApplicationDisplayName("Warframe 配對阻斷器")
        app.setWindowIcon(QIcon(ICON_PATH))
        logger.info("Warframe 配對阻斷器啟動")
        try:
            controller = AppController()
            controller.run()
            sys.exit(app.exec())
        except Exception as e:
            logger.exception(f"Controller 初始化或執行時發生嚴重錯誤")
            QMessageBox.critical(None, "程式錯誤", 
                                f"應用程式執行時發生錯誤：\n{e}\n\n"
                                f"詳細資訊已記錄至 {LOG_PATH}")
            sys.exit(1)
            
    except Exception as e:
        # 未處理的例外
        logger.exception("未處理的例外")
        
        QMessageBox.critical(None, "啟動失敗", 
                            f"程式啟動時發生未處理的例外：\n{e}\n\n"
                            f"詳細資訊已記錄至 {LOG_PATH}")
        sys.exit(1)
