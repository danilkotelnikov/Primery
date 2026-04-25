"""
Mismatch-focused probe design helpers.

This module designs candidate hydrolysis probes, molecular beacons, and RPA exo
probes by scanning windows around conservative mismatch clusters. Primer3 is
used for Tm calculation when available; the scanner remains deterministic if
primer3 is unavailable.
"""

from typing import Dict, List, Optional, Set

try:
    import primer3
except ImportError:
    primer3 = None

from .probe_catalog import CHEMISTRY_DEFAULTS, chemistry_note, validate_combo

_COMP = str.maketrans("ACGTRYMKBDHVNacgtrymkbdhvn", "TGCAYRKMVHDBNtgcayrkmvhdbn")


def _revcomp(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _gc(seq: str) -> float:
    seq = seq.upper()
    return 100.0 * (seq.count("G") + seq.count("C")) / max(len(seq), 1)


def _tm(seq: str) -> float:
    seq = seq.upper()
    if primer3:
        try:
            return round(float(primer3.calc_tm(seq)), 1)
        except Exception:
            pass
    at = seq.count("A") + seq.count("T")
    gc = seq.count("G") + seq.count("C")
    return round(2 * at + 4 * gc, 1)


def _cluster_positions(clusters: List[Dict]) -> Dict[int, Set[str]]:
    pos_species: Dict[int, Set[str]] = {}
    for cl in clusters or []:
        species = set(cl.get("species", []))
        for pos in cl.get("positions", []):
            try:
                pos_species.setdefault(int(pos), set()).update(species)
            except (TypeError, ValueError):
                continue
    return pos_species


def _windows_for_chemistry(chemistry: str):
    if chemistry == "rpa_exo":
        return range(46, 53), (0, 100)
    if chemistry == "molecular_beacon":
        return range(25, 41), (55, 75)
    if chemistry == "taqman_mgb":
        return range(13, 23), (62, 75)
    return range(18, 31), (62, 75)


def _scan_region(seq: str, start0: int, end0: int, lengths, pos_species: Dict[int, Set[str]]):
    seq = seq.upper()
    mm_positions0 = {p - 1 for p in pos_species}
    for length in lengths:
        if length <= 0:
            continue
        for start in range(max(0, start0), max(0, end0 - length + 2)):
            end = start + length
            if end > len(seq):
                continue
            window = seq[start:end]
            if any(base not in "ACGTRYMKBDHVN" for base in window):
                continue
            hits = sorted((mm_positions0 & set(range(start, end))))
            if not hits:
                continue
            species = set()
            for p0 in hits:
                species.update(pos_species.get(p0 + 1, set()))
            yield start, window, hits, species


def _amplicon_bounds(seq_len: int, fwd_primer: Optional[Dict], rev_primer: Optional[Dict]):
    if not fwd_primer or not rev_primer:
        return 0, seq_len - 1
    left_start = int(fwd_primer.get("left_pos", 0)) + int(fwd_primer.get("left_len", 0))
    right_end = int(rev_primer.get("right_pos", seq_len - 1)) - int(rev_primer.get("right_len", 0))
    if right_end <= left_start:
        return 0, seq_len - 1
    return max(0, left_start), min(seq_len - 1, right_end)


def _format_probe_sequence(chemistry: str, seq: str, hits: List[int], start0: int):
    if chemistry == "molecular_beacon":
        stem = "CGCGC"
        return stem + seq + _revcomp(stem)
    if chemistry == "rpa_exo":
        # Place THF close to the best covered mismatch where possible.
        hit_rel = max(0, min(len(seq) - 1, hits[0] - start0)) if hits else len(seq) // 2
        thf_pos = min(max(hit_rel, 15), len(seq) - 16)
        return seq[:thf_pos] + "[THF]" + seq[thf_pos + 1:]
    return seq


def _label_quencher(quencher: str) -> str:
    return {
        "BHQ1": "BHQ-1",
        "BHQ2": "BHQ-2",
        "BHQ3": "BHQ-3",
        "MGB-NFQ": "MGB-NFQ",
    }.get(quencher, quencher)


def _select_lna_positions(core_seq: str, hits: List[int], start0: int, max_lna: int = 3) -> List[int]:
    """Return global 0-based positions to LNA-modify.

    LNA is reserved for the most discriminatory internal mismatch bases:
    cap at three, avoid probe termini, and avoid adjacent LNA residues.
    """
    if max_lna <= 0:
        return []
    length = len(core_seq or "")
    if length <= 0:
        return []
    rel_hits = sorted({p - start0 for p in hits if 0 <= p - start0 < length})
    if not rel_hits:
        return []

    center = (length - 1) / 2.0
    internal = [r for r in rel_hits if 3 <= r <= length - 4]
    if not internal:
        internal = [r for r in rel_hits if 1 <= r <= length - 2] or rel_hits

    scored = sorted(internal, key=lambda r: (abs(r - center), -min(r, length - 1 - r), r))
    selected: List[int] = []
    for rel in scored:
        if len(selected) >= max_lna:
            break
        if any(abs(rel - prev) <= 1 for prev in selected):
            continue
        selected.append(rel)

    return sorted(start0 + rel for rel in selected)


def _format_order_sequence(
    chemistry: str,
    core_seq: str,
    displayed_seq: str,
    hits: List[int],
    start0: int,
    dye: str,
    quencher: str,
    modifications: List[str],
    lna_positions: Optional[List[int]] = None,
) -> str:
    lna_rel = {p - start0 for p in (lna_positions or _select_lna_positions(core_seq, hits, start0))}
    body = []
    for i, base in enumerate(core_seq):
        if "LNA" in modifications and i in lna_rel and base in "ACGT":
            body.append(f"[{base}+]")
        else:
            body.append(base)
    body = "".join(body)
    if chemistry == "molecular_beacon":
        stem = "CGCGC"
        body = stem + body + _revcomp(stem)
    if chemistry == "rpa_exo":
        body = displayed_seq
    if "MGB" in modifications and chemistry != "taqman_mgb":
        body += "[MGB]"
    suffix = f"[{_label_quencher(quencher)}]"
    if "3p_C3_spacer" in modifications:
        suffix += "[C3]"
    return f"[{dye}]{body}{suffix}"


def design_probes(
    seq: str,
    clusters: List[Dict],
    chemistry: str = "taqman",
    fwd_primer: Optional[Dict] = None,
    rev_primer: Optional[Dict] = None,
    dye: Optional[str] = None,
    quencher: Optional[str] = None,
    modifications: Optional[List[str]] = None,
    n_top: int = 5,
) -> List[Dict]:
    seq = "".join(str(seq or "").split()).upper()
    if not seq:
        return []

    chemistry = (chemistry or "taqman").lower()
    defaults = CHEMISTRY_DEFAULTS.get(chemistry, CHEMISTRY_DEFAULTS["taqman"])
    dye = dye or defaults["dye"]
    quencher = quencher or defaults["quencher"]
    if modifications is None:
        modifications = list(defaults.get("mods", []))

    compatible, combo_note = validate_combo(dye, quencher)
    lengths, tm_range = _windows_for_chemistry(chemistry)
    pos_species = _cluster_positions(clusters)
    if not pos_species:
        return []

    start0, end0 = _amplicon_bounds(len(seq), fwd_primer, rev_primer)
    if end0 - start0 < min(lengths):
        start0, end0 = 0, len(seq) - 1

    candidates = []
    for start, probe_seq, hits, species in _scan_region(seq, start0, end0, lengths, pos_species):
        tm = _tm(probe_seq)
        gc = _gc(probe_seq)
        tm_ok = tm_range[0] <= tm <= tm_range[1] if tm_range[1] < 100 else True
        gc_penalty = 0 if 35 <= gc <= 65 else 2
        tm_penalty = 0 if tm_ok else min(abs(tm - tm_range[0]), abs(tm - tm_range[1])) / 2
        score = len(species) * 10 + len(hits) * 5 - gc_penalty - tm_penalty
        displayed_seq = _format_probe_sequence(chemistry, probe_seq, hits, start)
        lna_positions0 = _select_lna_positions(probe_seq, hits, start) if "LNA" in modifications else []
        lna_note = (
            "LNA capped at <=3 internal, non-adjacent mismatch bases."
            if lna_positions0 else ""
        )
        candidates.append({
            "chemistry": chemistry,
            "type": "Probe",
            "sequence": displayed_seq,
            "core_sequence": probe_seq,
            "formatted_sequence": _format_order_sequence(
                chemistry, probe_seq, displayed_seq, hits, start,
                dye, quencher, modifications,
                lna_positions=lna_positions0,
            ),
            "start": start,
            "end": start + len(probe_seq) - 1,
            "length": len(probe_seq),
            "tm": tm,
            "gc": round(gc, 1),
            "dye": dye,
            "quencher": quencher,
            "modifications": modifications,
            "lna_positions": [p + 1 for p in lna_positions0],
            "lna_count": len(lna_positions0),
            "lna_design_note": lna_note,
            "combo_ok": compatible,
            "combo_note": combo_note,
            "mm_covered": len(hits),
            "mismatch_positions": [p + 1 for p in hits],
            "n_species": len(species),
            "species": sorted(species, key=str.lower),
            "score": round(score, 1),
            "rationale": chemistry_note(chemistry),
        })

    candidates.sort(key=lambda x: (-x["score"], abs(x["gc"] - 50), x["start"]))
    picked = []
    used_ranges = []
    for cand in candidates:
        if len(picked) >= n_top:
            break
        overlap = False
        for s, e in used_ranges:
            if not (cand["end"] < s or cand["start"] > e):
                overlap = True
                break
        if overlap:
            continue
        cand["rank"] = len(picked) + 1
        picked.append(cand)
        used_ranges.append((cand["start"], cand["end"]))
    return picked
