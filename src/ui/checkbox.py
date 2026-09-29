import os
import sys

from PySide6.QtGui import QPalette


def checkbox_style(palette):
    """Keep the checkbox mark readable against the current system theme."""
    text_color = palette.color(QPalette.ColorRole.WindowText)
    mark = "check_white.svg" if text_color.lightness() > 127 else "check_black.svg"
    root = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    mark_path = os.path.join(root, "assets", mark).replace("\\", "/")
    background = palette.color(QPalette.ColorRole.Window).name()
    border = palette.color(QPalette.ColorRole.Mid).name()
    return f"""
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            background-color: {background};
            border: 1px solid {border};
            border-radius: 4px;
        }}
        QCheckBox::indicator:checked {{
            image: url("{mark_path}");
        }}
    """
