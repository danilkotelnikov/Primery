"""
Editable text and FASTA-aware sequence tabs.
"""

import os
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QLabel,
    QInputDialog, QMessageBox,
)

_COMP = str.maketrans("ACGTRYMKBDHVNacgtrymkbdhvn", "TGCAYRKMVHDBNtgcayrkmvhdbn")
_CODON = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L", "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M", "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S", "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T", "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*", "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K", "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W", "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R", "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}
_IUPAC = {
    "A": "A", "C": "C", "G": "G", "T": "T", "U": "T", "R": "[AG]", "Y": "[CT]",
    "S": "[GC]", "W": "[AT]", "K": "[GT]", "M": "[AC]", "B": "[CGT]",
    "D": "[AGT]", "H": "[ACT]", "V": "[ACG]", "N": "[ACGT]",
}


class TextEditor(QWidget):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.lbl = QLabel(os.path.basename(path))
        self.btn_save = QPushButton("Save")
        self.btn_find = QPushButton("Find")
        bar.addWidget(self.lbl)
        bar.addStretch()
        bar.addWidget(self.btn_find)
        bar.addWidget(self.btn_save)
        layout.addLayout(bar)
        self.editor = QPlainTextEdit()
        layout.addWidget(self.editor)
        self.btn_save.clicked.connect(self.save)
        self.btn_find.clicked.connect(self.find_text)
        self.load()

    def load(self):
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            self.editor.setPlainText(f.read())

    def save(self):
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(self.editor.toPlainText())
        self.lbl.setText(os.path.basename(self.path) + " saved")

    def find_text(self):
        text, ok = QInputDialog.getText(self, "Find", "Text:")
        if ok and text:
            self.editor.find(text)


class SequenceEditor(TextEditor):
    def __init__(self, path, parent=None):
        super().__init__(path, parent)
        self.btn_rev = QPushButton("Rev-comp")
        self.btn_translate = QPushButton("Translate")
        self.btn_trim = QPushButton("Trim")
        self.btn_motif = QPushButton("Motif")
        self.layout().itemAt(0).layout().insertWidget(2, self.btn_rev)
        self.layout().itemAt(0).layout().insertWidget(3, self.btn_translate)
        self.layout().itemAt(0).layout().insertWidget(4, self.btn_trim)
        self.layout().itemAt(0).layout().insertWidget(5, self.btn_motif)
        self.btn_rev.clicked.connect(self.reverse_complement_selection)
        self.btn_translate.clicked.connect(self.translate_selection)
        self.btn_trim.clicked.connect(self.trim_ends)
        self.btn_motif.clicked.connect(self.find_iupac_motif)
        self.editor.textChanged.connect(self.validate_sequence)
        self.validate_sequence()

    def _selected_or_sequence(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            return cursor.selectedText().replace("\u2029", "\n"), cursor
        text = self.editor.toPlainText()
        seq = "".join(line.strip() for line in text.splitlines() if not line.startswith(">"))
        return seq, cursor

    def reverse_complement_selection(self):
        seq, cursor = self._selected_or_sequence()
        rc = seq.translate(_COMP)[::-1]
        if cursor.hasSelection():
            cursor.insertText(rc)
        else:
            QMessageBox.information(self, "Reverse complement", rc[:5000])

    def translate_selection(self):
        seq, _ = self._selected_or_sequence()
        seq = re.sub(r"[^ACGTacgt]", "", seq).upper()
        aa = "".join(_CODON.get(seq[i:i + 3], "X") for i in range(0, len(seq) - 2, 3))
        QMessageBox.information(self, "Translation", aa[:5000] or "No complete codons.")

    def trim_ends(self):
        n, ok = QInputDialog.getInt(self, "Trim", "Trim bases from each end:", 1, 0, 100000, 1)
        if not ok:
            return
        text = self.editor.toPlainText().splitlines()
        headers = [line for line in text if line.startswith(">")]
        seq = "".join(line.strip() for line in text if not line.startswith(">"))
        if n:
            seq = seq[n:-n] if len(seq) > 2 * n else ""
        wrapped = "\n".join(seq[i:i + 80] for i in range(0, len(seq), 80))
        self.editor.setPlainText(("\n".join(headers) + "\n" if headers else "") + wrapped)

    def find_iupac_motif(self):
        motif, ok = QInputDialog.getText(self, "IUPAC motif", "Motif:")
        if not ok or not motif:
            return
        pattern = "".join(_IUPAC.get(ch.upper(), re.escape(ch)) for ch in motif)
        text = self.editor.toPlainText()
        m = re.search(pattern, text, re.I)
        if not m:
            QMessageBox.information(self, "IUPAC motif", "No match.")
            return
        cursor = self.editor.textCursor()
        cursor.setPosition(m.start())
        cursor.setPosition(m.end(), QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)

    def validate_sequence(self):
        bad = []
        for line_no, line in enumerate(self.editor.toPlainText().splitlines(), 1):
            if line.startswith(">"):
                continue
            if re.search(r"[^ACGTRYMKBDHVNacgtrymkbdhvn\s.-]", line):
                bad.append(str(line_no))
        self.lbl.setText(os.path.basename(self.path) + (f" invalid lines: {', '.join(bad[:5])}" if bad else ""))


class FileEditorTab(QWidget):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        ext = os.path.splitext(path)[1].lower()
        if ext in {".fasta", ".fa", ".fna", ".ffn", ".faa"}:
            self.editor = SequenceEditor(path)
        else:
            self.editor = TextEditor(path)
        layout.addWidget(self.editor)
