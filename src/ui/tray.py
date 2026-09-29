import threading
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QAction, QPalette
from PySide6.QtCore import Signal, QObject, QTimer, QThread, QEvent
from loguru import logger

class TrayManager(QObject):
    """管理系統托盤圖示、選單與通知。"""
    
    show_window_signal = Signal()
    toggle_firewall_signal = Signal(bool)
    open_firewall_signal = Signal()
    open_settings_signal = Signal()
    quit_app_signal = Signal()
    
    def __init__(self, parent=None, resolve_path=lambda x: x):
        super().__init__(parent)
        thread_id = threading.get_ident()
        logger.debug(f"初始化Tray管理器 [線程ID: {thread_id}]")
        
        self.resolve_path = resolve_path
        self.tray_icon = None
        self.menu = None
        self.status_action = None
        self.toggle_action = None
        self.is_blocked = False
        self.parent_window = parent
        self._current_icon_key = None
        
        self.icon_path = self.resolve_path("assets/logo.ico")
        self.blocked_icon_path = self.resolve_path("assets/logo_blocked.ico")

        self._icon_normal = QIcon(self.icon_path)
        self._icon_blocked = QIcon(self.blocked_icon_path)
        
        self._creation_thread = QThread.currentThread()
        QApplication.instance().installEventFilter(self)
        
    def _check_thread(self, method_name):
        """檢查當前線程是否為創建對象的線程"""
        current_thread = QThread.currentThread()
        if current_thread != self._creation_thread:
            logger.warning(f"{method_name}: 在非創建線程中調用!")
            return False
        return True
        
    def setup(self, parent_window=None):
        """初始化系統Tray"""
        try:
            thread_id = threading.get_ident()
            logger.debug(f"開始設置Tray [線程ID: {thread_id}]")
            
            if parent_window:
                self.parent_window = parent_window
                logger.debug(f"使用提供的父窗口: {parent_window}")
                
            # 重複建立圖示會在系統托盤留下多個入口。
            if hasattr(self, "_tray_initialized") and self._tray_initialized:
                logger.warning("Tray已初始化過！跳過重複初始化")
                return
                
            if isinstance(self.tray_icon, QSystemTrayIcon):
                logger.warning("Tray圖示已存在，跳過創建")
                return
                
            logger.debug("創建Tray圖示")
            self.tray_icon = QSystemTrayIcon(self._icon_normal, self.parent_window)
            self._current_icon_key = self._icon_normal.cacheKey()
            self.tray_icon.setToolTip("Warframe 配對阻斷器")
            
            self._tray_initialized = True
            
            menu = QMenu(self.parent_window)
            self.menu = menu
            self._apply_menu_theme()
            menu.setMinimumWidth(160)
            
            self.status_action = QAction("🟢 配對狀態：正常連線", self.parent_window)
            self.status_action.setEnabled(False)
            menu.addAction(self.status_action)
            menu.addSeparator()
            
            show_action = QAction("顯示主視窗", self.parent_window)
            show_action.triggered.connect(self.show_window_signal.emit)
            menu.addAction(show_action)
            
            settings_action = QAction("設定", self.parent_window)
            settings_action.triggered.connect(self.open_settings_signal.emit)
            menu.addAction(settings_action)
            
            self.toggle_action = QAction("切換為阻斷配對", self.parent_window)
            self.toggle_action.triggered.connect(lambda: self.toggle_firewall_signal.emit(False))
            menu.addAction(self.toggle_action)
            
            fw_action = QAction("查看防火牆", self.parent_window)
            fw_action.triggered.connect(self.open_firewall_signal.emit)
            menu.addAction(fw_action)
            
            menu.addSeparator()
            
            quit_action = QAction("結束程式", self.parent_window)
            quit_action.triggered.connect(self.quit_app_signal.emit)
            menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            
            self.tray_icon.show()
            logger.info(f"Tray圖示初始化完成")
        except Exception as e:
            logger.error(f"初始化Tray時發生錯誤: {e}")
            logger.exception("詳細錯誤")

    def _apply_menu_theme(self):
        if self.menu is None:
            return
        palette = QApplication.palette()
        menu_bg = palette.color(QPalette.ColorRole.Window)
        menu_text = palette.color(QPalette.ColorRole.WindowText)
        menu_border = palette.color(QPalette.ColorRole.Mid)
        menu_highlight = palette.color(QPalette.ColorRole.Highlight)
        selected_text = palette.color(QPalette.ColorRole.HighlightedText)
        self.menu.setStyleSheet(f"""
            QMenu {{
                background-color: {menu_bg.name()};
                border: 1px solid {menu_border.name()};
                padding: 4px;
                color: {menu_text.name()};
            }}
            QMenu::item {{
                padding: 6px 20px;
            }}
            QMenu::item:selected {{
                background-color: {menu_highlight.name()};
                color: {selected_text.name()};
            }}
        """)

    def eventFilter(self, obj, event):
        if obj is QApplication.instance() and event.type() == QEvent.Type.ApplicationPaletteChange:
            self._apply_menu_theme()
        return super().eventFilter(obj, event)
        
    def _on_tray_activated(self, reason):
        """Tray圖示被點擊時的處理"""
        try:
            if reason == QSystemTrayIcon.Trigger:
                logger.debug("Tray圖示被左鍵點擊，顯示主視窗")
                self.show_window_signal.emit()
        except Exception as e:
            logger.error(f"處理Tray圖示點擊時發生錯誤: {e}")
    
    def update_status(self, state, busy=False):
        """更新系統Tray狀態（同步更新圖示和選單項目）"""
        try:
            # Qt 的托盤元件必須在建立它的執行緒更新。
            if QThread.currentThread() != self.thread():
                logger.debug("從非主執行緒調用 update_status，重新調度至主執行緒")
                QTimer.singleShot(0, lambda: self.update_status(state, busy))
                return
            
            if self.tray_icon is None:
                logger.warning("Tray圖示不存在")
                return
                
            is_blocked = state is True or state == "STATE_BLOCKED"
            if state == "STATE_UNKNOWN":
                self.status_action.setText("⚪ 防火牆狀態：無法確認")
                self.toggle_action.setText("重新檢查")
                new_icon = self._icon_normal
            elif is_blocked:
                self.status_action.setText("🔴 配對狀態：已阻斷")
                self.toggle_action.setText("切換為正常配對")
                new_icon = self._icon_blocked
            else:
                self.status_action.setText("🟢 配對狀態：正常連線")
                self.toggle_action.setText("切換為阻斷配對")
                new_icon = self._icon_normal
            self.toggle_action.setEnabled(not busy)
            
            new_icon_key = new_icon.cacheKey()
            if self._current_icon_key != new_icon_key:
                logger.debug(f"更新Tray圖示 (新狀態: {'阻斷中' if is_blocked else '正常'})")
                self.tray_icon.setIcon(new_icon)
                self._current_icon_key = new_icon_key
            else:
                logger.debug("圖示未變更，僅更新選單文字")
            
            self.is_blocked = is_blocked
            logger.debug(f"Tray狀態更新完成: {'阻斷中' if is_blocked else '正常'}")
            
        except Exception as e:
            logger.error(f"更新Tray狀態時發生錯誤: {e}")
            logger.exception("詳細錯誤")
    
    def show_message(self, title, msg, icon=QSystemTrayIcon.Information, timeout=3000):
        """顯示系統Tray通知"""
        try:
            thread_id = threading.get_ident()
            
            if self.tray_icon is None:
                logger.warning("Tray圖示不存在，無法顯示通知")
                return
                
            logger.debug(f"顯示系統Tray通知: {title} [線程ID: {thread_id}]")
            self.tray_icon.showMessage(title, msg, icon, timeout)
        except Exception as e:
            logger.error(f"顯示Tray通知時發生錯誤: {e}")
    
    def cleanup(self):
        """清理Tray資源"""
        try:
            logger.debug("開始清理Tray資源")
            QApplication.instance().removeEventFilter(self)
            self.menu = None
            
            if self.tray_icon is None:
                logger.debug("Tray圖示不存在，跳過清理")
                return
                
            logger.debug("隱藏Tray圖示")
            self.tray_icon.hide()

            logger.debug("清除Tray資源：卸載選單和圖示")
            self.tray_icon.setContextMenu(None)
            self.tray_icon.setIcon(QIcon())
            
            logger.debug("刪除Tray圖示物件")
            self.tray_icon.deleteLater()
            self.tray_icon = None
            self._current_icon_key = None
            
            logger.info("Tray資源清理完成")
        except Exception as e:
            logger.error(f"清理Tray資源時發生錯誤: {e}")
            logger.exception("詳細錯誤")
