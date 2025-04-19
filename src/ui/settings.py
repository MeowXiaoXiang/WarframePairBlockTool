import threading
import keyboard
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QFont, QCursor, QColor, QPalette
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QCheckBox,
    QPushButton, QMessageBox,
    QHBoxLayout, QGraphicsDropShadowEffect, QApplication
)
from loguru import logger

class HotkeyCapture(QObject):
    """專用於快捷鍵捕獲的類別"""
    hotkey_captured = Signal(str)
    
    def start_capture(self):
        """開始捕獲快捷鍵（在子線程中執行）"""
        def capture():
            try:
                logger.debug("開始捕獲快捷鍵")
                hotkey = keyboard.read_hotkey(suppress=False)
                # 標準化快捷鍵格式
                formatted_hotkey = self._format_hotkey(hotkey)
                logger.debug(f"捕獲到快捷鍵: {hotkey}, 格式化後: {formatted_hotkey}")
                self.hotkey_captured.emit(formatted_hotkey)
            except Exception as e:
                # 捕獲錯誤但不中斷程式
                logger.error(f"捕獲快捷鍵時發生錯誤: {e}")
                self.hotkey_captured.emit("")
        
        threading.Thread(target=capture, daemon=True).start()
    
    def _format_hotkey(self, hotkey):
        """標準化快捷鍵格式，讓其更美觀"""
        if not hotkey:
            return ""
            
        parts = hotkey.split('+')
        formatted_parts = []
        
        for part in parts:
            part = part.strip()
            # 特殊按鍵首字母大寫
            if part.lower() in ['ctrl', 'alt', 'shift', 'win']:
                formatted_parts.append(part.capitalize())
            # 單個字母全部大寫
            elif len(part) == 1 and part.isalpha():
                formatted_parts.append(part.upper())
            # 其他按鍵首字母大寫
            else:
                formatted_parts.append(part.capitalize())
                
        return ' + '.join(formatted_parts)

class SettingsUI(QWidget):
    def __init__(self, notify_callback=None, hotkey_callback=None, clear_config_callback=None):
        super().__init__()
        logger.debug("初始化設定視窗")
        self.notify_callback = notify_callback
        self.hotkey_callback = hotkey_callback
        self.clear_config_callback = clear_config_callback
        self.drag_position = None
        self.is_focused = False
        
        # 創建快捷鍵捕獲器並連接信號
        self.hotkey_capturer = HotkeyCapture()
        self.hotkey_capturer.hotkey_captured.connect(self._on_hotkey_captured)
        
        self.init_ui()

    def init_ui(self):
        try:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setFixedSize(275, 220)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 讓視窗可以獲得焦點

            # 獲取系統調色板
            palette = QApplication.palette()
            card_bg_color = palette.color(QPalette.ColorRole.Window)
            card_border_color = palette.color(QPalette.ColorRole.Mid)
            text_color = palette.color(QPalette.ColorRole.WindowText)
            button_hover_bg = palette.color(QPalette.ColorRole.Highlight).lighter(120)
            button_pressed_bg = palette.color(QPalette.ColorRole.Highlight)
            input_bg_color = palette.color(QPalette.ColorRole.Base)
            input_border_color = palette.color(QPalette.ColorRole.Dark)

            # 使用更好的陰影效果
            self.shadow = QGraphicsDropShadowEffect()
            self.shadow.setBlurRadius(12)
            self.shadow.setColor(QColor(0, 0, 0, 30))
            self.shadow.setOffset(0, 0)

            self.card = QWidget()
            self.card.setObjectName("card")
            self.card.setGraphicsEffect(self.shadow)
            self.card.setStyleSheet(f"""
                QWidget#card {{
                    background-color: {card_bg_color.name()};
                    border-radius: 32px;
                    border: 1px solid {card_border_color.name()};
                }}
            """)

            outer_layout = QVBoxLayout(self)
            outer_layout.setContentsMargins(10, 10, 10, 10)
            outer_layout.addWidget(self.card)

            layout = QVBoxLayout(self.card)
            layout.setContentsMargins(16, 12, 16, 12)
            layout.setSpacing(6)

            font = QFont("Microsoft JhengHei", 9)

            # Title Bar
            title_bar = QHBoxLayout()
            title = QLabel("設定")
            title.setFont(QFont("Microsoft JhengHei", 11, QFont.Bold))
            title_bar.addWidget(title)
            title_bar.addStretch()

            close_btn = QPushButton("×")
            close_btn.setFixedSize(24, 24)
            close_btn.setCursor(QCursor(Qt.PointingHandCursor))
            close_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    font-size: 16px;
                    color: {text_color.name()};
                }}
                QPushButton:hover {{
                    background-color: {button_hover_bg.name()};
                    border-radius: 12px;
                }}
                QPushButton:pressed {{
                    background-color: {button_pressed_bg.name()};
                }}
            """)
            close_btn.clicked.connect(self.close)
            title_bar.addWidget(close_btn)
            layout.addLayout(title_bar)

            # 通知開關
            self.notify_checkbox = QCheckBox("啟用 Windows 通知")
            self.notify_checkbox.setFont(font)
            self.notify_checkbox.setChecked(True)
            self.notify_checkbox.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.notify_checkbox.stateChanged.connect(
                lambda state: self.notify_callback(state == 2) if self.notify_callback else None
            )
            
            
            layout.addWidget(self.notify_checkbox)

            # 快捷鍵區塊
            layout.addWidget(QLabel("設定快捷鍵（按下按鈕後輸入）", font=font))

            self.hotkey_display = QLabel("目前設定：無")
            self.hotkey_display.setFont(font)
            self.hotkey_display.setStyleSheet(f"""
                QLabel {{
                    border: 1px solid {input_border_color.name()};
                    border-radius: 6px;
                    background-color: {input_bg_color.name()};
                    padding: 4px 8px;
                    color: {text_color.name()};
                }}
            """)
            layout.addWidget(self.hotkey_display)

            self.hotkey_btn = QPushButton("點此設定快捷鍵")
            self.hotkey_btn.setFont(font)
            self.hotkey_btn.setCursor(QCursor(Qt.PointingHandCursor))
            self.hotkey_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {input_bg_color.name()};
                    border: 1px solid {input_border_color.name()};
                    border-radius: 12px;
                    padding: 6px;
                    color: {text_color.name()};
                }}
                QPushButton:hover {{
                    background-color: {button_hover_bg.name()};
                }}
                QPushButton:pressed {{
                    background-color: {button_pressed_bg.name()};
                }}
            """)
            self.hotkey_btn.clicked.connect(self._start_hotkey_capture)
            layout.addWidget(self.hotkey_btn)

            # 清除設定按鈕 - 保留紅色警告風格
            danger_main_color = "#B22222"  # 與main.py一致的紅色
            danger_hover_color = "#cc4444"
            danger_pressed_color = "#a11a1a"
            
            clear_btn = QPushButton("清除所有設定")
            clear_btn.setFont(font)
            clear_btn.setCursor(QCursor(Qt.PointingHandCursor))
            clear_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {danger_main_color};
                    border: none;
                    border-radius: 10px;
                    padding: 6px;
                    color: white;
                }}
                QPushButton:hover {{
                    background-color: {danger_hover_color};
                }}
                QPushButton:pressed {{
                    background-color: {danger_pressed_color};
                }}
            """)
            clear_btn.clicked.connect(self._on_clear_clicked)
            layout.addWidget(clear_btn)
            logger.debug("UI設定完成")
        except Exception as e:
            logger.error(f"初始化UI時發生錯誤: {e}")
            logger.exception("詳細錯誤")

    def _start_hotkey_capture(self):
        """開始捕獲快捷鍵"""
        try:
            logger.debug("開始捕獲快捷鍵")
            self.hotkey_btn.setText("請按下組合鍵...")
            self.hotkey_display.setText("目前設定：偵測中...")
            self.setDisabled(True)
            
            # 使用信號來處理跨線程通信
            self.hotkey_capturer.start_capture()
        except Exception as e:
            logger.error(f"啟動快捷鍵捕獲時發生錯誤: {e}")
            self.setDisabled(False)
            self.hotkey_btn.setText("點此設定快捷鍵")
    
    def _on_hotkey_captured(self, hotkey):
        """當快捷鍵被捕獲時處理（在UI線程中執行）"""
        try:
            if not hotkey:  # 如果出錯返回空字串
                logger.warning("快捷鍵捕獲失敗或用戶取消")
                self.hotkey_display.setText("目前設定：捕獲失敗")
                self.hotkey_btn.setText("點此設定快捷鍵")
                self.setDisabled(False)
                return
                
            logger.info(f"已捕獲到快捷鍵: {hotkey}")
            self.hotkey_display.setText(f"目前設定：{hotkey}")
            self.hotkey_btn.setText("點此設定快捷鍵")
            self.setDisabled(False)
            
            if self.hotkey_callback:
                self.hotkey_callback(hotkey)
        except Exception as e:
            logger.error(f"處理捕獲到的快捷鍵時發生錯誤: {e}")
            self.setDisabled(False)
            self.hotkey_btn.setText("點此設定快捷鍵")

    def _on_clear_clicked(self):
        try:
            logger.debug("用戶點擊清除所有設定按鈕")
            if QMessageBox.question(self, "確認清除", "確定要刪除所有設定嗎？") == QMessageBox.Yes:
                logger.info("用戶確認清除所有設定")
                if self.clear_config_callback:
                    self.clear_config_callback()
                # 更新UI狀態以反應清除效果
                self.hotkey_display.setText("目前設定：無")
                self.notify_checkbox.setChecked(True)
                QMessageBox.information(self, "完成", "設定已清除！")
        except Exception as e:
            logger.error(f"清除設定時發生錯誤: {e}")
            QMessageBox.warning(self, "錯誤", f"清除設定時發生錯誤: {e}")

    def updateShadow(self, focused: bool):
        """更新視窗陰影效果"""
        self.is_focused = focused
        alpha = 100 if focused else 30
        blur = 30 if focused else 12
        self.shadow.setColor(QColor(0, 0, 0, alpha))
        self.shadow.setBlurRadius(blur)

    def focusInEvent(self, event):
        """視窗獲得焦點時更新陰影"""
        super().focusInEvent(event)
        logger.debug("設定視窗獲得焦點")
        self.updateShadow(True)

    def focusOutEvent(self, event):
        """視窗失去焦點時更新陰影"""
        super().focusOutEvent(event)
        logger.debug("設定視窗失去焦點")
        self.updateShadow(False)

    def mousePressEvent(self, event):
        """點擊處理（包含拖動和焦點獲取）"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setFocus()  # 滑鼠點擊時獲得焦點
        
        event.accept()

    def mouseMoveEvent(self, event):
        """拖動視窗處理"""
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
        
        event.accept()

    def mouseReleaseEvent(self, event):
        """滑鼠放開處理"""
        self.drag_position = None
        event.accept()
    
    def closeEvent(self, event):
        """窗口關閉事件處理，只隱藏不關閉"""
        try:
            # 檢查是否為獨立運行模式
            if __name__ == "__main__":
                logger.debug("設定視窗關閉事件觸發，關閉程式 (獨立運行模式)")
                print("關閉視窗，退出程式...")
                # 允許關閉事件正常處理，而不是立即退出
                event.accept()
                # 在事件處理後使用QTimer安排應用程式退出
                QTimer.singleShot(0, QApplication.instance().quit)
            else:
                logger.debug("設定視窗關閉事件觸發，隱藏視窗")
                event.ignore()  # 忽略原始關閉事件
                self.hide()     # 只隱藏視窗，不關閉它
        except Exception as e:
            logger.error(f"處理設定視窗關閉事件時發生錯誤: {e}")
            logger.exception("詳細錯誤")

if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys

    def notify_changed(enabled):
        print(f"[通知] 狀態改為：{enabled}")

    def hotkey_set(hotkey):
        print(f"[快捷鍵] 設定為：{hotkey}")

    def clear_all():
        print("[設定] 已清除")

    print("測試模式啟動：按X鍵將直接關閉程式")

    app = QApplication(sys.argv)
    window = SettingsUI(
        notify_callback=notify_changed,
        hotkey_callback=hotkey_set,
        clear_config_callback=clear_all
    )
    
    window.show()
    sys.exit(app.exec())

