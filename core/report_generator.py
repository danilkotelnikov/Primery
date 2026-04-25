"""
report_generator.py

Generates comprehensive PDF (A4) and DOCX reports from primer design data.
Collects gene info, cluster composition, primer tables, and specificity results.
"""
import os
import sys
import json
import glob
import re
from datetime import datetime

# Ensure the embedded site-packages directory is on sys.path so that
# python-docx (and other bundled packages) are importable even when the
# app is launched with a system Python that lacks those packages.
_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_embed_site = os.path.join(_here, "python_embed", "Lib", "site-packages")
if os.path.isdir(_embed_site) and _embed_site not in sys.path:
    # Append instead of insert(0) so we don't override the active Conda/venv packages
    sys.path.append(_embed_site)


# ─────────────────────── Design constants ─────────────────────────────────────
# Color palette
C_GREEN_DARK   = "#1A4D2E"   # title / section headers
C_GREEN_MID    = "#2E7D4F"   # sub-headers
C_GREEN_LIGHT  = "#E8F5EC"   # alternating row tint (gene/cluster tables)
C_BLUE_DARK    = "#0D3B6E"   # primer table header
C_BLUE_LIGHT   = "#E8F0FB"   # alternating row tint (primer tables)
C_SPEC_DARK    = "#4A235A"   # specificity table header (purple)
C_SPEC_LIGHT   = "#F5EEF8"   # alternating row tint
C_RULE         = "#CCCCCC"   # grid lines
C_TEXT_DARK    = "#1A1A1A"
C_GOLD         = "#C9A84C"   # decorative accent line under title

_BUNDLED_GSANS = os.path.join(
    _here, "assets", "fonts",
    "GoogleSansFlex-VariableFont_GRAD,ROND,opsz,slnt,wdth,wght.ttf",
)
_USER_GSANS = (
    r"C:\Users\danil\AppData\Local\Microsoft\Windows\Fonts"
    r"\GoogleSansFlex-VariableFont_GRAD,ROND,opsz,slnt,wdth,wght.ttf"
)
_GSANS_PATH = _BUNDLED_GSANS if os.path.isfile(_BUNDLED_GSANS) else _USER_GSANS
_FONTS_AVAILABLE = os.path.isfile(_GSANS_PATH)


# ─────────────────────── Data collection ──────────────────────────────────────

class ReportDataCollector:
    """Collect all report data from the filesystem."""

    def __init__(self, workspace):
        self.workspace = workspace

    def collect(self, organism, gene):
        """Return a dict with all data for one organism/gene pair."""
        org_root = os.path.join(self.workspace, organism)
        blast_dir = os.path.join(org_root, "BLAST", gene)
        genes_dir = os.path.join(org_root, "Genes", gene)
        spec_dir  = os.path.join(org_root, "Primer-BLAST")

        data = {
            "organism": organism,
            "gene": gene,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "reference": {},
            "clusters": [],
            "primer_sets": [],
            "probe_sets": [],
            "specificity": [],
            "specificity_table": [],   # parsed rows for the table
        }

        # --- Reference FASTA info ---
        if os.path.isdir(genes_dir):
            for fn in os.listdir(genes_dir):
                if fn.endswith(".fasta"):
                    fp = os.path.join(genes_dir, fn)
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    seq = "".join(l.strip() for l in lines if not l.startswith(">"))
                    header = lines[0].strip() if lines else ""
                    if not data["reference"] or len(seq) > data["reference"].get("length", 0):
                        data["reference"] = {
                            "file": fn,
                            "header": header,
                            "length": len(seq),
                            "accession": header.split()[0].lstrip(">") if header else "",
                        }

        # --- Cluster metadata ---
        meta_path = os.path.join(blast_dir, f"{gene}_cluster_meta.json")
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            data["n_accessions"] = meta.get("n_accessions", 0)
            data["n_species"]    = meta.get("n_species", 0)
            for cl in meta.get("clusters", []):
                data["clusters"].append({
                    "id":          cl["cluster_id"],
                    "rank":        cl["cluster_rank"],
                    "span":        f"{cl['span_start']}-{cl['span_end']}",
                    "n_positions": cl["n_positions"],
                    "n_species":   cl.get("n_species", 0),
                    "top_species": ", ".join(cl.get("species", [])[:5]),
                })

        # --- Primer sets ---
        primer_files = glob.glob(os.path.join(blast_dir, f"{gene}_*_primers.json"))
        primer_file_re = re.compile(rf"^{re.escape(gene)}_(.+?)_primers\.json$")
        for pf in primer_files:
            match = primer_file_re.match(os.path.basename(pf))
            if not match:
                continue
            method = match.group(1)
            with open(pf, "r", encoding="utf-8") as f:
                pairs = json.load(f)
            primer_set = {"method": method.upper(), "pairs": []}
            for i, p in enumerate(pairs):
                primer_set["pairs"].append({
                    "rank":         p.get("global_rank", i + 1),
                    "fwd_seq":      p.get("left", ""),
                    "fwd_tm":       round(p.get("left_tm", 0), 1),
                    "fwd_pos":      p.get("left_pos", 0),
                    "fwd_len":      p.get("left_len", 0),
                    "rev_seq":      p.get("right", ""),
                    "rev_tm":       round(p.get("right_tm", 0), 1),
                    "rev_pos":      p.get("right_pos", 0),
                    "rev_len":      p.get("right_len", 0),
                    "product_size": p.get("product_size", 0),
                    "fwd_cluster":  p.get("fwd_cluster_id", "?"),
                    "rev_cluster":  p.get("rev_cluster_id", "?"),
                    "n_species":    p.get("n_species_covered", 0),
                })
            data["primer_sets"].append(primer_set)

        # --- Probe sets ---
        flat_probe_files = glob.glob(os.path.join(blast_dir, f"{gene}_*_probes.json"))
        nested_probe_files = glob.glob(os.path.join(blast_dir, "Probes", "**", f"{gene}_*_probes.json"), recursive=True)
        probe_file_map = {os.path.basename(p): p for p in sorted(flat_probe_files)}
        for path in sorted(nested_probe_files):
            probe_file_map[os.path.basename(path)] = path
        probe_files = list(probe_file_map.values())
        probe_file_re = re.compile(rf"^{re.escape(gene)}_(.+?)_probes\.json$")
        for pf in probe_files:
            match = probe_file_re.match(os.path.basename(pf))
            if not match:
                continue
            chemistry = match.group(1)
            with open(pf, "r", encoding="utf-8") as f:
                probes = json.load(f)
            data["probe_sets"].append({
                "chemistry": chemistry.upper(),
                "probes": probes if isinstance(probes, list) else [probes],
            })

        # --- Specificity reports ---
        if os.path.isdir(spec_dir):
            safe_gene = re.sub(r"[^A-Za-z0-9_.-]+", "_", gene).strip("_")
            named_report_re = re.compile(
                rf"^PrimerBLAST_{re.escape(safe_gene)}_(.+?)_\d{{8}}_\d{{6}}\.txt$"
            )
            generic_report_re = re.compile(r"^PrimerBLAST_\d{8}_\d{6}\.txt$")
            for sf in sorted(glob.glob(os.path.join(spec_dir, "PrimerBLAST_*.txt"))):
                sf_name = os.path.basename(sf)
                source_method = ""
                method_match = named_report_re.match(sf_name)
                if method_match:
                    source_method = method_match.group(1).upper()
                elif not generic_report_re.match(sf_name):
                    # New per-gene reports for other genes should not bleed into
                    # this gene's primer tables. Keep legacy timestamp-only
                    # reports readable.
                    continue
                with open(sf, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                # Parse summary lines (kept for possible future use)
                summary_lines = []
                for line in content.split("\n"):
                    ls = line.strip()
                    if ls.startswith("Pair") or ls.startswith("="):
                        summary_lines.append(ls)
                    elif any(k in ls.upper() for k in ("SPECIFIC", "PASS", "FAIL")):
                        summary_lines.append(ls)

                # Parse structured per-pair rows for the specificity table
                spec_rows = _parse_specificity_rows(content)

                data["specificity"].append({
                    "file":      sf_name,
                    "summary":   "\n".join(summary_lines[:30]) if summary_lines else "",
                    "full_path": sf,
                    "rows":      spec_rows,
                })

                # Flat list for the combined table
                for row in spec_rows:
                    row["source_file"] = sf_name
                    row["method"] = source_method
                    data["specificity_table"].append(row)

        return data


def _parse_specificity_rows(content):
    """
    Parse PrimerBLAST report text into a list of dicts:
      rank, status, target_hits, off_target_hits, product_size, mismatches
    """
    rows = []
    current = {}
    for line in content.split("\n"):
        ls = line.strip()
        m = re.match(r"^Pair:\s*(.+)", ls)
        if m:
            if current:
                rows.append(current)
            current = {"rank": m.group(1).strip(), "status": "—",
                       "target_hits": "—", "off_target_hits": "—",
                       "product_size": "—", "mismatches": "—"}
            continue
        if current:
            m2 = re.match(r"Status:\s*(.+)", ls)
            if m2:
                current["status"] = m2.group(1).strip()
            m3 = re.match(r"Target Hits:\s*(.+)", ls)
            if m3:
                current["target_hits"] = m3.group(1).strip()
            m4 = re.match(r"Off-Target Hits:\s*(.+)", ls)
            if m4:
                current["off_target_hits"] = m4.group(1).strip()
            m5 = re.match(r"Product Size:\s*(.+)", ls)
            if m5 and current.get("product_size") == "—":
                current["product_size"] = m5.group(1).strip()
            m6 = re.match(r"Mismatches:\s*(.+)", ls)
            if m6 and current.get("mismatches") == "—":
                current["mismatches"] = m6.group(1).strip()
    if current:
        rows.append(current)
    return rows


def _rank_number(label):
    """Extract the pair rank without mixing in digits from gene names (COX1_Rank1)."""
    label = str(label or "")
    m = re.search(r"(?:^|[_\s-])Rank\s*([0-9]+)\b", label, re.I)
    if m:
        return m.group(1)
    m = re.fullmatch(r"\s*#?\s*([0-9]+)\s*", label)
    if m:
        return m.group(1)
    m = re.search(r"\bPair\s*([0-9]+)\b", label, re.I)
    if m:
        return m.group(1)
    return ""


def _specificity_by_rank(data, method):
    method = str(method or "").lower()
    spec_by_rank = {}
    for row in data.get("specificity_table", []):
        row_method = str(row.get("method") or "").lower()
        if row_method and method and row_method != method:
            continue
        rk_num = _rank_number(row.get("rank", ""))
        if rk_num:
            spec_by_rank[rk_num] = row
    return spec_by_rank


def _summary_rows(data):
    rows = []
    for ps in data.get("primer_sets", []):
        spec_by_rank = _specificity_by_rank(data, ps.get("method", ""))
        for p in ps.get("pairs", []):
            rank = str(p.get("rank", ""))
            spec = spec_by_rank.get(rank, {})
            rows.append({
                "method": ps.get("method", ""),
                "rank": rank,
                "type": "Forward primer",
                "sequence": p.get("fwd_seq", ""),
                "tm": p.get("fwd_tm", ""),
                "position": f"{p.get('fwd_pos', '')}+{p.get('fwd_len', '')}",
                "cluster": p.get("fwd_cluster", ""),
                "mod": "",
                "specificity": spec.get("status", ""),
                "off_targets": spec.get("off_target_hits", ""),
            })
            rows.append({
                "method": ps.get("method", ""),
                "rank": rank,
                "type": "Reverse primer",
                "sequence": p.get("rev_seq", ""),
                "tm": p.get("rev_tm", ""),
                "position": f"{p.get('rev_pos', '')}+{p.get('rev_len', '')}",
                "cluster": p.get("rev_cluster", ""),
                "mod": "",
                "specificity": spec.get("status", ""),
                "off_targets": spec.get("off_target_hits", ""),
            })
    for ps in data.get("probe_sets", []):
        for p in ps.get("probes", []):
            rows.append({
                "method": ps.get("chemistry", ""),
                "rank": p.get("rank", ""),
                "type": "Probe",
                "sequence": p.get("sequence", ""),
                "tm": p.get("tm", ""),
                "position": f"{p.get('start', 0) + 1}-{p.get('end', 0) + 1}",
                "cluster": ",".join(str(x) for x in p.get("mismatch_positions", [])),
                "mod": f"{p.get('dye', '')}/{p.get('quencher', '')}; " + ", ".join(p.get("modifications", [])),
                "specificity": f"{p.get('mm_covered', 0)} mismatches",
                "off_targets": p.get("n_species", ""),
            })
    return rows


# ═══════════════════════ PDF Generation ═══════════════════════════════════════

def generate_pdf(all_data, output_path, screenshot_path=None):
    """Generate an A4 PDF report using ReportLab with Google Sans typography."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor, white, black
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        Image, PageBreak, KeepTogether, HRFlowable,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # ── Register Google Sans Flex ─────────────────────────────────────────────
    # Variable font: register the same file four times under distinct names so
    # ReportLab can reference normal / bold / italic variants independently.
    if _FONTS_AVAILABLE:
        try:
            for _alias in ("GSans", "GSans-B", "GSans-I", "GSans-BI"):
                try:
                    pdfmetrics.registerFont(TTFont(_alias, _GSANS_PATH))
                except Exception:
                    pass
            from reportlab.pdfbase.pdfmetrics import registerFontFamily
            registerFontFamily("GSans",
                               normal="GSans", bold="GSans-B",
                               italic="GSans-I", boldItalic="GSans-BI")
            _sans = "GSans"
        except Exception:
            _sans = "Helvetica"
    else:
        _sans = "Helvetica"

    _sans_b = "GSans-B"  if _sans == "GSans" else "Helvetica-Bold"
    _sans_i = "GSans-I"  if _sans == "GSans" else "Helvetica-Oblique"

    # ── Page geometry ────────────────────────────────────────────────────────
    L_MARGIN = 22 * mm
    R_MARGIN = 22 * mm
    T_MARGIN = 22 * mm
    B_MARGIN = 22 * mm

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=L_MARGIN, rightMargin=R_MARGIN,
        topMargin=T_MARGIN,  bottomMargin=B_MARGIN,
    )
    page_w = A4[0] - L_MARGIN - R_MARGIN

    # ── Styles ───────────────────────────────────────────────────────────────
    base = getSampleStyleSheet()

    def _ps(name, **kw):
        kw.setdefault("fontName", _sans)
        return ParagraphStyle(name=name, **kw)

    sty = {
        "Title": _ps("RPTitle",
                     fontName=_sans_b, fontSize=20,
                     textColor=HexColor(C_GREEN_DARK),
                     leading=26, spaceAfter=2),
        "Subtitle": _ps("RPSubtitle",
                        fontName=_sans_i, fontSize=11,
                        textColor=HexColor(C_GREEN_MID),
                        leading=14, spaceAfter=2),
        "Meta": _ps("RPMeta",
                    fontSize=8, textColor=HexColor("#666666"),
                    leading=11, spaceAfter=10),
        "SectionH": _ps("RPSection",
                        fontName=_sans_b, fontSize=12,
                        textColor=HexColor(C_GREEN_DARK),
                        spaceBefore=14, spaceAfter=5, leading=16),
        "SubH": _ps("RPSubH",
                    fontName=_sans_b, fontSize=10,
                    textColor=HexColor(C_BLUE_DARK),
                    spaceBefore=10, spaceAfter=4, leading=13),
        "Body": _ps("RPBody", fontSize=9, leading=13, spaceAfter=4),
        "Cell": _ps("RPCell", fontSize=7, leading=9),
        "CellMono": ParagraphStyle(
            name="RPCellMono", fontName="Courier",
            fontSize=6.5, leading=8.5,
            textColor=HexColor(C_TEXT_DARK)),
        "CellSpec": _ps("RPCellSpec", fontSize=7, leading=9,
                        textColor=HexColor(C_TEXT_DARK)),
    }

    # ── Table style helpers ──────────────────────────────────────────────────
    def _tblstyle(hdr_color, row_tint, font_size=7.5):
        return TableStyle([
            # Header
            ("BACKGROUND",    (0, 0), (-1, 0),  HexColor(hdr_color)),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  white),
            ("FONTNAME",      (0, 0), (-1, 0),  _sans_b),
            ("FONTSIZE",      (0, 0), (-1, 0),  font_size),
            ("TOPPADDING",    (0, 0), (-1, 0),  4),
            ("BOTTOMPADDING", (0, 0), (-1, 0),  4),
            # Body
            ("FONTNAME",      (0, 1), (-1, -1), _sans),
            ("FONTSIZE",      (0, 1), (-1, -1), font_size - 0.5),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [HexColor(row_tint), white]),
            ("GRID",          (0, 0), (-1, -1), 0.35, HexColor(C_RULE)),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 1), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ])

    def _status_color(status):
        """Return a HexColor for a specificity status string."""
        s = status.upper()
        if "SPECIFIC" in s:
            return HexColor("#1A6B35")
        if "PASS" in s:
            return HexColor("#1A6B35")
        if "FAIL" in s or "NON" in s:
            return HexColor("#B71C1C")
        return HexColor(C_TEXT_DARK)

    # ── Build story ──────────────────────────────────────────────────────────
    story = []

    for data in all_data:
        # ── Cover block ──────────────────────────────────────────────────────
        story.append(Spacer(1, 6 * mm))

        # Decorative gold rule
        story.append(HRFlowable(
            width="100%", thickness=2.5,
            color=HexColor(C_GOLD), spaceAfter=5))

        story.append(Paragraph(
            f"Primer Design Report", sty["Title"]))
        story.append(Paragraph(
            f"<i>{data['organism']}</i> &mdash; {data['gene']}", sty["Subtitle"]))
        story.append(Paragraph(
            f"Generated: {data['timestamp']}", sty["Meta"]))

        # Thin green rule
        story.append(HRFlowable(
            width="100%", thickness=0.8,
            color=HexColor(C_GREEN_MID), spaceAfter=10))

        # -- 0. Summary -------------------------------------------------------
        summary = _summary_rows(data)
        if summary:
            story.append(Paragraph("0. Summary", sty["SectionH"]))
            sm_rows = [["Method", "#", "Type", "Sequence", "Tm", "Position", "Cluster/MM", "Mod", "Specificity", "Off-targets"]]
            for row in summary:
                sm_rows.append([
                    str(row["method"]),
                    str(row["rank"]),
                    row["type"],
                    Paragraph(str(row["sequence"]), sty["CellMono"]),
                    str(row["tm"]),
                    str(row["position"]),
                    str(row["cluster"]),
                    Paragraph(str(row["mod"]), sty["Cell"]),
                    str(row["specificity"]),
                    str(row["off_targets"]),
                ])
            cw0 = [page_w * x for x in [0.09, 0.035, 0.11, 0.245, 0.055, 0.08, 0.08, 0.13, 0.105, 0.07]]
            t0 = Table(sm_rows, colWidths=cw0, repeatRows=1)
            t0.setStyle(_tblstyle(C_SPEC_DARK, C_SPEC_LIGHT, font_size=6.8))
            story.append(t0)
            story.append(Spacer(1, 8))

        # ── 1. Gene Information ───────────────────────────────────────────────
        ref = data.get("reference", {})
        story.append(Paragraph("1. Gene Information", sty["SectionH"]))
        info_rows = [
            ["Parameter", "Value"],
            ["Gene",                 data["gene"]],
            ["Reference file",       ref.get("file", "N/A")],
            ["Accession",            ref.get("accession", "N/A")],
            ["Sequence length (bp)", str(ref.get("length", "N/A"))],
            ["BLAST accessions",     str(data.get("n_accessions", "N/A"))],
            ["Species covered",      str(data.get("n_species", "N/A"))],
        ]
        t = Table(info_rows, colWidths=[page_w * 0.38, page_w * 0.62])
        t.setStyle(_tblstyle(C_GREEN_DARK, C_GREEN_LIGHT, font_size=8))
        story.append(t)
        story.append(Spacer(1, 10))

        # ── 2. Mismatch Cluster Composition ───────────────────────────────────
        if data["clusters"]:
            story.append(Paragraph("2. Mismatch Cluster Composition", sty["SectionH"]))
            cl_rows = [["Rank", "ID", "Span (bp)", "Positions", "Species", "Representative species"]]
            for cl in data["clusters"]:
                cl_rows.append([
                    str(cl["rank"]), str(cl["id"]), cl["span"],
                    str(cl["n_positions"]), str(cl["n_species"]),
                    Paragraph(cl["top_species"], sty["Cell"]),
                ])
            cw = [page_w * x for x in [0.06, 0.06, 0.10, 0.09, 0.08, 0.61]]
            t = Table(cl_rows, colWidths=cw, repeatRows=1)
            t.setStyle(_tblstyle(C_GREEN_MID, C_GREEN_LIGHT))
            story.append(t)
            story.append(Spacer(1, 10))

        # ── 3+. Primer Pairs (per method) ────────────────────────────────────
        for ps_idx, ps in enumerate(data["primer_sets"], 1):
            sn = 2 + ps_idx
            story.append(Paragraph(
                f"{sn}. Primer Pairs &mdash; {ps['method']}", sty["SectionH"]))

            # Build a lookup: rank -> specificity status scoped to this method.
            spec_by_rank = _specificity_by_rank(data, ps["method"])

            pr_rows = [["#", "Forward 5'→3'", "Tm°C", "Reverse 5'→3'", "Tm°C",
                         "Product\n(bp)", "Fwd\nClust.", "Rev\nClust.", "Spp.", "Specificity"]]
            for p in ps["pairs"]:
                rank_str = str(p["rank"])
                spec = spec_by_rank.get(rank_str, {})
                status_text = spec.get("status", "—")
                otarg = spec.get("off_target_hits", "—")
                if status_text != "—":
                    spec_label = f"{status_text}"
                    if otarg not in ("—", "0", ""):
                        spec_label += f"\nOff-target: {otarg}"
                else:
                    spec_label = "—"

                # Color-code status text
                status_para = Paragraph(
                    f"<font color='{_status_color(status_text).hexval()}'>{spec_label}</font>",
                    sty["CellSpec"])

                pr_rows.append([
                    str(p["rank"]),
                    Paragraph(p["fwd_seq"], sty["CellMono"]),
                    str(p["fwd_tm"]),
                    Paragraph(p["rev_seq"], sty["CellMono"]),
                    str(p["rev_tm"]),
                    str(p["product_size"]),
                    str(p["fwd_cluster"]),
                    str(p["rev_cluster"]),
                    str(p["n_species"]),
                    status_para,
                ])

            cw = [page_w * x for x in [0.04, 0.22, 0.055, 0.22, 0.055,
                                        0.07, 0.055, 0.055, 0.055, 0.175]]
            t = Table(pr_rows, colWidths=cw, repeatRows=1)
            st = _tblstyle(C_BLUE_DARK, C_BLUE_LIGHT)
            # Right-align Tm columns
            st.add("ALIGN", (2, 0), (2, -1), "CENTER")
            st.add("ALIGN", (4, 0), (4, -1), "CENTER")
            st.add("ALIGN", (5, 0), (5, -1), "CENTER")
            st.add("ALIGN", (0, 0), (0, -1), "CENTER")
            t.setStyle(st)
            story.append(t)
            story.append(Spacer(1, 10))

        if data.get("probe_sets"):
            sn = 2 + len(data["primer_sets"]) + 1
            story.append(Paragraph(f"{sn}. Probes", sty["SectionH"]))
            for ps in data["probe_sets"]:
                story.append(Paragraph(ps.get("chemistry", "PROBE"), sty["SubH"]))
                prb_rows = [["#", "Chemistry", "Dye", "Quencher", "Mods", "Sequence", "Tm", "Pos", "MM", "Spp.", "Rationale"]]
                for p in ps.get("probes", []):
                    prb_rows.append([
                        str(p.get("rank", "")),
                        p.get("chemistry", ps.get("chemistry", "")),
                        p.get("dye", ""),
                        p.get("quencher", ""),
                        Paragraph(", ".join(p.get("modifications", [])), sty["Cell"]),
                        Paragraph(p.get("sequence", ""), sty["CellMono"]),
                        str(p.get("tm", "")),
                        f"{p.get('start', 0) + 1}-{p.get('end', 0) + 1}",
                        str(p.get("mm_covered", "")),
                        str(p.get("n_species", "")),
                        Paragraph(p.get("rationale", ""), sty["Cell"]),
                    ])
                cw_probe = [page_w * x for x in [0.035, 0.08, 0.045, 0.065, 0.11, 0.25, 0.045, 0.07, 0.04, 0.04, 0.22]]
                tp = Table(prb_rows, colWidths=cw_probe, repeatRows=1)
                tp.setStyle(_tblstyle(C_BLUE_DARK, C_BLUE_LIGHT, font_size=6.8))
                story.append(tp)
                story.append(Spacer(1, 8))

        # ── Specificity Summary Table ─────────────────────────────────────────
        if data.get("specificity_table"):
            sn = 2 + len(data["primer_sets"]) + (1 if data.get("probe_sets") else 0) + 1
            story.append(Paragraph(
                f"{sn}. Primer Specificity (BLAST)", sty["SectionH"]))

            # Group by source file
            by_file = {}
            for row in data["specificity_table"]:
                by_file.setdefault(row.get("source_file", ""), []).append(row)

            for fname, rows in by_file.items():
                story.append(Paragraph(
                    f"<i>{fname}</i>", sty["Body"]))
                spec_tbl = [["Pair", "Status", "Target\nHits",
                              "Off-target\nHits", "Product\n(bp)", "Mismatches"]]
                for r in rows:
                    status_text = r.get("status", "—")
                    status_para = Paragraph(
                        f"<font color='{_status_color(status_text).hexval()}'>"
                        f"<b>{status_text}</b></font>",
                        sty["CellSpec"])
                    spec_tbl.append([
                        r.get("rank", "—"),
                        status_para,
                        r.get("target_hits", "—"),
                        r.get("off_target_hits", "—"),
                        r.get("product_size", "—"),
                        r.get("mismatches", "—"),
                    ])
                cw2 = [page_w * x for x in [0.12, 0.28, 0.12, 0.13, 0.13, 0.22]]
                t2 = Table(spec_tbl, colWidths=cw2, repeatRows=1)
                st2 = _tblstyle(C_SPEC_DARK, C_SPEC_LIGHT, font_size=7.5)
                st2.add("ALIGN", (2, 0), (4, -1), "CENTER")
                t2.setStyle(st2)
                story.append(t2)
                story.append(Spacer(1, 8))

        # ── Sequence Map ─────────────────────────────────────────────────────
        if screenshot_path and os.path.isfile(screenshot_path):
            sn2 = 2 + len(data["primer_sets"]) + (2 if data["specificity"] else 1)
            story.append(Paragraph(f"{sn2}. Sequence Map", sty["SectionH"]))
            # Determine aspect ratio using ReportLab's built-in reader (no Pillow needed)
            try:
                from reportlab.lib.utils import ImageReader
                ir = ImageReader(screenshot_path)
                iw, ih = ir.getSize()
                aspect = ih / iw if iw > 0 else 0.4
            except Exception:
                aspect = 0.4
            img = Image(screenshot_path, width=page_w, height=page_w * aspect)
            img.hAlign = "CENTER"
            story.append(img)

        story.append(PageBreak())

    # ── Page footer (page numbers) ───────────────────────────────────────────
    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont(_sans, 7)
        canvas.setFillColor(HexColor("#888888"))
        canvas.drawRightString(
            A4[0] - R_MARGIN, B_MARGIN / 2,
            f"Page {doc_.page}")
        canvas.drawString(
            L_MARGIN, B_MARGIN / 2,
            "Primer Design Report — generated by FusariumPanel")
        canvas.setStrokeColor(HexColor(C_RULE))
        canvas.setLineWidth(0.4)
        canvas.line(L_MARGIN, B_MARGIN * 0.75,
                    A4[0] - R_MARGIN, B_MARGIN * 0.75)
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output_path


# ═══════════════════════ DOCX Generation ══════════════════════════════════════

def generate_docx(all_data, output_path, screenshot_path=None):
    """Generate an A4 DOCX report using python-docx with Google Sans typography."""
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm, Emu
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    import re as _re

    def _hex(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def _set_cell_bg(cell, hex_color):
        hex_color = hex_color.lstrip("#")
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        # Remove any existing shd
        for old in tcPr.findall(qn("w:shd")):
            tcPr.remove(old)
        tcPr.append(shd)

    def _set_cell_font(cell, size_pt, bold=False, color_hex=None,
                       font_name="Google Sans", italic=False):
        for para in cell.paragraphs:
            for run in para.runs:
                run.font.name      = font_name
                run.font.size      = Pt(size_pt)
                run.font.bold      = bold
                run.font.italic    = italic
                if color_hex:
                    r, g, b = _hex(color_hex)
                    run.font.color.rgb = RGBColor(r, g, b)

    def _add_table(doc, headers, rows,
                   hdr_hex=C_GREEN_DARK, row_tint=C_GREEN_LIGHT,
                   col_widths=None):
        n_cols = len(headers)
        table = doc.add_table(rows=1 + len(rows), cols=n_cols)
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        table.style = "Table Grid"

        # Set column widths if provided (in cm)
        if col_widths:
            for i, w in enumerate(col_widths):
                for row in table.rows:
                    row.cells[i].width = Cm(w)

        # Header row
        for i, h in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = h
            _set_cell_bg(cell, hdr_hex)
            _set_cell_font(cell, 7.5, bold=True,
                           color_hex="#FFFFFF", font_name="Google Sans")
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Body rows with alternating tint
        tint_hex = row_tint.lstrip("#")
        for r_idx, row_data in enumerate(rows):
            bg = tint_hex if r_idx % 2 == 0 else "FFFFFF"
            for c_idx, val in enumerate(row_data):
                cell = table.rows[r_idx + 1].cells[c_idx]
                cell.text = str(val)
                _set_cell_bg(cell, bg)
                _set_cell_font(cell, 7, font_name="Google Sans")

        return table

    def _add_spec_table(doc, headers, rows,
                        hdr_hex=C_SPEC_DARK, row_tint=C_SPEC_LIGHT,
                        col_widths=None):
        """Like _add_table but colorises Status column."""
        n_cols = len(headers)
        table = doc.add_table(rows=1 + len(rows), cols=n_cols)
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        table.style = "Table Grid"

        if col_widths:
            for i, w in enumerate(col_widths):
                for row_ in table.rows:
                    row_.cells[i].width = Cm(w)

        # Header
        for i, h in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = h
            _set_cell_bg(cell, hdr_hex)
            _set_cell_font(cell, 7.5, bold=True,
                           color_hex="#FFFFFF", font_name="Google Sans")
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Body
        STATUS_COL = 1  # second column
        tint_hex = row_tint.lstrip("#")
        for r_idx, row_data in enumerate(rows):
            bg = tint_hex if r_idx % 2 == 0 else "FFFFFF"
            for c_idx, val in enumerate(row_data):
                cell = table.rows[r_idx + 1].cells[c_idx]
                _set_cell_bg(cell, bg)
                if c_idx == STATUS_COL:
                    # Colour-code status
                    sval = str(val).upper()
                    if "SPECIFIC" in sval or "PASS" in sval:
                        col = "#1A6B35"
                    elif "FAIL" in sval or "NON" in sval:
                        col = "#B71C1C"
                    else:
                        col = C_TEXT_DARK
                    para = cell.paragraphs[0]
                    run = para.add_run(str(val))
                    run.font.name   = "Google Sans"
                    run.font.size   = Pt(7)
                    run.font.bold   = True
                    r_, g_, b_ = _hex(col)
                    run.font.color.rgb = RGBColor(r_, g_, b_)
                else:
                    cell.text = str(val)
                    _set_cell_font(cell, 7, font_name="Google Sans")

        return table

    # ── Document setup ────────────────────────────────────────────────────────
    doc = Document()

    section = doc.sections[0]
    section.page_width    = Cm(21.0)
    section.page_height   = Cm(29.7)
    section.left_margin   = Cm(2.2)
    section.right_margin  = Cm(2.2)
    section.top_margin    = Cm(2.2)
    section.bottom_margin = Cm(2.0)

    # Default body style → Google Sans 10
    nstyle = doc.styles["Normal"]
    nstyle.font.name = "Google Sans"
    nstyle.font.size = Pt(10)

    # Heading 1: large, dark green, Google Sans
    h1 = doc.styles["Heading 1"]
    h1.font.name  = "Google Sans"
    h1.font.size  = Pt(16)
    h1.font.bold  = True
    h1.font.color.rgb = RGBColor(*_hex(C_GREEN_DARK))

    # Heading 2: medium, mid green, Google Sans
    h2 = doc.styles["Heading 2"]
    h2.font.name  = "Google Sans"
    h2.font.size  = Pt(11)
    h2.font.bold  = True
    h2.font.color.rgb = RGBColor(*_hex(C_GREEN_MID))

    def _add_rule(doc_, color_hex="#CCCCCC", thickness_pt=0.5):
        """Insert a thin horizontal rule via a paragraph border."""
        para = doc_.add_paragraph()
        pPr = para._element.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bot = OxmlElement("w:bottom")
        bot.set(qn("w:val"), "single")
        bot.set(qn("w:sz"), str(int(thickness_pt * 8)))  # eighths of a point
        bot.set(qn("w:space"), "1")
        bot.set(qn("w:color"), color_hex.lstrip("#"))
        pBdr.append(bot)
        pPr.append(pBdr)
        para.paragraph_format.space_before = Pt(0)
        para.paragraph_format.space_after  = Pt(4)
        return para

    # ── Per organism/gene ─────────────────────────────────────────────────────
    content_width_cm = (21.0 - 2.2 - 2.2)  # 16.6 cm usable

    for data_idx, data in enumerate(all_data):
        # ── Title block ──────────────────────────────────────────────────────
        # Gold decorative rule
        _add_rule(doc, color_hex=C_GOLD.lstrip("#"), thickness_pt=2.5)

        h = doc.add_heading("Primer Design Report", level=1)
        h.runs[0].font.name  = "Google Sans"
        h.runs[0].font.bold  = True

        sub = doc.add_paragraph()
        sub_run = sub.add_run(f"{data['organism']} — {data['gene']}")
        sub_run.font.name   = "Google Sans"
        sub_run.font.size   = Pt(12)
        sub_run.font.italic = True
        sub_run.font.color.rgb = RGBColor(*_hex(C_GREEN_MID))

        meta = doc.add_paragraph(f"Generated: {data['timestamp']}")
        meta.runs[0].font.name  = "Google Sans"
        meta.runs[0].font.size  = Pt(8)
        meta.runs[0].font.color.rgb = RGBColor(0x88, 0x88, 0x88)

        _add_rule(doc, color_hex=C_GREEN_MID.lstrip("#"), thickness_pt=0.8)

        summary = _summary_rows(data)
        if summary:
            doc.add_heading("0. Summary", level=2)
            _add_table(
                doc,
                ["Method", "#", "Type", "Sequence", "Tm", "Position", "Cluster/MM", "Mod", "Specificity", "Off-targets"],
                [[
                    r["method"], r["rank"], r["type"], r["sequence"], r["tm"],
                    r["position"], r["cluster"], r["mod"], r["specificity"], r["off_targets"],
                ] for r in summary],
                hdr_hex=C_SPEC_DARK,
                row_tint=C_SPEC_LIGHT,
                col_widths=[content_width_cm * x for x in [0.09, 0.04, 0.11, 0.25, 0.05, 0.08, 0.08, 0.13, 0.10, 0.07]],
            )
            doc.add_paragraph("")

        # ── 1. Gene Information ───────────────────────────────────────────────
        doc.add_heading("1. Gene Information", level=2)
        ref = data.get("reference", {})
        cw = [content_width_cm * 0.38, content_width_cm * 0.62]
        _add_table(doc,
                   ["Parameter", "Value"],
                   [
                       ["Gene",                  data["gene"]],
                       ["Reference file",         ref.get("file", "N/A")],
                       ["Accession",              ref.get("accession", "N/A")],
                       ["Sequence length (bp)",   str(ref.get("length", "N/A"))],
                       ["BLAST accessions",       str(data.get("n_accessions", "N/A"))],
                       ["Species covered",        str(data.get("n_species", "N/A"))],
                   ],
                   hdr_hex=C_GREEN_DARK, row_tint=C_GREEN_LIGHT,
                   col_widths=cw)
        doc.add_paragraph("")

        # ── 2. Mismatch Cluster Composition ──────────────────────────────────
        if data["clusters"]:
            doc.add_heading("2. Mismatch Cluster Composition", level=2)
            cw2 = [content_width_cm * x for x in [0.06, 0.06, 0.11, 0.09, 0.09, 0.59]]
            _add_table(doc,
                       ["Rank", "ID", "Span (bp)", "Positions", "Species", "Representative species"],
                       [[cl["rank"], cl["id"], cl["span"], cl["n_positions"],
                         cl["n_species"], cl["top_species"]] for cl in data["clusters"]],
                       hdr_hex=C_GREEN_MID, row_tint=C_GREEN_LIGHT,
                       col_widths=cw2)
            doc.add_paragraph("")

        # ── 3+. Primer Pairs ─────────────────────────────────────────────────
        for ps_idx, ps in enumerate(data["primer_sets"], 1):
            sn = 2 + ps_idx
            doc.add_heading(f"{sn}. Primer Pairs — {ps['method']}", level=2)
            spec_by_rank = _specificity_by_rank(data, ps["method"])

            hdrs = ["#", "Forward 5'→3'", "Tm°C", "Reverse 5'→3'", "Tm°C",
                    "Product (bp)", "Fwd Cl.", "Rev Cl.", "Spp.", "Specificity"]
            cw3 = [content_width_cm * x for x in
                   [0.05, 0.21, 0.06, 0.21, 0.06, 0.08, 0.06, 0.06, 0.06, 0.15]]

            rows_pr = []
            for p in ps["pairs"]:
                rank_str = str(p["rank"])
                spec = spec_by_rank.get(rank_str, {})
                status = spec.get("status", "—")
                otarg  = spec.get("off_target_hits", "—")
                if status != "—" and otarg not in ("—", "0", ""):
                    spec_text = f"{status} / Off-tgt: {otarg}"
                elif status != "—":
                    spec_text = status
                else:
                    spec_text = "—"
                rows_pr.append([
                    str(p["rank"]),
                    p["fwd_seq"],
                    str(p["fwd_tm"]),
                    p["rev_seq"],
                    str(p["rev_tm"]),
                    str(p["product_size"]),
                    str(p["fwd_cluster"]),
                    str(p["rev_cluster"]),
                    str(p["n_species"]),
                    spec_text,
                ])

            # Use a custom table that colorises the Specificity column
            n_cols = len(hdrs)
            table = doc.add_table(rows=1 + len(rows_pr), cols=n_cols)
            table.alignment = WD_TABLE_ALIGNMENT.LEFT
            table.style = "Table Grid"
            for i, w in enumerate(cw3):
                for row_ in table.rows:
                    row_.cells[i].width = Cm(w)

            # Header
            for i, h_txt in enumerate(hdrs):
                cell = table.rows[0].cells[i]
                cell.text = h_txt
                _set_cell_bg(cell, C_BLUE_DARK)
                _set_cell_font(cell, 7, bold=True,
                               color_hex="#FFFFFF", font_name="Google Sans")
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

            SPEC_COL = 9
            tint = C_BLUE_LIGHT.lstrip("#")
            for r_idx, row_data in enumerate(rows_pr):
                bg = tint if r_idx % 2 == 0 else "FFFFFF"
                for c_idx, val in enumerate(row_data):
                    cell = table.rows[r_idx + 1].cells[c_idx]
                    _set_cell_bg(cell, bg)
                    if c_idx == SPEC_COL:
                        sval = str(val).upper()
                        if "SPECIFIC" in sval or "PASS" in sval:
                            col = "#1A6B35"
                        elif "FAIL" in sval or "NON" in sval:
                            col = "#B71C1C"
                        else:
                            col = C_TEXT_DARK
                        para = cell.paragraphs[0]
                        run  = para.add_run(str(val))
                        run.font.name  = "Google Sans"
                        run.font.size  = Pt(6.5)
                        run.font.bold  = True
                        r_, g_, b_ = _hex(col)
                        run.font.color.rgb = RGBColor(r_, g_, b_)
                    else:
                        # Monospace for sequences
                        if c_idx in (1, 3):
                            cell.text = str(val)
                            for p_ in cell.paragraphs:
                                for r_ in p_.runs:
                                    r_.font.name = "Courier New"
                                    r_.font.size = Pt(6)
                        else:
                            cell.text = str(val)
                            _set_cell_font(cell, 6.5, font_name="Google Sans")

            doc.add_paragraph("")

        if data.get("probe_sets"):
            sn = 2 + len(data["primer_sets"]) + 1
            doc.add_heading(f"{sn}. Probes", level=2)
            for ps in data["probe_sets"]:
                doc.add_heading(ps.get("chemistry", "PROBE"), level=3)
                _add_table(
                    doc,
                    ["#", "Chemistry", "Dye", "Quencher", "Mods", "Sequence", "Tm", "Pos", "MM", "Spp.", "Rationale"],
                    [[
                        p.get("rank", ""),
                        p.get("chemistry", ps.get("chemistry", "")),
                        p.get("dye", ""),
                        p.get("quencher", ""),
                        ", ".join(p.get("modifications", [])),
                        p.get("sequence", ""),
                        p.get("tm", ""),
                        f"{p.get('start', 0) + 1}-{p.get('end', 0) + 1}",
                        p.get("mm_covered", ""),
                        p.get("n_species", ""),
                        p.get("rationale", ""),
                    ] for p in ps.get("probes", [])],
                    hdr_hex=C_BLUE_DARK,
                    row_tint=C_BLUE_LIGHT,
                    col_widths=[content_width_cm * x for x in [0.04, 0.08, 0.05, 0.07, 0.11, 0.24, 0.05, 0.07, 0.04, 0.04, 0.21]],
                )
            doc.add_paragraph("")

        # ── Specificity Summary Table ─────────────────────────────────────────
        if data.get("specificity_table"):
            sn = 2 + len(data["primer_sets"]) + (1 if data.get("probe_sets") else 0) + 1
            doc.add_heading(f"{sn}. Primer Specificity (BLAST)", level=2)

            # Group by source file
            by_file = {}
            for row in data["specificity_table"]:
                by_file.setdefault(row.get("source_file", ""), []).append(row)

            for fname, rows in by_file.items():
                p = doc.add_paragraph()
                r_ = p.add_run(fname)
                r_.font.name   = "Google Sans"
                r_.font.size   = Pt(8)
                r_.font.italic = True

                hdrs_s = ["Pair", "Status", "Target Hits",
                          "Off-target Hits", "Product (bp)", "Mismatches"]
                cw_s = [content_width_cm * x
                        for x in [0.13, 0.27, 0.13, 0.14, 0.14, 0.19]]
                rows_s = [
                    [r.get("rank", "—"),
                     r.get("status", "—"),
                     r.get("target_hits", "—"),
                     r.get("off_target_hits", "—"),
                     r.get("product_size", "—"),
                     r.get("mismatches", "—")]
                    for r in rows
                ]
                _add_spec_table(doc, hdrs_s, rows_s,
                                hdr_hex=C_SPEC_DARK, row_tint=C_SPEC_LIGHT,
                                col_widths=cw_s)
                doc.add_paragraph("")

        # ── Sequence Map ─────────────────────────────────────────────────────
        if screenshot_path and os.path.isfile(screenshot_path):
            sn2 = 2 + len(data["primer_sets"]) + (2 if data["specificity"] else 1)
            doc.add_heading(f"{sn2}. Sequence Map", level=2)
            doc.add_picture(screenshot_path, width=Cm(content_width_cm))

        if data_idx < len(all_data) - 1:
            doc.add_page_break()

    doc.save(output_path)
    return output_path
