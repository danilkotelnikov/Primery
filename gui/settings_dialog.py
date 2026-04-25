"""Application preferences backed by QSettings."""

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget, QKeySequenceEdit,
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(560, 420)
        self.settings = QSettings("Primery", "Primery")

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Editor
        tab_editor = QWidget()
        f_editor = QFormLayout(tab_editor)
        self.combo_editor_font = QComboBox()
        self.combo_editor_font.addItems(["Consolas", "Cascadia Mono", "Courier New", "Segoe UI"])
        self.sp_editor_size = QSpinBox()
        self.sp_editor_size.setRange(8, 28)
        self.chk_autosave = QCheckBox("Auto-save edited files")
        f_editor.addRow("Editor font:", self.combo_editor_font)
        f_editor.addRow("Editor font size:", self.sp_editor_size)
        f_editor.addRow(self.chk_autosave)
        tabs.addTab(tab_editor, "Editor")

        # Application
        tab_app = QWidget()
        f_app = QFormLayout(tab_app)
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["System", "Light", "Dark"])
        self.chk_open_viewers = QCheckBox("Open result viewers after analysis")
        f_app.addRow("Theme:", self.combo_theme)
        f_app.addRow(self.chk_open_viewers)
        tabs.addTab(tab_app, "Application")

        # Analysis
        tab_analysis = QWidget()
        f_analysis = QFormLayout(tab_analysis)
        self.sp_fastas = QSpinBox()
        self.sp_fastas.setRange(1, 500)
        self.sp_blast_hits = QSpinBox()
        self.sp_blast_hits.setRange(20, 1000)
        self.chk_deep_parse = QCheckBox("Use GenBank /gene= deep parse")
        f_analysis.addRow("FASTAs per cluster:", self.sp_fastas)
        f_analysis.addRow("BLAST max hits:", self.sp_blast_hits)
        f_analysis.addRow(self.chk_deep_parse)
        tabs.addTab(tab_analysis, "Analysis")

        # Keyboard
        tab_keys = QWidget()
        f_keys = QFormLayout(tab_keys)
        self.key_save = QKeySequenceEdit()
        self.key_find = QKeySequenceEdit()
        self.key_report = QKeySequenceEdit()
        f_keys.addRow("Save:", self.key_save)
        f_keys.addRow("Find:", self.key_find)
        f_keys.addRow("Generate report:", self.key_report)
        tabs.addTab(tab_keys, "Keyboard")

        btns = QHBoxLayout()
        self.btn_ok = QPushButton("Apply")
        self.btn_cancel = QPushButton("Cancel")
        btns.addStretch()
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self._load()

    def _load(self):
        self.combo_editor_font.setCurrentText(self.settings.value("editor/font", "Consolas"))
        self.sp_editor_size.setValue(int(self.settings.value("editor/fontSize", 11)))
        self.chk_autosave.setChecked(self.settings.value("editor/autosave", "false") == "true")
        self.combo_theme.setCurrentText(self.settings.value("app/theme", "System"))
        self.chk_open_viewers.setChecked(self.settings.value("app/openViewers", "true") == "true")
        self.sp_fastas.setValue(int(self.settings.value("analysis/fastasPerCluster", 10)))
        self.sp_blast_hits.setValue(int(self.settings.value("analysis/blastMaxHits", 200)))
        self.chk_deep_parse.setChecked(self.settings.value("analysis/deepParse", "false") == "true")
        self.key_save.setKeySequence(QKeySequence(self.settings.value("keys/save", "Ctrl+S")))
        self.key_find.setKeySequence(QKeySequence(self.settings.value("keys/find", "Ctrl+F")))
        self.key_report.setKeySequence(QKeySequence(self.settings.value("keys/report", "Ctrl+R")))

    def accept(self):
        self.settings.setValue("editor/font", self.combo_editor_font.currentText())
        self.settings.setValue("editor/fontSize", self.sp_editor_size.value())
        self.settings.setValue("editor/autosave", "true" if self.chk_autosave.isChecked() else "false")
        self.settings.setValue("app/theme", self.combo_theme.currentText())
        self.settings.setValue("app/openViewers", "true" if self.chk_open_viewers.isChecked() else "false")
        self.settings.setValue("analysis/fastasPerCluster", self.sp_fastas.value())
        self.settings.setValue("analysis/blastMaxHits", self.sp_blast_hits.value())
        self.settings.setValue("analysis/deepParse", "true" if self.chk_deep_parse.isChecked() else "false")
        self.settings.setValue("keys/save", self.key_save.keySequence().toString())
        self.settings.setValue("keys/find", self.key_find.keySequence().toString())
        self.settings.setValue("keys/report", self.key_report.keySequence().toString())
        super().accept()
