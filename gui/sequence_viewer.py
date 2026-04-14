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
    QToolTip, QMenu, QWidget, QVBoxLayout,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QBrush, QPen, QColor, QFont, QPolygonF, QPainter,
    QAction, QGuiApplication, QFontMetrics,
)
import math

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
PRIMER_H   = 8
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


class PrimerArrowItem(QGraphicsPolygonItem):
    def __init__(self, x, y, w, h, is_reverse, metadata):
        super().__init__()
        if not is_reverse:
            pts = [
                QPointF(x, y + 2), QPointF(x + w - 6, y + 2),
                QPointF(x + w - 6, y), QPointF(x + w, y + h / 2),
                QPointF(x + w - 6, y + h), QPointF(x + w - 6, y + h - 2),
                QPointF(x, y + h - 2),
            ]
            color = QColor(0, 200, 0, 210)
        else:
            pts = [
                QPointF(x + w, y + 2), QPointF(x + 6, y + 2),
                QPointF(x + 6, y), QPointF(x, y + h / 2),
                QPointF(x + 6, y + h), QPointF(x + 6, y + h - 2),
                QPointF(x + w, y + h - 2),
            ]
            color = QColor(220, 60, 60, 210)
        self.setPolygon(QPolygonF(pts))
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(120), 0.5))

        m = metadata
        direction = "Forward (→)" if not is_reverse else "Reverse (←)"
        tip = (
            f"{direction}\n"
            f"Sequence: {m.get('seq','')}\n"
            f"Position: {m.get('pos',0)+1}  Length: {m.get('len',0)}\n"
            f"Tm: {m.get('tm',0)}°C\n"
            f"Mismatches covered: {m.get('mm',0)}\n"
            f"Cluster: {m.get('cluster_id','?')}"
        )
        self.setToolTip(tip)
        self.setAcceptHoverEvents(True)


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setBackgroundBrush(QBrush(_DARK_BG))

        # State
        self.sequence = ""
        self.font_name = "Consolas"
        self.font_size = 10
        self.scheme_name = "Classic"
        self._recalc_metrics()

        self.cols_per_row = self.DEFAULT_COLS

        # Annotation data (kept for re-render)
        self._mismatches = []
        self._clusters = []
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
    def load_sequence(self, seq: str):
        self.sequence = seq
        self._mismatches.clear()
        self._clusters.clear()
        self._primers.clear()
        self._amplicons.clear()
        self.sel_start = self.sel_end = None
        self.sel_items.clear()
        self.auto_cols_for_width()

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

    def add_amplicon_span(self, left_start, right_end, metadata):
        self._amplicons.append({
            "left_start": left_start, "right_end": right_end,
            "meta": metadata,
        })

    def finish_annotations(self):
        self._rebuild()

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

            # --- Dynamic primer/amplicon tracks (stacked per pair_rank) ---
            pair_ranks = row_pairs.get(row_idx, [])
            primer_base_y = cl_y + CLUSTER_H + TRACK_GAP
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
            fixed_h = RULER_H + SEQ_H + MM_H + TRACK_GAP + CLUSTER_H + TRACK_GAP
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
            fixed_h = RULER_H + SEQ_H + MM_H + TRACK_GAP + CLUSTER_H + TRACK_GAP
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
            fixed_h = RULER_H + SEQ_H + MM_H + TRACK_GAP + CLUSTER_H + TRACK_GAP
            y_acc += fixed_h + dynamic_h + 8

    def copy_sel(self):
        if self.sel_start is not None and self.sel_end is not None:
            s, e = sorted((self.sel_start, self.sel_end))
            QGuiApplication.clipboard().setText(self.sequence[s:e + 1])
