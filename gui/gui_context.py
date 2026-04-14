"""
gui_context.py

Global state management for the GUI.
"""
from PySide6.QtCore import QObject, Signal

class GUIContext(QObject):
    # Signals for global events
    workspace_changed = Signal(str)
    language_changed = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.workspace_path = ""
        self.lang = "en" # Default to English as requested
        self.email = ""
        self.api_key = ""
        
    def set_workspace(self, path: str):
        self.workspace_path = path
        self.workspace_changed.emit(path)

    def set_language(self, lang: str):
        self.lang = lang
        self.language_changed.emit(lang)

context = GUIContext()
