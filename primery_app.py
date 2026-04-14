"""
primery_app.py

Entry point for the Primery application.
"""
import sys
import os

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout,
                                QPushButton, QLabel, QSpacerItem, QSizePolicy)
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtCore import Qt
from PySide6.QtSvgWidgets import QSvgWidget


def _load_inter_bold():
    """Load bundled Inter-Bold.ttf and return the family name, or fallback."""
    font_path = os.path.join(os.path.dirname(__file__), "assets", "fonts", "Inter-Bold.ttf")
    if os.path.isfile(font_path):
        fid = QFontDatabase.addApplicationFont(font_path)
        families = QFontDatabase.applicationFontFamilies(fid)
        if families:
            return families[0]
    return "Segoe UI"   # fallback


class StartScreen(QDialog):
    """Splash screen that renders the user's SVG at its native aspect ratio
    with a Start button overlaid at the bottom."""

    # Original SVG dimensions
    SVG_W, SVG_H = 2193, 1286
    SCALE = 0.32  # render at ~700px wide

    def __init__(self, font_family):
        super().__init__(None, Qt.FramelessWindowHint)

        w = int(self.SVG_W * self.SCALE)
        h = int(self.SVG_H * self.SCALE)
        self.setFixedSize(w, h)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # SVG fills the entire dialog
        svg_path = os.path.join(os.path.dirname(__file__), "assets", "Loading.svg")
        if os.path.exists(svg_path):
            svg = QSvgWidget(svg_path)
            svg.setFixedSize(w, h)
            layout.addWidget(svg)
        else:
            self.setStyleSheet("background: white;")
            lbl = QLabel("Primery")
            lbl.setFont(QFont(font_family, 44))
            lbl.setStyleSheet("color: #184F27;")
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)

        # Start button overlaid at the bottom center
        self.btn_start = QPushButton("Start", self)
        self.btn_start.setFixedSize(160, 46)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setFont(QFont(font_family, 16))
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background-color: #216635;
                color: white;
                border: none;
                border-radius: 10px;
                font-family: '{font_family}';
                font-size: 16px;
                font-weight: bold;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{
                background-color: #2a8045;
            }}
            QPushButton:pressed {{
                background-color: #184F27;
            }}
        """)
        self.btn_start.clicked.connect(self.accept)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position the button at the bottom center
        bw, bh = self.btn_start.width(), self.btn_start.height()
        x = (self.width() - bw) // 2
        y = self.height() - bh - 30
        self.btn_start.move(x, y)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Set application icon
    icon_path = os.path.join(os.path.dirname(__file__), "assets", "Logo.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    font_family = _load_inter_bold()

    start = StartScreen(font_family)
    if start.exec() != QDialog.Accepted:
        sys.exit(0)

    from gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
