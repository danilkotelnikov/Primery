"""In-app viewers for primer tables and Primer-BLAST reports."""

import csv
import glob
import json
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget, QHeaderView, QComboBox,
)


class PrimerTableViewer(QDialog):
    def __init__(self, start_dir="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Primer Table Viewer")
        self.resize(980, 620)
        self.rows = []
        self.workbook_sheets = {}
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.btn_open = QPushButton("Open XLSX/JSON")
        self.sheet_combo = QComboBox()
        self.sheet_combo.setMinimumWidth(160)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter")
        self.btn_export = QPushButton("Export CSV")
        top.addWidget(self.btn_open)
        top.addWidget(QLabel("Sheet:"))
        top.addWidget(self.sheet_combo)
        top.addWidget(QLabel("Filter:"))
        top.addWidget(self.filter)
        top.addWidget(self.btn_export)
        layout.addLayout(top)
        self.table = QTableWidget()
        layout.addWidget(self.table)
        self.btn_open.clicked.connect(lambda: self.open_file(start_dir))
        self.sheet_combo.currentTextChanged.connect(self._on_sheet_changed)
        self.filter.textChanged.connect(self._render)
        self.btn_export.clicked.connect(self.export_csv)

    def open_file(self, start_dir=""):
        path, _ = QFileDialog.getOpenFileName(self, "Open primer table", start_dir, "Primer files (*.xlsx *.json)")
        if path:
            self.load_file(path)

    def load_file(self, path):
        if path.lower().endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.rows = data if isinstance(data, list) else [data]
            self.workbook_sheets = {"JSON": self.rows}
            self.sheet_combo.blockSignals(True)
            self.sheet_combo.clear()
            self.sheet_combo.addItem("JSON")
            self.sheet_combo.blockSignals(False)
        else:
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
            self.workbook_sheets = {}
            for ws in wb.worksheets:
                rows = list(ws.iter_rows(values_only=True))
                if not rows:
                    self.workbook_sheets[ws.title] = []
                    continue
                headers = [str(h or f"Column {i + 1}") for i, h in enumerate(rows[0])]
                self.workbook_sheets[ws.title] = [
                    {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
                    for row in rows[1:]
                ]
            wb.close()
            self.sheet_combo.blockSignals(True)
            self.sheet_combo.clear()
            self.sheet_combo.addItems(list(self.workbook_sheets.keys()))
            self.sheet_combo.blockSignals(False)
            self.rows = self.workbook_sheets.get(self.sheet_combo.currentText(), [])
        self._render()

    def _on_sheet_changed(self, name):
        if self.workbook_sheets:
            self.rows = self.workbook_sheets.get(name, [])
            self._render()

    def _render(self):
        flt = self.filter.text().lower()
        rows = [r for r in self.rows if not flt or flt in json.dumps(r, ensure_ascii=False).lower()]
        preferred = [
            "rank", "Rank", "gene", "Gene", "method", "chemistry",
            "formatted_sequence", "Formatted", "left", "right",
            "Forward", "Reverse", "sequence", "Sequence", "tm", "Tm",
            "product_size", "specificity_status",
        ]
        keys = {k for row in rows for k in row.keys()}
        headers = [h for h in preferred if h in keys]
        headers.extend(sorted(k for k in keys if k not in headers))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, h in enumerate(headers):
                item = QTableWidgetItem(str(row.get(h, "")))
                item.setToolTip(item.text())
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        for c, h in enumerate(headers):
            width = 280 if "sequence" in h.lower() else 150
            self.table.setColumnWidth(c, width)
        self.table.verticalHeader().setDefaultSectionSize(24)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "primers.csv", "CSV (*.csv)")
        if not path:
            return
        headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for r in range(self.table.rowCount()):
                w.writerow([
                    self.table.item(r, c).text() if self.table.item(r, c) else ""
                    for c in range(self.table.columnCount())
                ])


class SpecificityReportViewer(QDialog):
    def __init__(self, report_dir="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Specificity Report Viewer")
        self.resize(1000, 650)
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        self.files = QListWidget()
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.table = QTableWidget()
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.table)
        right_layout.addWidget(self.text)
        splitter.addWidget(self.files)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)
        self.files.currentTextChanged.connect(self._load_report)
        self.report_dir = report_dir
        self.refresh()

    def refresh(self):
        self.files.clear()
        for path in sorted(glob.glob(os.path.join(self.report_dir, "PrimerBLAST_*.txt"))):
            self.files.addItem(os.path.basename(path))
        if self.files.count():
            self.files.setCurrentRow(self.files.count() - 1)

    def _parse_rows(self, content):
        rows = []
        current = None
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("Pair:"):
                if current:
                    rows.append(current)
                current = {"Pair": line.split(":", 1)[1].strip()}
            elif current and ":" in line:
                k, v = line.split(":", 1)
                if k.strip() in {"Status", "Target Hits", "Off-Target Hits"}:
                    current[k.strip()] = v.strip()
        if current:
            rows.append(current)
        return rows

    def _load_report(self, name):
        path = os.path.join(self.report_dir, name)
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        self.text.setPlainText(content)
        rows = self._parse_rows(content)
        headers = ["Pair", "Status", "Target Hits", "Off-Target Hits"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, h in enumerate(headers):
                item = QTableWidgetItem(str(row.get(h, "")))
                if h == "Status":
                    val = item.text()
                    if val == "Species-Specific":
                        item.setBackground(QColor("#2E7D32"))
                    elif val == "Non-Specific":
                        item.setBackground(QColor("#C62828"))
                    elif val == "Genus-Specific":
                        item.setBackground(QColor("#E65100"))
                self.table.setItem(r, c, item)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
