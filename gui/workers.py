"""
workers.py

Background workers for Primery GUI.
"""

from PySide6.QtCore import QThread, Signal, QObject

class BaseWorker(QThread):
    finished_result = Signal(object)
    error_occurred = Signal(str)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        
    def run(self):
        try:
            res = self.func(*self.args, **self.kwargs)
            self.finished_result.emit(res)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))

# Specialized workers if needed, but BaseWorker covers most functional calls
