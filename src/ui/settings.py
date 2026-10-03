import keyboard
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QEvent
from PySide6.QtGui import QFont, QCursor, QColor, QPalette
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QCheckBox,
    QPushButton, QMessageBox,
    QHBoxLayout, QGraphicsDropShadowEffect, QApplication
)
from loguru import logger
from src.ui.checkbox import checkbox_style

class HotkeyCapture(QObject):
    """以鍵盤 hook 捕捉組合鍵；Esc 與逾時都不變更原設定。"""
    hotkey_captured = Signal(str)
    _key_seen = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._hook = None
        self._pressed = set()
        self._key_seen.connect(self._handle_key)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.cancel)

    def start_capture(self):
        self.cancel(emit=False)
        self._pressed.clear()
        self._hook = keyboard.hook(lambda event: self._key_seen.emit(event.name, event.event_type),
                                   suppress=False)
        self._timer.start(15000)

    def _handle_key(self, name, event_type):
        if self._hook is None:
            return
        key = name.lower()
        if event_type == "up":
            self._pressed.discard(key)
            return
        if event_type != "down":
            return
        if key == "esc":
            self.cancel()
            return
        self._pressed.add(key)
        modifiers = {"ctrl", "left ctrl", "right ctrl", "alt", "left alt", "right alt",
                     "shift", "left shift", "right shift", "windows", "left windows", "right windows"}
        if key in modifiers:
            return
        names = []
        for label, variants in (("ctrl", ("ctrl", "left ctrl", "right ctrl")),
                                ("alt", ("alt", "left alt", "right alt")),
                                ("shift", ("shift", "left shift", "right shift")),
                                ("windows", ("windows", "left windows", "right windows"))):
            if self._pressed.intersection(variants):
                names.append(label)
        names.append(key)
        self.cancel(emit=False)
        self.hotkey_captured.emit(self._format_hotkey("+".join(names)))

    def cancel(self, emit=True):
        self._timer.stop()
        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None
        self._pressed.clear()
        if emit:
            self.hotkey_captured.emit("")
    
    def _format_hotkey(self, hotkey):
        """統一快捷鍵名稱的大小寫。"""
        if not hotkey:
            return ""
            
        parts = hotkey.split('+')
        formatted_parts = []
        
        for part in parts:
            part = part.strip()
            if part.lower() in ['ctrl', 'alt', 'shift', 'win']:
                formatted_parts.append(part.capitalize())
            elif len(part) == 1 and part.isalpha():
                formatted_parts.append(part.upper())
            else:
                formatted_parts.append(part.capitalize())
                
        return ' + '.join(formatted_parts)

class SettingsUI(QWidget):
    def __init__(self, notify_callback=None, hotkey_callback=None, clear_config_callback=None,
                 capture_start_callback=None, capture_end_callback=None):
        super().__init__()
        logger.debug("初始化設定視窗")
        self.notify_callback = notify_callback
        self.hotkey_callback = hotkey_callback
        self.clear_config_callback = clear_config_callback
        self.capture_start_callback = capture_start_callback
        self.capture_end_callback = capture_end_callback
        self._previous_hotkey_text = "目前設定：無"
        self.drag_position = None
        self.is_focused = False
        self._theme_palette_key = None
        
        self.hotkey_capturer = HotkeyCapture()
        self.hotkey_capturer.hotkey_captured.connect(self._on_hotkey_captured)
        
        self.init_ui()

    def init_ui(self):
        try:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setFixedSize(275, 220)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

            self.shadow = QGraphicsDropShadowEffect()
            self.shadow.setBlurRadius(12)
            self.shadow.setColor(QColor(0, 0, 0, 30))
            self.shadow.setOffset(0, 0)

            self.card = QWidget()
            self.card.setObjectName("card")
            self.card.setGraphicsEffect(self.shadow)

            outer_layout = QVBoxLayout(self)
            outer_layout.setContentsMargins(10, 10, 10, 10)
            outer_layout.addWidget(self.card)

            layout = QVBoxLayout(self.card)
            layout.setContentsMargins(16, 12, 16, 12)
            layout.setSpacing(6)

            font = QFont("Microsoft JhengHei", 9)

            title_bar = QHBoxLayout()
            title = QLabel("設定")
            title.setFont(QFont("Microsoft JhengHei", 11, QFont.Bold))
            title_bar.addWidget(title)
            title_bar.addStretch()

            self.close_btn = QPushButton("×")
            self.close_btn.setToolTip("關閉設定視窗（程式繼續執行）")
            self.close_btn.setFixedSize(24, 24)
            self.close_btn.setCursor(QCursor(Qt.PointingHandCursor))
            self.close_btn.clicked.connect(self.close)
            title_bar.addWidget(self.close_btn)
            layout.addLayout(title_bar)

            self.notify_checkbox = QCheckBox("顯示 Windows 通知")
            self.notify_checkbox.setToolTip("控制本工具的系統匣通知")
            self.notify_checkbox.setFont(font)
            self.notify_checkbox.setChecked(True)
            self.notify_checkbox.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.notify_checkbox.stateChanged.connect(
                lambda state: self.notify_callback(state == 2) if self.notify_callback else None
            )
            
            
            layout.addWidget(self.notify_checkbox)

            layout.addWidget(QLabel("配對切換快捷鍵", font=font))

            self.hotkey_display = QLabel("目前設定：無")
            self.hotkey_display.setFont(font)
            layout.addWidget(self.hotkey_display)

            self.hotkey_btn = QPushButton("設定快捷鍵")
            self.hotkey_btn.setToolTip("按下後輸入快捷鍵；可按 Esc 取消，15 秒後自動取消")
            self.hotkey_btn.setFont(font)
            self.hotkey_btn.setCursor(QCursor(Qt.PointingHandCursor))
            self.hotkey_btn.clicked.connect(self._start_hotkey_capture)
            layout.addWidget(self.hotkey_btn)

            danger_main_color = "#B22222"
            danger_hover_color = "#cc4444"
            danger_pressed_color = "#a11a1a"
            
            clear_btn = QPushButton("還原預設設定")
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
            self._apply_theme()
            logger.debug("UI設定完成")
        except Exception as e:
            logger.error(f"初始化UI時發生錯誤: {e}")
            logger.exception("詳細錯誤")

    def _apply_theme(self):
        palette = QApplication.palette()
        self._theme_palette_key = palette.cacheKey()
        self.notify_checkbox.setStyleSheet(checkbox_style(palette))
        card_bg_color = palette.color(QPalette.ColorRole.Window)
        card_border_color = palette.color(QPalette.ColorRole.Mid)
        text_color = palette.color(QPalette.ColorRole.WindowText)
        button_hover_bg = palette.color(QPalette.ColorRole.Highlight).lighter(120)
        button_pressed_bg = palette.color(QPalette.ColorRole.Highlight)
        input_bg_color = palette.color(QPalette.ColorRole.Base)
        input_border_color = palette.color(QPalette.ColorRole.Dark)

        self.card.setStyleSheet(f"""
            QWidget#card {{
                background-color: {card_bg_color.name()};
                border-radius: 32px;
                border: 1px solid {card_border_color.name()};
            }}
        """)
        self.close_btn.setStyleSheet(f"""
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
        self.hotkey_display.setStyleSheet(f"""
            QLabel {{
                border: 1px solid {input_border_color.name()};
                border-radius: 6px;
                background-color: {input_bg_color.name()};
                padding: 4px 8px;
                color: {text_color.name()};
            }}
        """)
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

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.Type.PaletteChange
                and hasattr(self, "hotkey_btn")
                and self._theme_palette_key != QApplication.palette().cacheKey()):
            self._apply_theme()

    def _start_hotkey_capture(self):
        """開始捕獲快捷鍵"""
        try:
            if self.hotkey_capturer._hook is not None:
                self.hotkey_capturer.cancel()
                return
            logger.debug("開始捕獲快捷鍵")
            self._previous_hotkey_text = self.hotkey_display.text()
            if self.capture_start_callback:
                self.capture_start_callback()
            self.hotkey_btn.setText("取消設定（Esc）")
            self.hotkey_display.setText("請按下快捷鍵（Esc 取消）")
            self.hotkey_capturer.start_capture()
        except Exception as e:
            logger.error(f"啟動快捷鍵捕獲時發生錯誤: {e}")
            if self.capture_end_callback:
                self.capture_end_callback()
            self.hotkey_display.setText(self._previous_hotkey_text)
            self.hotkey_btn.setText("設定快捷鍵")
    
    def _on_hotkey_captured(self, hotkey):
        """當快捷鍵被捕獲時處理（在UI線程中執行）"""
        try:
            self.hotkey_btn.setText("設定快捷鍵")
            if not hotkey:
                self.hotkey_display.setText(self._previous_hotkey_text)
                if self.capture_end_callback:
                    self.capture_end_callback()
                return
            if self.hotkey_callback and self.hotkey_callback(hotkey) is False:
                self.hotkey_display.setText(self._previous_hotkey_text)
            else:
                self.hotkey_display.setText(f"目前設定：{hotkey}")
            if self.capture_end_callback:
                self.capture_end_callback()
        except Exception as e:
            logger.error(f"處理捕獲到的快捷鍵時發生錯誤: {e}")
            self.hotkey_display.setText(self._previous_hotkey_text)
            self.hotkey_btn.setText("設定快捷鍵")
            if self.capture_end_callback:
                self.capture_end_callback()

    def _on_clear_clicked(self):
        try:
            logger.debug("使用者點擊還原預設設定按鈕")
            if QMessageBox.question(
                    self, "還原預設設定",
                    "確定要還原預設設定嗎？\nUDP 埠、自動恢復及通知將恢復預設值，快捷鍵將被移除。") == QMessageBox.Yes:
                logger.info("使用者確認還原預設設定")
                if self.clear_config_callback:
                    self.clear_config_callback()
                self.hotkey_display.setText("目前設定：無")
                self.notify_checkbox.setChecked(True)
                QMessageBox.information(self, "完成", "設定已還原為預設值。")
        except Exception as e:
            logger.error(f"還原預設設定失敗：{e}")
            QMessageBox.warning(self, "無法還原設定", f"還原預設設定失敗：{e}")

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
            self.setFocus()
        
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
        """一般模式隱藏視窗，獨立測試模式結束程式。"""
        try:
            if self.hotkey_capturer._hook is not None:
                self.hotkey_capturer.cancel()
            # 檢查是否為獨立運行模式
            if __name__ == "__main__":
                logger.debug("設定視窗關閉事件觸發，關閉程式 (獨立運行模式)")
                print("關閉視窗，退出程式...")
                event.accept()
                # 關閉事件結束後再退出獨立執行的測試程式。
                QTimer.singleShot(0, QApplication.instance().quit)
            else:
                logger.debug("設定視窗關閉事件觸發，隱藏視窗")
                event.ignore()
                self.hide()
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

