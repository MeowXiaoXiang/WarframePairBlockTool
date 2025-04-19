import os
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QCursor, QDesktopServices, QColor, QPalette
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QCheckBox, QSpinBox,
    QGraphicsDropShadowEffect, 
)

from loguru import logger

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


# 可點擊 SVG Icon
class ClickableSvgWidget(QSvgWidget):
    """
    可點擊的 SVG 圖示元件。
    - 可設定網址（url）或 callback 函式。
    - 可選擇設定 tooltip 說明文字。
    """
    def __init__(self, path, url=None, callback=None, tooltip=None, parent=None):
        super().__init__(path, parent)
        self.url = url
        self.callback = callback
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if tooltip:
            self.setToolTip(tooltip)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.callback:
                self.callback()
            elif self.url:
                QDesktopServices.openUrl(QUrl(self.url))


class WarframeMainUI(QWidget):
    """
    主介面：Warframe 配對阻斷工具 UI。

    支援傳入 callback 控制：
    - toggle_callback: 切換配對阻斷狀態
    - auto_recover_callback: 開關「自動恢復」與設定時間
    - open_firewall_callback: 開啟防火牆介面
    - open_settings_callback: 開啟設定面板
    - state_labels: 配對狀態對應字串
    """
    def __init__(
        self,
        toggle_callback=None,
        auto_recover_callback=None,
        open_firewall_callback=None,
        open_settings_callback=None,
        state_labels=None,
        resolve_path=lambda x: x
    ):
        super().__init__()
        self.resolve_path = resolve_path
        self.drag_position = None
        self.toggle_callback = toggle_callback
        self.auto_recover_callback = auto_recover_callback
        self.open_firewall_callback = open_firewall_callback
        self.open_settings_callback = open_settings_callback
        self.state_labels = state_labels or {
            "STATE_BLOCKED": "配對已阻斷",
            "STATE_NORMAL": "配對正常"
        }
        self.current_state = "STATE_NORMAL"
        self.is_focused = False
        self.init_ui()

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(275, 300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 讓視窗可以獲得焦點

        # 獲取系統調色板
        palette = QApplication.palette()
        card_bg_color = palette.color(QPalette.ColorRole.Window)
        card_border_color = palette.color(QPalette.ColorRole.Mid)
        text_color = palette.color(QPalette.ColorRole.WindowText)
        input_bg_color = palette.color(QPalette.ColorRole.Base)
        input_border_color = palette.color(QPalette.ColorRole.Dark)
        highlight_color = palette.color(QPalette.ColorRole.Highlight)
        button_hover_bg = highlight_color.lighter(120)
        button_pressed_bg = highlight_color

        # 使用更好的陰影效果
        self.shadow = QGraphicsDropShadowEffect()
        self.shadow.setBlurRadius(12)
        self.shadow.setColor(QColor(0, 0, 0, 30))
        self.shadow.setOffset(0, 0)

        self.card = QWidget()
        self.card.setGraphicsEffect(self.shadow)
        self.card.setObjectName("card")
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

        main_layout = QVBoxLayout(self.card)
        main_layout.setContentsMargins(16, 6, 16, 12)
        main_layout.setSpacing(8)

        font = QFont("Microsoft JhengHei", 9)

        # Title Bar
        title_bar = QHBoxLayout()
        self.logo = QSvgWidget(self.resolve_path("assets/logo.svg"))
        self.logo.setFixedSize(26, 26)
        title_bar.addWidget(self.logo)

        self.title = QLabel("Warframe 配對阻斷器")
        self.title.setFont(QFont("Microsoft JhengHei", 9, QFont.Weight.Bold))
        title_bar.addWidget(self.title)
        title_bar.addStretch()

        minimize_btn = QPushButton("−")
        close_btn = QPushButton("×")
        
        for btn in (minimize_btn, close_btn):
            btn.setFixedSize(26, 26)
            btn.setFont(QFont("Arial", 15))
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    color: {text_color.name()};
                }}
                QPushButton:hover {{
                    background-color: {button_hover_bg.name()};
                    border-radius: 13px;
                }}
                QPushButton:pressed {{
                    background-color: {button_pressed_bg.name()};
                }}
            """)
        minimize_btn.clicked.connect(self.showMinimized)
        close_btn.clicked.connect(self.close)
        title_bar.addWidget(minimize_btn)
        title_bar.addWidget(close_btn)
        main_layout.addLayout(title_bar)

        # UDP Port Selection
        udp_layout = QVBoxLayout()
        udp_label = QLabel("選擇您 Warframe 內的 UDP 埠")
        udp_label.setFont(font)
        udp_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        udp_label.setFixedHeight(14)
        udp_layout.addWidget(udp_label)

        self.combo = QComboBox()
        self.combo.setFont(font)
        self.combo.addItems([
            "4950 & 4955", "4960 & 4965", "4970 & 4975",
            "4980 & 4985", "4990 & 4995", "3074 & 3080"
        ])
        # 獲取 arrow_down 圖片路徑並處理反斜線
        arrow_down_path = self.resolve_path("assets/arrow_down.svg").replace("\\", "/")
        
        self.combo.setStyleSheet(f"""
            QComboBox {{
                padding: 6px 10px;
                border: 1px solid {input_border_color.name()};
                border-radius: 6px;
                background-color: {input_bg_color.name()};
                color: {text_color.name()};
            }}
            QComboBox:hover {{
                border: 1px solid {highlight_color.name()};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border: none;
            }}
            QComboBox::down-arrow {{
                image: url({arrow_down_path});
                width: 18px;
                height: 18px;
            }}
            QAbstractItemView {{
                border: 1px solid {input_border_color.name()};
                selection-background-color: {highlight_color.name()};
                selection-color: {palette.color(QPalette.ColorRole.HighlightedText).name()};
                background-color: {input_bg_color.name()};
                padding: 4px;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 28px;
                padding: 4px 10px;
            }}
        """)

        udp_layout.addWidget(self.combo)
        main_layout.addLayout(udp_layout)

        # 自動恢復區塊
        auto_recover_layout = QHBoxLayout()
        auto_recover_layout.setSpacing(6)
        auto_recover_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.auto_recover_checkbox = QCheckBox("自動恢復配對（秒）")
        self.auto_recover_checkbox.setFont(font)
        self.auto_recover_checkbox.setChecked(True)
        self.auto_recover_checkbox.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.auto_recover_checkbox.stateChanged.connect(self._on_auto_recover_toggled)

        self.recover_spinbox = QSpinBox()
        self.recover_spinbox.setFont(font)
        self.recover_spinbox.setRange(1, 999)
        self.recover_spinbox.setValue(20)
        self.recover_spinbox.setFixedWidth(60)
        self.recover_spinbox.setEnabled(True)

        up_path = self.resolve_path("assets/arrow_up.svg").replace("\\", "/")
        down_path = self.resolve_path("assets/arrow_down.svg").replace("\\", "/")
        self.recover_spinbox.setStyleSheet(f"""
            QSpinBox {{
                padding: 4px;
                border: 1px solid {input_border_color.name()};
                border-radius: 10px;
                background-color: {input_bg_color.name()};
                color: {text_color.name()};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                border: none;
                background: transparent;
                subcontrol-origin: border;
                width: 20px;
                height: 16px;
            }}
            QSpinBox::up-button {{
                subcontrol-position: top right;
                image: url({up_path});
            }}
            QSpinBox::down-button {{
                subcontrol-position: bottom right;
                image: url({down_path});
            }}
        """)

        auto_recover_layout.addWidget(self.auto_recover_checkbox)
        auto_recover_layout.addWidget(self.recover_spinbox)
        main_layout.addLayout(auto_recover_layout)

        main_layout.addSpacing(8)

        # Control Buttons
        control_layout = QVBoxLayout()
        self.toggle_btn = QPushButton("配對正常")
        self.toggle_btn.setFont(QFont("Microsoft JhengHei", 9, QFont.Weight.Bold))
        self.toggle_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setMinimumHeight(36)
        self.toggle_btn.setStyleSheet(self.get_toggle_style(False))
        self.toggle_btn.clicked.connect(self.toggle_status)
        control_layout.addWidget(self.toggle_btn)

        # 在按鈕間添加間隔
        control_layout.addSpacing(16)

        self.firewall_btn = QPushButton("查看防火牆")
        self.firewall_btn.setFont(font)
        self.firewall_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.firewall_btn.setMinimumHeight(32)
        self.firewall_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {input_bg_color.name()};
                border: 1px solid {input_border_color.name()};
                border-radius: 12px;
                color: {text_color.name()};
            }}
            QPushButton:hover {{
                background-color: {button_hover_bg.name()};
            }}
            QPushButton:pressed {{
                background-color: {button_pressed_bg.name()};
            }}
        """)
        self.firewall_btn.clicked.connect(self._on_firewall_clicked)
        control_layout.addWidget(self.firewall_btn)
        main_layout.addLayout(control_layout)

        main_layout.addSpacing(12)
        main_layout.addStretch()

        # Footer
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(4, 2, 4, 4)
        footer_layout.setSpacing(6)

        settings_icon = ClickableSvgWidget(
            self.resolve_path("assets/settings.svg"),
            callback=self._on_settings_clicked,
            tooltip="開啟設定"
        )
        settings_icon.setFixedSize(18, 18)
        footer_layout.addWidget(settings_icon)

        author_widget = QWidget()
        author_layout = QVBoxLayout()
        author_layout.setContentsMargins(0, 0, 0, 0)
        author_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        author_label = QLabel("開發者：小翔\nDiscord: xiaoxiang_meow")
        author_label.setFont(QFont("Microsoft JhengHei", 8))
        author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author_layout.addWidget(author_label)
        author_widget.setLayout(author_layout)

        footer_layout.addWidget(author_widget, stretch=1)

        github_icon = ClickableSvgWidget(
            self.resolve_path("assets/github.svg"),
            url="https://github.com/MeowXiaoXiang/WarframePairBlockTool",
            tooltip="前往 GitHub"
        )
        github_icon.setFixedSize(18, 18)
        footer_layout.addWidget(github_icon)

        main_layout.addLayout(footer_layout)

    def _on_firewall_clicked(self):
        if self.open_firewall_callback:
            self.open_firewall_callback()

    def get_toggle_style(self, checked):
        # 狀態切換按鈕使用固定的白色文字，但保留紅綠色調
        # 紅/綠主色和深淺變體
        if checked:  # 阻斷狀態 - 紅色
            main_color = "#B22222"
            hover_color = "#cc4444" 
            pressed_color = "#a11a1a"
        else:  # 正常狀態 - 綠色
            main_color = "#4CAF50"
            hover_color = "#66bb6a"
            pressed_color = "#388e3c"
            
        return f"""
            QPushButton {{
                color: white;  /* 固定使用白色文字 */
                background-color: {main_color};
                border: none;
                border-radius: 18px;
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            QPushButton:pressed {{
                background-color: {pressed_color};
            }}
        """

    def toggle_status(self):
        if self.toggle_callback:
            self.toggle_callback()

    def _on_auto_recover_toggled(self):
        enabled = self.auto_recover_checkbox.isChecked()
        self.recover_spinbox.setEnabled(enabled)
        if self.auto_recover_callback:
            self.auto_recover_callback(enabled)

    def _on_settings_clicked(self):
        if self.open_settings_callback:
            self.open_settings_callback()

    def set_toggle_state(self, state_code: str):
        self.current_state = state_code
        checked = state_code == "STATE_BLOCKED"
        text = self.state_labels.get(state_code, "未知狀態")
        self.toggle_btn.setChecked(checked)
        self.toggle_btn.setText(text)
        self.toggle_btn.setStyleSheet(self.get_toggle_style(checked))

    def get_selected_udp_ports(self) -> str:
        return self.combo.currentText()

    def set_selected_udp_index(self, index: int):
        self.combo.setCurrentIndex(index)

    def get_auto_recover_time(self) -> int:
        return self.recover_spinbox.value()

    def set_auto_recover_time(self, seconds: int):
        self.recover_spinbox.setValue(seconds)

    def is_auto_recover_enabled(self) -> bool:
        return self.auto_recover_checkbox.isChecked()

    def set_auto_recover_enabled(self, enabled: bool):
        self.auto_recover_checkbox.setChecked(enabled)

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
        logger.debug("視窗獲得焦點")
        self.updateShadow(True)

    def focusOutEvent(self, event):
        """視窗失去焦點時更新陰影"""
        super().focusOutEvent(event)
        logger.debug("視窗失去焦點")
        self.updateShadow(False)

    def mousePressEvent(self, event):
        """點擊處理（包含拖動和焦點獲取）"""
        if event.button() == Qt.MouseButton.LeftButton:
            widget = self.childAt(event.position().toPoint())
            allowed_widgets = (self.card, self.title, self.logo)
            if widget in allowed_widgets or widget.parent() in allowed_widgets:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.setFocus()  # 滑鼠點擊時獲得焦點
            else:
                self.drag_position = None
        
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

if __name__ == "__main__":
    import random

    logger.info("啟動測試模式")

    app = QApplication(sys.argv)

    counter = {"blocked": 0, "normal": 0}

    def resolve_path(relative_path):
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        return os.path.join(base, relative_path)

    def mock_toggle_callback():
        logger.debug(f"[TOGGLE] 現在狀態：{window.current_state}")
        logger.debug(f"[UDP] 當前選擇：{window.get_selected_udp_ports()}")
        if window.current_state == "STATE_BLOCKED":
            counter["normal"] += 1
            window.state_labels["STATE_NORMAL"] = f"配對正常 [{counter['normal']}]"
            window.set_toggle_state("STATE_NORMAL")
        else:
            counter["blocked"] += 1
            window.state_labels["STATE_BLOCKED"] = f"配對已阻斷 [{counter['blocked']}]"
            window.set_toggle_state("STATE_BLOCKED")

    def mock_auto_recover_callback(enabled: bool):
        logger.debug(f"[AUTO-RECOVER] 狀態變更：{enabled}, 時間: {window.get_auto_recover_time()} 秒")

    def mock_firewall_callback():
        logger.debug("[FIREWALL] 查看防火牆按鈕被觸發，模擬開啟 MMC...")

    def mock_settings_callback():
        logger.debug("[SETTINGS] 開啟設定面板按鈕觸發")

    label_dict = {
        "STATE_BLOCKED": "配對已阻斷",
        "STATE_NORMAL": "配對正常"
    }

    window = WarframeMainUI(
        toggle_callback=mock_toggle_callback,
        auto_recover_callback=mock_auto_recover_callback,
        open_firewall_callback=mock_firewall_callback,
        open_settings_callback=mock_settings_callback,
        resolve_path=resolve_path
    )

    window.set_toggle_state(random.choice(["STATE_BLOCKED", "STATE_NORMAL"]))
    window.set_selected_udp_index(2)  # 預設選擇 "4970 & 4975"
    window.set_auto_recover_enabled(False)
    window.set_auto_recover_time(99)

    logger.info("主視窗已建立，準備顯示")
    window.show()
    sys.exit(app.exec())