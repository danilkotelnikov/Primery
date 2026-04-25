"""
primery_app.py

Entry point for the Primery application.
"""
import sys
import os

# Ensure the project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

APP_VERSION = "0.2.0"

from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout,
                                QPushButton, QLabel, QSpacerItem, QSizePolicy)
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtCore import Qt
from PySide6.QtSvgWidgets import QSvgWidget


def _load_start_font():
    """Prefer Google Sans Flex, then bundled Inter, then the platform UI font."""
    root = os.path.dirname(__file__)
    candidates = [
        os.path.join(root, "assets", "fonts", "GoogleSansFlex-VariableFont_GRAD,ROND,opsz,slnt,wdth,wght.ttf"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts",
                     "GoogleSansFlex-VariableFont_GRAD,ROND,opsz,slnt,wdth,wght.ttf"),
        os.path.join(root, "assets", "fonts", "Inter-Bold.ttf"),
    ]
    for font_path in candidates:
        if os.path.isfile(font_path):
            fid = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                return families[0]
    return "Segoe UI"


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
            lbl = QLabel(f"Primery {APP_VERSION}")
            lbl.setFont(QFont(font_family, 44))
            lbl.setStyleSheet("color: #184F27;")
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)

        # Start button overlaid at the bottom center
        self.btn_start = QPushButton("Start", self)
        self.btn_start.setFixedSize(190, 52)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setFont(QFont(font_family, 16))
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #2E7D4F, stop:1 #0D3B6E);
                color: white;
                border: none;
                border-radius: 8px;
                font-family: '{font_family}';
                font-size: 17px;
                font-weight: 600;
                letter-spacing: 0px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #37945E, stop:1 #104A86);
            }}
            QPushButton:pressed {{
                background: #184F27;
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

    font_family = _load_start_font()

    start = StartScreen(font_family)
    if start.exec() != QDialog.Accepted:
        sys.exit(0)

    from gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
