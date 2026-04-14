"""
widgets.py

Reusable UI components for Primery.
"""
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QAction

class HintLabel(QLabel):
    """A helper label that shows a tooltip-like hint on hover."""
    def __init__(self, text, hint="", parent=None):
        super().__init__(text, parent)
        self.hint = hint
        self.setMouseTracking(True)
        if hint:
            self.setToolTip(hint)
            # We could implement a custom popup here if QToolTip isn't "IDE" enough

class Separator(QFrame):
    def __init__(self, vertical=False):
        super().__init__()
        if vertical:
            self.setFrameShape(QFrame.VLine)
        else:
            self.setFrameShape(QFrame.HLine)
        self.setFrameShadow(QFrame.Sunken)
