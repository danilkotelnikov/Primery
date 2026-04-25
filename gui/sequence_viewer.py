"""
sequence_viewer.py

Tabular (wrapped) sequence viewer with annotation tracks.

Layout per row (dynamic):
  Row-header | Ruler | Sequence | Mismatch track | Cluster track
  Then one sub-row per primer pair (stacked, non-overlapping)
  Then amplicon bracket per pair

All color schemes use a dark background — only nucleotide colors vary.
"""
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsSimpleTextItem, QGraphicsRectItem,
    QGraphicsLineItem, QGraphicsPolygonItem,
    QToolTip, QMenu, QWidget, QVBoxLayout, QDialog, QPlainTextEdit,
    QDialogButtonBox, QLabel, QMessageBox, QFileDialog, QInputDialog,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QBrush, QPen, QColor, QFont, QPolygonF, QPainter,
    QAction, QGuiApplication, QFontMetrics,
)
import math
import os
import re

# ─────────────────────── Color schemes ────────────────────────
# All schemes share a dark background; only nucleotide colors differ.

_DARK_BG     = QColor(28, 28, 32)
_RULER_CLR   = QColor(160, 165, 180)
_HEADER_CLR  = QColor(130, 140, 160)

COLOR_SCHEMES = {
    "Classic": {
        "A": QColor(80, 200, 80),
        "T": QColor(240, 80, 80),
        "G": QColor(200, 200, 200),
        "C": QColor(80, 140, 255),
        "N": QColor(100, 100, 100),
    },
    "Nucleotide": {
        "A": QColor(64, 225, 64),
        "T": QColor(255, 90, 90),
        "G": QColor(255, 210, 40),
        "C": QColor(80, 160, 255),
        "N": QColor(120, 120, 120),
    },
    "Shapely": {
        "A": QColor(160, 255, 160),
        "T": QColor(255, 160, 95),
        "G": QColor(255, 130, 140),
        "C": QColor(235, 218, 40),
        "N": QColor(140, 140, 140),
    },
    "Rasmol": {
        "A": QColor(160, 0, 0),
        "T": QColor(0, 0, 255),
        "G": QColor(255, 200, 0),
        "C": QColor(0, 200, 0),
        "N": QColor(120, 120, 120),
    },
}

IUPAC_BASES = set("ACGTRYSWKMBDHVN")
_COMP = str.maketrans(
    "ACGTRYSWKMBDHVNacgtryswkmbdhvn",
    "TGCAYRSWMKVHDBNtgcayrswmkvhdbn",
)
_IUPAC_RE = {
    "A": "A", "C": "C", "G": "G", "T": "T",
    "R": "[AG]", "Y": "[CT]", "S": "[GC]", "W": "[AT]",
    "K": "[GT]", "M": "[AC]", "B": "[CGT]", "D": "[AGT]",
    "H": "[ACT]", "V": "[ACG]", "N": "[ACGT]",
}
_CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
    "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
    "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


def _clean_sequence(text):
    lines = [line.strip() for line in text.splitlines() if not line.startswith(">")]
    return re.sub(r"\s+", "", "".join(lines)).upper()


def _wrap_fasta(seq, width=80):
    return "\n".join(seq[i:i + width] for i in range(0, len(seq), width))

MONOSPACE_FONTS = [
    "Consolas", "Courier New", "Lucida Console",
    "DejaVu Sans Mono", "Source Code Pro", "JetBrains Mono",
    "Fira Code", "IBM Plex Mono",
]

# ─────────────────────── Track sizes ──────────────────────────
RULER_H    = 18
SEQ_H      = 18
MM_H       = 8
CLUSTER_H  = 10
PROBE_H    = 10
PRIMER_H   = 10
AMPLICON_H = 10
TRACK_GAP  = 2
HEADER_W   = 55


# ═══════════════════════ Graphics Items ═══════════════════════

class RowHeaderItem(QGraphicsItem):
    def __init__(self, start_pos, font, char_h):
        super().__init__()
        self.label = str(start_pos + 1)
        self.font = font
        self.h = char_h

    def boundingRect(self):
        return QRectF(0, 0, HEADER_W - 4, self.h)

    def paint(self, painter, option, widget):
        painter.setFont(self.font)
        painter.setPen(QPen(_HEADER_CLR))
        painter.drawText(self.boundingRect(), Qt.AlignRight | Qt.AlignVCenter, self.label)


class RowRulerItem(QGraphicsItem):
    def __init__(self, start_idx, count, char_w):
        super().__init__()
        self.start = start_idx
        self.count = count
        self.cw = char_w

    def boundingRect(self):
        return QRectF(0, 0, self.count * self.cw, RULER_H)

    def paint(self, painter, option, widget):
        pen = QPen(_RULER_CLR, 1)
        painter.setPen(pen)
        painter.drawLine(0, RULER_H - 1, self.count * self.cw, RULER_H - 1)
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        for i in range(self.count):
            pos1 = self.start + i + 1
            x = i * self.cw + self.cw / 2
            if pos1 % 10 == 0:
                painter.drawLine(x, 8, x, RULER_H - 1)
                painter.drawText(x - 12, 7, str(pos1))
            elif pos1 % 5 == 0:
                painter.drawLine(x, 12, x, RULER_H - 1)


class RowSequenceItem(QGraphicsItem):
    def __init__(self, seq_chunk, base_colors, font, char_w, char_h):
        super().__init__()
        self.seq = seq_chunk
        self.colors = base_colors
        self.font = font
        self.cw = char_w
        self.ch = char_h

    def boundingRect(self):
        return QRectF(0, 0, len(self.seq) * self.cw, self.ch)

    def paint(self, painter, option, widget):
        painter.setFont(self.font)
        rect = option.exposedRect
        start = max(0, int(rect.left() / self.cw))
        end = min(len(self.seq), int(rect.right() / self.cw) + 1)
        for i in range(start, end):
            c = self.seq[i].upper()
            color = self.colors.get(c, QColor(100, 100, 100))
            painter.setPen(QPen(color))
            painter.drawText(
                QRectF(i * self.cw, 0, self.cw, self.ch),
                Qt.AlignCenter, self.seq[i],
            )


class MismatchBarItem(QGraphicsRectItem):
    def __init__(self, x, y, w, h, ratio, metadata):
        super().__init__(x, y, w, h)
        alpha = max(50, int(255 * ratio))
        self.setBrush(QBrush(QColor(255, 60, 60, alpha)))
        self.setPen(Qt.NoPen)
        pos1 = metadata.get("pos", 0)
        count = metadata.get("count", 0)
        species = metadata.get("species", "")
        variants = metadata.get("variants", "")
        tip = f"Position {pos1}\n{count} accession(s) mismatch"
        if species:
            tip += f"\nSpecies: {species}"
        if variants:
            tip += f"\nVariants: {variants}"
        self.setToolTip(tip)
        self.setAcceptHoverEvents(True)


class ClusterRegionItem(QGraphicsRectItem):
    PALETTE = [
        QColor(52, 152, 219, 130), QColor(46, 204, 113, 130),
        QColor(155, 89, 182, 130), QColor(241, 196, 15, 130),
        QColor(230, 126, 34, 130), QColor(231, 76, 60, 130),
        QColor(26, 188, 156, 130), QColor(142, 68, 173, 130),
    ]

    def __init__(self, x, y, w, h, cluster_id, rank, n_mm, n_species, species_list=None):
        super().__init__(x, y, w, h)
        idx = (cluster_id - 1) % len(self.PALETTE)
        self.setBrush(QBrush(self.PALETTE[idx]))
        self.setPen(QPen(self.PALETTE[idx].darker(130), 1))
        tip = (
            f"Cluster {cluster_id}  (Rank {rank})\n"
            f"Mismatches: {n_mm}\n"
            f"Discriminates {n_species} species"
        )
        if species_list:
            shown = species_list[:8]
            tip += "\n" + "\n".join(f"  • {s}" for s in shown)
            if len(species_list) > 8:
                tip += f"\n  … +{len(species_list)-8} more"
        self.setToolTip(tip)
        self.setAcceptHoverEvents(True)


def _as_int_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[;,\s]+", value.strip())
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    out = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return sorted(set(out))


def _match_map(length, rel_positions):
    if length <= 0:
        return ""
    marks = ["·"] * min(length, 80)
    for rel in rel_positions:
        if 0 <= rel < len(marks):
            marks[rel] = "█"
    suffix = "…" if length > len(marks) else ""
    return "".join(marks) + suffix


class PrimerArrowItem(QGraphicsItem):
    def __init__(
        self, x, y, w, h, is_reverse, metadata,
        visible_start0=None, visible_len=None, base_color=None, label="Primer",
    ):
        super().__init__()
        self.x, self.y, self.w, self.h = x, y, max(w, 1), h
        self.is_reverse = bool(is_reverse)
        self.meta = metadata or {}
        self.visible_start0 = int(visible_start0 if visible_start0 is not None else self._start0())
        self.visible_len = max(1, int(visible_len or self._length()))
        self.base_color = QColor(base_color or (QColor(220, 60, 60, 220) if is_reverse else QColor(0, 200, 0, 220)))
        self.label = label
        self.setToolTip(self._tooltip())
        self.setAcceptHoverEvents(True)

    def _start0(self):
        m = self.meta
        if "pos" in m:
            return int(m.get("pos", 0) or 0)
        return int(m.get("start", 0) or 0)

    def _length(self):
        m = self.meta
        return int(m.get("len") or m.get("length") or max(1, len(m.get("seq") or m.get("sequence") or "")))

    def _mismatch_rel_positions(self):
        start0 = self._start0()
        positions1 = _as_int_list(self.meta.get("mismatch_positions"))
        if not positions1:
            positions1 = _as_int_list(self.meta.get("mm_positions"))
        return sorted({p - 1 - start0 for p in positions1})

    def _tooltip(self):
        m = self.meta
        direction = "Reverse (←)" if self.is_reverse else "Forward (→)"
        if self.label == "Probe":
            direction = "Probe (→)"
        start0 = self._start0()
        length = self._length()
        rel_mm = self._mismatch_rel_positions()
        positions = _as_int_list(m.get("mismatch_positions") or m.get("mm_positions"))
        seq = m.get("seq") or m.get("formatted_sequence") or m.get("sequence", "")
        tip = (
            f"{self.label} {direction}\n"
            f"Sequence: {seq}\n"
            f"Position: {start0 + 1}-{start0 + length}\n"
            f"Mismatches covered: {m.get('mm', m.get('mm_covered', 0))}"
        )
        if m.get("tm", "") != "":
            tip += f"\nTm: {m.get('tm')}°C"
        if m.get("cluster_id"):
            tip += f"\nCluster: {m.get('cluster_id')}"
        if m.get("chemistry"):
            tip += f"\nChemistry: {m.get('chemistry')}"
        if positions:
            tip += f"\nMismatch positions: {', '.join(str(p) for p in positions)}"
            tip += f"\nMismatch map: {_match_map(length, rel_mm)}"
        lna_positions = _as_int_list(m.get("lna_positions"))
        if lna_positions:
            tip += f"\nLNA positions: {', '.join(str(p) for p in lna_positions)}"
        return tip

    def boundingRect(self):
        return QRectF(self.x - 1, self.y - 1, self.w + 2, self.h + 2)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing, False)
        cell_w = self.w / max(1, self.visible_len)
        start0 = self._start0()
        mismatch_rel = set(self._mismatch_rel_positions())
        visible_rel0 = self.visible_start0 - start0
        pen = QPen(self.base_color.darker(150), 0.6)
        painter.setPen(pen)
        for i in range(self.visible_len):
            rel = visible_rel0 + i
            x0 = self.x + i * cell_w
            x1 = self.x + (i + 1) * cell_w
            lighten = 90 + int(35 * (i / max(1, self.visible_len - 1)))
            color = self.base_color.lighter(lighten)
            if rel in mismatch_rel:
                color = QColor(255, 70, 55, 235)
            brush = QBrush(color)
            is_head = (i == 0 and self.is_reverse) or (i == self.visible_len - 1 and not self.is_reverse)
            if is_head and cell_w >= 4:
                if self.is_reverse:
                    pts = QPolygonF([
                        QPointF(x1, self.y + 1),
                        QPointF(x0, self.y + self.h / 2),
                        QPointF(x1, self.y + self.h - 1),
                    ])
                else:
                    pts = QPolygonF([
                        QPointF(x0, self.y + 1),
                        QPointF(x1, self.y + self.h / 2),
                        QPointF(x0, self.y + self.h - 1),
                    ])
                painter.setBrush(brush)
                painter.drawPolygon(pts)
            else:
                painter.setBrush(brush)
                painter.drawRect(QRectF(x0 + 0.5, self.y + 1, max(1, cell_w - 1), self.h - 2))


class ProbeRegionItem(PrimerArrowItem):
    def __init__(self, x, y, w, h, metadata, visible_start0=None, visible_len=None):
        super().__init__(
            x, y, w, h, False, metadata,
            visible_start0=visible_start0,
            visible_len=visible_len,
            base_color=QColor(180, 90, 230, 220),
            label="Probe",
        )


class AmpliconBracketItem(QGraphicsItem):
    def __init__(self, x_start, x_end, y, metadata):
        super().__init__()
        self.xs = x_start
        self.xe = x_end
        self.y = y
        self.meta = metadata
        tip = (
            f"Amplicon #{metadata.get('rank',0)}\n"
            f"Product size: {metadata.get('size',0)} bp\n"
            f"Forward cluster: {metadata.get('fwd_cid','?')}\n"
            f"Reverse cluster: {metadata.get('rev_cid','?')}\n"
            f"Species covered: {metadata.get('n_species',0)}"
        )
        self.setToolTip(tip)
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        return QRectF(self.xs - 2, self.y - 2, self.xe - self.xs + 4, AMPLICON_H + 4)

    def paint(self, painter, option, widget):
        pen = QPen(QColor(160, 170, 190), 1.5)
        painter.setPen(pen)
        y = self.y
        painter.drawLine(self.xs, y, self.xs, y + 8)
        painter.drawLine(self.xs, y + 8, self.xe, y + 8)
        painter.drawLine(self.xe, y, self.xe, y + 8)
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(QPen(_RULER_CLR))
        mid = (self.xs + self.xe) / 2
        painter.drawText(QPointF(mid - 18, y + 6),
                         f"{self.meta.get('size', 0)}bp")


# ═══════════════════════ Main Viewer ═══════════════════════

class SequenceViewer(QGraphicsView):
    """
    Tabular wrapped sequence viewer.
    Primer pairs are stacked vertically (one sub-row per pair) so they
    never overlap. Each row's height is dynamic based on the number of
    primers in that row.
    """
    DEFAULT_COLS = 80
    sequenceEdited = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setBackgroundBrush(QBrush(_DARK_BG))

        # State
        self.sequence = ""
        self.source_path = None
        self.font_name = "Consolas"
        self.font_size = 10
        self.scheme_name = "Classic"
        self._recalc_metrics()

        self.cols_per_row = self.DEFAULT_COLS

        # Annotation data (kept for re-render)
        self._mismatches = []
        self._clusters = []
        self._probes = []
        self._primers = []       # [{start, len, is_reverse, meta, pair_rank}]
        self._amplicons = []

        # Selection
        self.sel_start = None
        self.sel_end = None
        self.sel_items = []

    # ── Config ───────────────────────────────────────────────
    def _recalc_metrics(self):
        f = QFont(self.font_name, self.font_size)
        fm = QFontMetrics(f)
        self.char_width = max(fm.horizontalAdvance("W"), 8)
        self.char_height = fm.height()
        self._font_obj = f

    def set_font(self, name: str, size: int = 10):
        self.font_name = name
        self.font_size = size
        self._recalc_metrics()
        self._rebuild()

    def set_color_scheme(self, name: str):
        if name in COLOR_SCHEMES:
            self.scheme_name = name
            self._rebuild()

    def set_cols_per_row(self, cols: int):
        self.cols_per_row = max(10, cols)
        self._rebuild()

    def auto_cols_for_width(self):
        vw = self.viewport().width()
        usable = vw - HEADER_W - 20
        cols = max(10, int(usable / self.char_width))
        if cols != self.cols_per_row:
            self.cols_per_row = cols
            self._rebuild()

    # ── Data loading ─────────────────────────────────────────
    def load_sequence(self, seq: str, source_path: str = None):
        self.sequence = _clean_sequence(seq)
        self.source_path = source_path
        self.clear_annotations()
        self.sel_start = self.sel_end = None
        self.sel_items.clear()
        self.auto_cols_for_width()
        self._rebuild()

    def set_source_path(self, path):
        self.source_path = path

    def clear_annotations(self):
        self._mismatches.clear()
        self._clusters.clear()
        self._probes.clear()
        self._primers.clear()
        self._amplicons.clear()

    def clear_probes(self):
        self._probes.clear()

    def add_mismatches(self, mismatch_data: list):
        self._mismatches = mismatch_data
        self._rebuild()

    def add_cluster(self, start0, end0, cluster_id, rank, n_mm, n_species, species_list=None):
        self._clusters.append({
            "start": start0, "end": end0,
            "id": cluster_id, "rank": rank,
            "n_mm": n_mm, "n_species": n_species,
            "species": species_list or [],
        })
        self._rebuild()

    def add_clusters_batch(self, clusters_list):
        for c in clusters_list:
            self._clusters.append(c)
        self._rebuild()

    def add_primer(self, start, length, is_reverse, metadata, pair_rank=0):
        if isinstance(metadata, str):
            metadata = {"label": metadata}
        self._primers.append({
            "start": start, "len": length,
            "is_reverse": is_reverse, "meta": metadata,
            "pair_rank": pair_rank,
        })

    def add_probe(self, start, length, metadata):
        if isinstance(metadata, str):
            metadata = {"label": metadata}
        self._probes.append({
            "start": start,
            "len": length,
            "meta": metadata,
        })

    def add_amplicon_span(self, left_start, right_end, metadata):
        self._amplicons.append({
            "left_start": left_start, "right_end": right_end,
            "meta": metadata,
        })

    def finish_annotations(self):
        self._rebuild()

    def selected_range(self):
        if self.sel_start is None or self.sel_end is None:
            return None
        return tuple(sorted((self.sel_start, self.sel_end)))

    def selected_sequence(self):
        rng = self.selected_range()
        if not rng:
            return ""
        start, end = rng
        return self.sequence[start:end + 1]

    def invalid_bases(self):
        return sorted({b for b in self.sequence.upper() if b not in IUPAC_BASES})

    def validate_sequence(self, show_message=True):
        invalid = self.invalid_bases()
        if invalid:
            msg = f"Invalid sequence characters: {', '.join(invalid)}"
            if show_message:
                QMessageBox.warning(self, "Sequence Validation", msg)
            return False, msg
        msg = f"Valid IUPAC nucleotide sequence ({len(self.sequence)} bp)."
        if show_message:
            QMessageBox.information(self, "Sequence Validation", msg)
        return True, msg

    def edit_sequence(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Sequence")
        dlg.resize(760, 520)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Edit FASTA or raw nucleotide sequence:"))
        editor = QPlainTextEdit(dlg)
        header = os.path.splitext(os.path.basename(self.source_path or "sequence"))[0]
        editor.setPlainText(f">{header}\n{_wrap_fasta(self.sequence)}")
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, dlg)
        layout.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted:
            return

        seq = _clean_sequence(editor.toPlainText())
        if not seq:
            QMessageBox.warning(self, "Edit Sequence", "Sequence is empty.")
            return
        invalid = sorted({b for b in seq if b not in IUPAC_BASES})
        if invalid:
            QMessageBox.warning(
                self,
                "Edit Sequence",
                f"Invalid sequence characters: {', '.join(invalid)}",
            )
            return
        self.sequence = seq
        self.clear_annotations()
        self.sel_start = self.sel_end = None
        self.sel_items.clear()
        self.auto_cols_for_width()
        self._rebuild()
        self.sequenceEdited.emit(self.sequence)

    def save_fasta(self):
        path = self.source_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save FASTA", "sequence.fasta", "FASTA (*.fasta *.fa)"
            )
        if not path:
            return
        header = os.path.splitext(os.path.basename(path))[0]
        with open(path, "w", encoding="utf-8") as f:
            f.write(f">{header}\n{_wrap_fasta(self.sequence)}\n")
        self.source_path = path
        QMessageBox.information(self, "Save FASTA", f"Saved {os.path.basename(path)}")

    def reverse_complement(self):
        if not self.sequence:
            return
        self.sequence = self.sequence.translate(_COMP)[::-1].upper()
        self.clear_annotations()
        self.sel_start = self.sel_end = None
        self.sel_items.clear()
        self.auto_cols_for_width()
        self._rebuild()
        self.sequenceEdited.emit(self.sequence)

    def trim_to_selection(self):
        seq = self.selected_sequence()
        if not seq:
            QMessageBox.information(self, "Trim Sequence", "Select a sequence range first.")
            return
        self.sequence = seq.upper()
        self.clear_annotations()
        self.sel_start = self.sel_end = None
        self.sel_items.clear()
        self.auto_cols_for_width()
        self._rebuild()
        self.sequenceEdited.emit(self.sequence)

    def translate_selection(self):
        seq = self.selected_sequence() or self.sequence
        seq = seq.upper()
        aa = []
        for i in range(0, len(seq) - 2, 3):
            codon = seq[i:i + 3]
            aa.append(_CODON_TABLE.get(codon, "X"))
        QMessageBox.information(
            self,
            "Translation",
            "".join(aa) or "No complete codons in sequence.",
        )

    def find_iupac_motif(self):
        motif, ok = QInputDialog.getText(self, "Find IUPAC Motif", "Motif:")
        if not ok or not motif.strip():
            return
        motif = _clean_sequence(motif)
        try:
            pattern = "".join(_IUPAC_RE[b] for b in motif)
        except KeyError as e:
            QMessageBox.warning(self, "Find IUPAC Motif", f"Unsupported base: {e.args[0]}")
            return
        match = re.search(pattern, self.sequence, flags=re.IGNORECASE)
        if not match:
            QMessageBox.information(self, "Find IUPAC Motif", "No match found.")
            return
        self.sel_start = match.start()
        self.sel_end = match.end() - 1
        self._update_sel()
        row = self.sel_start // max(1, self.cols_per_row)
        row_h = RULER_H + SEQ_H + MM_H + TRACK_GAP + CLUSTER_H + TRACK_GAP + PROBE_H + TRACK_GAP
        self.centerOn(HEADER_W + (self.sel_start % self.cols_per_row) * self.char_width, row * row_h)

    def export_to_image(self):
        """Render the scene to a white-background QImage for reports.

        The image is rendered at the scene's native pixel dimensions so that
        the result is representative regardless of the cols_per_row setting.
        The caller (main_window) is responsible for setting cols_per_row to
        the desired value before calling this method.
        """
        from PySide6.QtGui import QImage
        sr = self.scene.sceneRect()
        if sr.width() < 1 or sr.height() < 1:
            return None
        img_w = int(sr.width())
        img_h = int(sr.height())
        img = QImage(img_w, img_h, QImage.Format_ARGB32)
        img.fill(QColor(255, 255, 255))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        self.scene.render(p)
        p.end()
        return img

    # ── Compute which primer pairs live in each row ──────────
    def _primers_per_row(self, cols):
        """Return dict: row_idx -> list of unique pair_rank values."""
        row_pairs = {}
        for pr in self._primers:
            ps = pr["start"]
            pe = ps + pr["len"] - 1
            for row_idx in range(ps // cols, pe // cols + 1):
                row_pairs.setdefault(row_idx, set()).add(pr["pair_rank"])
        for amp in self._amplicons:
            als = amp["left_start"]
            are_ = amp["right_end"]
            for row_idx in range(als // cols, are_ // cols + 1):
                rank = amp["meta"].get("rank", 0)
                row_pairs.setdefault(row_idx, set()).add(rank)
        return {k: sorted(v) for k, v in row_pairs.items()}

    # ── Core rendering ───────────────────────────────────────
    def _rebuild(self):
        self.scene.clear()
        self.sel_items.clear()
        if not self.sequence:
            return

        self.setBackgroundBrush(QBrush(_DARK_BG))
        base_colors = COLOR_SCHEMES.get(self.scheme_name, COLOR_SCHEMES["Classic"])

        seq = self.sequence
        cw = self.char_width
        ch = self.char_height
        cols = self.cols_per_row
        n_rows = math.ceil(len(seq) / cols)

        # Pre-compute per-row primer pair count for dynamic height
        row_pairs = self._primers_per_row(cols)

        y_cursor = 0  # Running Y position

        for row_idx in range(n_rows):
            row_start = row_idx * cols
            row_end = min(row_start + cols, len(seq))
            chunk = seq[row_start:row_end]
            n = len(chunk)

            x_base = HEADER_W
            y_base = y_cursor

            # --- Fixed tracks ---
            # Row header
            hdr = RowHeaderItem(row_start, self._font_obj, ch)
            hdr.setPos(0, y_base + RULER_H)
            self.scene.addItem(hdr)

            # Ruler
            ruler = RowRulerItem(row_start, n, cw)
            ruler.setPos(x_base, y_base)
            self.scene.addItem(ruler)

            # Sequence
            seq_item = RowSequenceItem(chunk, base_colors, self._font_obj, cw, ch)
            seq_item.setPos(x_base, y_base + RULER_H)
            self.scene.addItem(seq_item)

            # Mismatch track
            mm_y = y_base + RULER_H + SEQ_H
            for mm in self._mismatches:
                p0 = mm.get("pos", 0) - 1
                if row_start <= p0 < row_end:
                    local_x = (p0 - row_start) * cw
                    total = mm.get("total", 100)
                    count = mm.get("count", 0)
                    ratio = count / max(1, total)
                    item = MismatchBarItem(
                        x_base + local_x, mm_y, cw, MM_H, ratio, mm,
                    )
                    self.scene.addItem(item)

            # Cluster track
            cl_y = mm_y + MM_H + TRACK_GAP
            for cl in self._clusters:
                cs, ce = cl["start"], cl["end"]
                if ce < row_start or cs >= row_end:
                    continue
                local_s = max(cs - row_start, 0)
                local_e = min(ce - row_start, n - 1)
                x = x_base + local_s * cw
                w = (local_e - local_s + 1) * cw
                item = ClusterRegionItem(
                    x, cl_y, w, CLUSTER_H,
                    cl["id"], cl["rank"], cl["n_mm"], cl["n_species"],
                    cl.get("species"),
                )
                self.scene.addItem(item)

            # Probe track
            probe_y = cl_y + CLUSTER_H + TRACK_GAP
            for prb in self._probes:
                ps = prb["start"]
                pe = ps + prb["len"] - 1
                if pe < row_start or ps >= row_end:
                    continue
                local_s = max(ps - row_start, 0)
                local_e = min(pe - row_start, n - 1)
                x = x_base + local_s * cw
                w = (local_e - local_s + 1) * cw
                item = ProbeRegionItem(
                    x, probe_y, w, PROBE_H, prb["meta"],
                    visible_start0=row_start + local_s,
                    visible_len=local_e - local_s + 1,
                )
                self.scene.addItem(item)

            # --- Dynamic primer/amplicon tracks (stacked per pair_rank) ---
            pair_ranks = row_pairs.get(row_idx, [])
            primer_base_y = probe_y + PROBE_H + TRACK_GAP
            pair_slot = {rank: slot for slot, rank in enumerate(pair_ranks)}

            for pr in self._primers:
                ps = pr["start"]
                pe = ps + pr["len"] - 1
                if pe < row_start or ps >= row_end:
                    continue
                local_s = max(ps - row_start, 0)
                local_e = min(pe - row_start, n - 1)
                x = x_base + local_s * cw
                w = (local_e - local_s + 1) * cw
                slot = pair_slot.get(pr["pair_rank"], 0)
                sub_y = slot * (PRIMER_H * 2 + AMPLICON_H + TRACK_GAP * 2)
                y_fwd = primer_base_y + sub_y
                y_rev = y_fwd + PRIMER_H + 1
                y_track = y_fwd if not pr["is_reverse"] else y_rev
                item = PrimerArrowItem(
                    x, y_track, w, PRIMER_H,
                    pr["is_reverse"], pr["meta"],
                    visible_start0=row_start + local_s,
                    visible_len=local_e - local_s + 1,
                )
                self.scene.addItem(item)

            for amp in self._amplicons:
                als = amp["left_start"]
                are_ = amp["right_end"]
                if are_ < row_start or als >= row_end:
                    continue
                local_s = max(als - row_start, 0)
                local_e = min(are_ - row_start, n - 1)
                xs = x_base + local_s * cw
                xe = x_base + (local_e + 1) * cw
                rank = amp["meta"].get("rank", 0)
                slot = pair_slot.get(rank, 0)
                sub_y = slot * (PRIMER_H * 2 + AMPLICON_H + TRACK_GAP * 2)
                y_amp = primer_base_y + sub_y + PRIMER_H * 2 + TRACK_GAP
                item = AmpliconBracketItem(xs, xe, y_amp, amp["meta"])
                self.scene.addItem(item)

            # Advance y_cursor
            n_pair_slots = max(len(pair_ranks), 0)
            dynamic_h = n_pair_slots * (PRIMER_H * 2 + AMPLICON_H + TRACK_GAP * 2)
            fixed_h = RULER_H + SEQ_H + MM_H + TRACK_GAP + CLUSTER_H + TRACK_GAP + PROBE_H + TRACK_GAP
            row_height = fixed_h + dynamic_h + 8  # 8px padding below
            y_cursor += row_height

        # Set scene rect
        total_w = HEADER_W + cols * cw + 30
        self.setSceneRect(0, 0, total_w, y_cursor + 20)

    # ── Interaction ──────────────────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.sequence:
            self.auto_cols_for_width()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx = self._pos_to_idx(event.pos())
            if idx is not None:
                self.sel_start = idx
                self.sel_end = idx
                self._update_sel()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.sel_start is not None:
            idx = self._pos_to_idx(event.pos())
            if idx is not None:
                self.sel_end = idx
                self._update_sel()
        super().mouseMoveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        ac = QAction("Copy Selection", self)
        ac.triggered.connect(self.copy_sel)
        menu.addAction(ac)
        menu.addSeparator()
        menu.addAction("Edit Sequence", self.edit_sequence)
        menu.addAction("Save FASTA", self.save_fasta)
        menu.addAction("Validate Sequence", lambda: self.validate_sequence(True))
        menu.addSeparator()
        menu.addAction("Reverse Complement", self.reverse_complement)
        menu.addAction("Translate Selection", self.translate_selection)
        menu.addAction("Trim to Selection", self.trim_to_selection)
        menu.addAction("Find IUPAC Motif", self.find_iupac_motif)
        menu.exec_(event.globalPos())

    def _pos_to_idx(self, view_pos):
        # NOTE: with dynamic row heights, we need a different approach
        # For now use a simple heuristic (good enough for selection)
        sp = self.mapToScene(view_pos)
        x, y = sp.x(), sp.y()
        local_x = x - HEADER_W
        if local_x < 0:
            return None
        col = int(local_x / self.char_width)
        if col >= self.cols_per_row:
            return None
        # Estimate row from Y — scan row boundaries
        # Since we stored y_cursor increments, we need a simple accumulator
        cols = self.cols_per_row
        n_rows = math.ceil(len(self.sequence) / cols)
        row_pairs = self._primers_per_row(cols)
        y_acc = 0
        for row_idx in range(n_rows):
            n_pair_slots = len(row_pairs.get(row_idx, []))
            dynamic_h = n_pair_slots * (PRIMER_H * 2 + AMPLICON_H + TRACK_GAP * 2)
            fixed_h = RULER_H + SEQ_H + MM_H + TRACK_GAP + CLUSTER_H + TRACK_GAP + PROBE_H + TRACK_GAP
            row_h = fixed_h + dynamic_h + 8
            if y < y_acc + row_h:
                idx = row_idx * cols + col
                if 0 <= idx < len(self.sequence):
                    return idx
                return None
            y_acc += row_h
        return None

    def _update_sel(self):
        for it in self.sel_items:
            self.scene.removeItem(it)
        self.sel_items.clear()
        if self.sel_start is None or self.sel_end is None:
            return
        s, e = sorted((self.sel_start, self.sel_end))
        # Highlight selected bases — we just overlay rects on the sequence track
        # We need row Y positions, so recalculate
        cols = self.cols_per_row
        cw = self.char_width
        n_rows = math.ceil(len(self.sequence) / cols)
        row_pairs = self._primers_per_row(cols)
        y_acc = 0
        for row_idx in range(n_rows):
            row_start = row_idx * cols
            row_end = min(row_start + cols, len(self.sequence))
            # Check overlap with selection
            sel_lo = max(s, row_start)
            sel_hi = min(e, row_end - 1)
            if sel_lo <= sel_hi:
                for idx in range(sel_lo, sel_hi + 1):
                    col = idx - row_start
                    x = HEADER_W + col * cw
                    y_seq = y_acc + RULER_H
                    rect = QGraphicsRectItem(x, y_seq, cw, self.char_height)
                    rect.setBrush(QBrush(QColor(60, 120, 255, 60)))
                    rect.setPen(Qt.NoPen)
                    self.scene.addItem(rect)
                    self.sel_items.append(rect)

            n_pair_slots = len(row_pairs.get(row_idx, []))
            dynamic_h = n_pair_slots * (PRIMER_H * 2 + AMPLICON_H + TRACK_GAP * 2)
            fixed_h = RULER_H + SEQ_H + MM_H + TRACK_GAP + CLUSTER_H + TRACK_GAP + PROBE_H + TRACK_GAP
            y_acc += fixed_h + dynamic_h + 8

    def copy_sel(self):
        if self.sel_start is not None and self.sel_end is not None:
            s, e = sorted((self.sel_start, self.sel_end))
            QGuiApplication.clipboard().setText(self.sequence[s:e + 1])
