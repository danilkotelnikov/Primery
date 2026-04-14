"""
selection_dialog.py

A reusable dialog for selecting organisms and genes from the workspace.
Used for Mapping Mismatches, Mapping Primers, and Specificity Analysis.
"""
import os
import glob
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QMessageBox
)
from PySide6.QtCore import Qt

class SelectionDialog(QDialog):
    """
    Dialog to select Organisms and Genes.
    returns: list of {"organism": str, "genes": [str]}
    """
    def __init__(self, workspace, title="Select Targets", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(400, 500)
        self.workspace = workspace
        self.selections = []

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select organisms and genes:"))
        
        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Organism / Gene")
        layout.addWidget(self.tree)

        self._populate_tree()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(self.select_all)
        btn_none = QPushButton("Deselect All")
        btn_none.clicked.connect(self.deselect_all)
        btn_layout.addWidget(btn_all)
        btn_layout.addWidget(btn_none)
        layout.addLayout(btn_layout)

        # Action Buttons
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        self.btn_ok = QPushButton("OK")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept_selection)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_ok)
        action_layout.addWidget(self.btn_cancel)
        layout.addLayout(action_layout)

    def _populate_tree(self):
        ws = self.workspace
        if not os.path.isdir(ws):
            return

        for entry in sorted(os.listdir(ws)):
            org_path = os.path.join(ws, entry)
            # Check if it looks like an organism folder (has Genes or BLAST)
            if not os.path.isdir(org_path) or entry.startswith("."):
                continue
            
            blast_dir = os.path.join(org_path, "BLAST")
            genes_dir = os.path.join(org_path, "Genes")
            
            # We list genes found in BLAST (for results) OR Genes (for raw files)
            # For mapping, we usually care about BLAST/Primers results.
            # But let's look at BLAST dir primarily as that's where results are.
            # If BLAST dir doesn't exist, maybe fallback to Genes?
            # For "Analyzers" usually we need existing results.
            
            found_genes = set()
            if os.path.isdir(blast_dir):
                for g in os.listdir(blast_dir):
                    if os.path.isdir(os.path.join(blast_dir, g)):
                        found_genes.add(g)
            
            # If no BLAST results, maybe check Genes folder? 
            # (Use case: Specificity might want to choose just a gene to load primers for, 
            # but primers are in BLAST folder anyway).
            
            if not found_genes:
                continue

            item = QTreeWidgetItem([entry])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            item.setCheckState(0, Qt.Checked)
            
            for g in sorted(found_genes):
                child = QTreeWidgetItem([g])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked)
                item.addChild(child)
            
            self.tree.addTopLevelItem(item)

        self.tree.expandAll()

    def select_all(self):
        self._set_all_check_state(Qt.Checked)

    def deselect_all(self):
        self._set_all_check_state(Qt.Unchecked)

    def _set_all_check_state(self, state):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            item.setCheckState(0, state)
            for j in range(item.childCount()):
                item.child(j).setCheckState(0, state)

    def accept_selection(self):
        self.selections = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.Unchecked:
                continue
            
            org = item.text(0)
            genes = []
            for j in range(item.childCount()):
                child = item.child(j)
                if child.checkState(0) != Qt.Unchecked:
                    genes.append(child.text(0))
            
            if genes:
                self.selections.append({"organism": org, "genes": genes})
        
        if not self.selections:
            QMessageBox.warning(self, "No Selection", "Please select at least one gene.")
            return

        self.accept()
