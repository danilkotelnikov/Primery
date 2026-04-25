"""
report_dialog.py

Dialog for selecting organisms, genes, and report format before generating
a comprehensive PDF / DOCX report.
"""
import os
import glob
import re
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QGroupBox, QRadioButton, QLabel, QCheckBox,
    QFileDialog, QMessageBox, QSpinBox,
)
from PySide6.QtCore import Qt


class ReportDialog(QDialog):
    """Let the user pick organisms → genes and output format."""

    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Report")
        self.setMinimumSize(520, 420)
        self.workspace = workspace
        self.selections = []   # populated on accept
        self.output_format = "pdf"
        self.output_dir = ""

        layout = QVBoxLayout(self)

        # --- Tree ---
        layout.addWidget(QLabel("Select organisms and genes to include:"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Organism / Gene", "Primers", "Specificity"])
        self.tree.setColumnWidth(0, 280)
        layout.addWidget(self.tree)

        self._populate_tree()

        # --- Format ---
        grp_fmt = QGroupBox("Output Format")
        fl = QHBoxLayout(grp_fmt)
        self.rb_pdf = QRadioButton("PDF")
        self.rb_docx = QRadioButton("DOCX")
        self.rb_both = QRadioButton("Both")
        self.rb_pdf.setChecked(True)
        fl.addWidget(self.rb_pdf)
        fl.addWidget(self.rb_docx)
        fl.addWidget(self.rb_both)
        layout.addWidget(grp_fmt)

        # --- Include viewer screenshot ---
        self.cb_screenshot = QCheckBox("Include viewer mapping screenshot")
        self.cb_screenshot.setChecked(True)
        layout.addWidget(self.cb_screenshot)

        # --- Viewer export settings ---
        grp_viewer = QGroupBox("Viewer Export Settings (for screenshot)")
        vl = QHBoxLayout(grp_viewer)
        vl.addWidget(QLabel("Nucleotides per row:"))
        self.sb_cols = QSpinBox()
        self.sb_cols.setRange(20, 500)
        self.sb_cols.setValue(120)
        self.sb_cols.setToolTip(
            "Number of nucleotides displayed per row in the exported screenshot.\n"
            "Increase to fit more sequence in a single row (fits better on A4 landscape).\n"
            "Decrease for larger, more readable characters."
        )
        vl.addWidget(self.sb_cols)
        vl.addWidget(QLabel("(A4 landscape ≈ 120–160 nt/row)"))
        vl.addStretch()
        grp_viewer.setEnabled(True)
        self.cb_screenshot.toggled.connect(grp_viewer.setEnabled)
        layout.addWidget(grp_viewer)

        # --- Buttons ---
        bl = QHBoxLayout()
        bl.addStretch()
        self.btn_gen = QPushButton("Generate Report")
        self.btn_gen.setDefault(True)
        self.btn_cancel = QPushButton("Cancel")
        bl.addWidget(self.btn_gen)
        bl.addWidget(self.btn_cancel)
        layout.addLayout(bl)

        self.btn_gen.clicked.connect(self._on_generate)
        self.btn_cancel.clicked.connect(self.reject)

    # ── populate ──────────────────────────────────────────────
    def _populate_tree(self):
        ws = self.workspace
        if not os.path.isdir(ws):
            return
        for entry in sorted(os.listdir(ws)):
            org_path = os.path.join(ws, entry)
            blast_dir = os.path.join(org_path, "BLAST")
            if not os.path.isdir(blast_dir):
                continue
            org_item = QTreeWidgetItem([entry, "", ""])
            org_item.setFlags(org_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            org_item.setCheckState(0, Qt.Checked)

            for gene_name in sorted(os.listdir(blast_dir)):
                gene_blast = os.path.join(blast_dir, gene_name)
                if not os.path.isdir(gene_blast):
                    continue
                # Check for primers
                primer_files = glob.glob(os.path.join(gene_blast, "*_primers.json"))
                primer_methods = []
                for f in primer_files:
                    m = re.match(rf"^{re.escape(gene_name)}_(.+?)_primers\.json$", os.path.basename(f))
                    primer_methods.append(m.group(1) if m else os.path.basename(f))
                flat_probe_files = glob.glob(os.path.join(gene_blast, "*_probes.json"))
                nested_probe_files = glob.glob(os.path.join(gene_blast, "Probes", "**", "*_probes.json"), recursive=True)
                probe_file_map = {os.path.basename(p): p for p in sorted(flat_probe_files)}
                for f in sorted(nested_probe_files):
                    probe_file_map[os.path.basename(f)] = f
                probe_files = list(probe_file_map.values())
                for f in probe_files:
                    m = re.match(rf"^{re.escape(gene_name)}_(.+?)_probes\.json$", os.path.basename(f))
                    primer_methods.append((m.group(1) if m else os.path.basename(f)) + " probes")
                primer_label = ", ".join(primer_methods) if primer_methods else "—"
                
                # Check for specificity
                spec_dir = os.path.join(org_path, "Primer-BLAST")
                safe_gene = re.sub(r"[^A-Za-z0-9_.-]+", "_", gene_name).strip("_")
                spec_re = re.compile(rf"^PrimerBLAST_{re.escape(safe_gene)}_(.+?)_\d{{8}}_\d{{6}}\.txt$")
                spec_files = [
                    f for f in glob.glob(os.path.join(spec_dir, "PrimerBLAST_*.txt"))
                    if spec_re.match(os.path.basename(f))
                ] if os.path.isdir(spec_dir) else []
                spec_label = f"{len(spec_files)} report(s)" if spec_files else "—"

                child = QTreeWidgetItem([gene_name, primer_label, spec_label])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked)
                org_item.addChild(child)

            if org_item.childCount() > 0:
                self.tree.addTopLevelItem(org_item)

        self.tree.expandAll()

    # ── result ────────────────────────────────────────────────
    def _on_generate(self):
        # Gather selections
        self.selections = []
        for i in range(self.tree.topLevelItemCount()):
            org_item = self.tree.topLevelItem(i)
            if org_item.checkState(0) == Qt.Unchecked:
                continue
            org_name = org_item.text(0)
            genes = []
            for j in range(org_item.childCount()):
                child = org_item.child(j)
                if child.checkState(0) != Qt.Unchecked:
                    genes.append(child.text(0))
            if genes:
                self.selections.append({"organism": org_name, "genes": genes})

        if not self.selections:
            QMessageBox.warning(self, "No Selection", "Please select at least one gene.")
            return

        # Format
        if self.rb_docx.isChecked():
            self.output_format = "docx"
        elif self.rb_both.isChecked():
            self.output_format = "both"
        else:
            self.output_format = "pdf"

        self.include_screenshot = self.cb_screenshot.isChecked()
        self.viewer_cols = self.sb_cols.value()
        self.accept()
