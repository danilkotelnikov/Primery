"""
Combined primer/probe specificity classification.

The assay-level classifier evaluates Primer-BLAST amplicons first, then tests
whether the selected probe hybridizes to target amplicons and discriminates
off-target amplicons. It remains conservative when amplicon sequences are not
available: those rows are reported as not fully assessed rather than rescued.
"""

from typing import Dict, List, Optional, Tuple

_COMP = str.maketrans("ACGTRYMKBDHVNacgtrymkbdhvn", "TGCAYRKMVHDBNtgcayrkmvhdbn")


def _revcomp(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _plain_probe_sequence(probe: Dict) -> str:
    seq = probe.get("core_sequence") or probe.get("sequence") or probe.get("formatted_sequence") or ""
    out = []
    in_bracket = False
    for ch in str(seq):
        if ch == "[":
            in_bracket = True
            continue
        if ch == "]":
            in_bracket = False
            continue
        if not in_bracket and ch.upper() in "ACGTRYMKBDHVN":
            out.append(ch.upper())
    return "".join(out)


def _amplicon_sequence(amp: Dict) -> str:
    return "".join(str(amp.get("sequence") or "").split()).upper()


def _amplicon_relevant(amp: Dict) -> bool:
    try:
        total_mm = int(amp.get("f_mm", 99)) + int(amp.get("r_mm", 99))
    except (TypeError, ValueError):
        total_mm = 99
    return bool(amp.get("f_3p", True)) and bool(amp.get("r_3p", True)) and total_mm < 5


def _is_target_amplicon(amp: Dict, target_organism: str = "") -> bool:
    if "is_target_species" in amp:
        return bool(amp.get("is_target_species"))
    target = str(target_organism or "").strip().lower()
    return bool(target and target in str(amp.get("title", "")).lower())


def _best_probe_alignment(probe_seq: str, amp_seq: str) -> Optional[Dict]:
    probe_seq = "".join(probe_seq.split()).upper()
    amp_seq = "".join(amp_seq.split()).upper()
    if not probe_seq or not amp_seq or len(amp_seq) < len(probe_seq):
        return None

    best = None
    for strand, query in (("+", probe_seq), ("-", _revcomp(probe_seq))):
        qlen = len(query)
        center_lo = max(0, qlen // 2 - 2)
        center_hi = min(qlen - 1, qlen // 2 + 2)
        for start in range(0, len(amp_seq) - qlen + 1):
            window = amp_seq[start:start + qlen]
            mismatches = [
                i for i, (a, b) in enumerate(zip(query, window))
                if a != "N" and b != "N" and a != b
            ]
            central = [i for i in mismatches if center_lo <= i <= center_hi]
            score = (len(mismatches), -len(central), start)
            if best is None or score < best["_score"]:
                best = {
                    "_score": score,
                    "strand": strand,
                    "start": start,
                    "end": start + qlen - 1,
                    "mismatches": len(mismatches),
                    "mismatch_offsets": mismatches,
                    "central_mismatches": len(central),
                    "probe_length": qlen,
                }
    if best:
        best.pop("_score", None)
    return best


def _lna_offsets(probe: Dict, probe_start0: int = 0) -> List[int]:
    offsets = []
    for value in probe.get("lna_positions") or []:
        try:
            # Stored as 1-based genomic/query positions.
            offsets.append(int(value) - 1 - probe_start0)
        except (TypeError, ValueError):
            continue
    return offsets


def _alignment_discriminates(aln: Dict, probe: Dict, probe_start0: int = 0) -> bool:
    mismatches = set(aln.get("mismatch_offsets") or [])
    if len(mismatches) >= 2:
        return True
    if aln.get("central_mismatches", 0) >= 1:
        return True
    lna_hits = mismatches & set(_lna_offsets(probe, probe_start0))
    return bool(lna_hits)


def _evaluate_probe_against_amplicons(
    probe: Dict,
    amplicons: List[Dict],
    target_organism: str = "",
) -> Dict:
    probe_seq = _plain_probe_sequence(probe)
    target_hits = []
    off_targets = []
    off_blocked = []
    off_unblocked = []
    unassessed = []

    for amp in amplicons or []:
        if not _amplicon_relevant(amp):
            continue
        amp_seq = _amplicon_sequence(amp)
        if not amp_seq:
            unassessed.append(amp)
            continue
        aln = _best_probe_alignment(probe_seq, amp_seq)
        if not aln:
            unassessed.append(amp)
            continue
        amp_eval = dict(amp)
        amp_eval["probe_alignment"] = aln
        is_target = _is_target_amplicon(amp, target_organism)
        if is_target and aln["mismatches"] <= 1:
            target_hits.append(amp_eval)
        elif is_target:
            unassessed.append(amp_eval)
        elif _alignment_discriminates(aln, probe, int(probe.get("start", 0) or 0)):
            off_blocked.append(amp_eval)
        else:
            off_unblocked.append(amp_eval)
        if not is_target:
            off_targets.append(amp_eval)

    assessed = len(target_hits) + len(off_blocked) + len(off_unblocked)
    if not probe_seq:
        status = "Probe sequence unavailable"
    elif target_hits and not off_unblocked and not unassessed:
        status = "Assay-specific"
    elif target_hits and off_blocked and not off_unblocked:
        status = "Probe-rescued candidate"
    elif target_hits and off_unblocked:
        status = "Probe-not-discriminating"
    elif not target_hits and assessed:
        status = "Probe target binding not confirmed"
    else:
        status = "Probe not assessed"

    return {
        "status": status,
        "target_hits": len(target_hits),
        "off_targets": len(off_targets),
        "off_targets_blocked": len(off_blocked),
        "off_targets_unblocked": len(off_unblocked),
        "unassessed_amplicons": len(unassessed),
        "target_amplicons": target_hits[:10],
        "unblocked_amplicons": off_unblocked[:10],
    }


def classify_primer_probe_specificity(
    primer_results: List[Dict],
    probes_by_gene: Dict[str, List[Dict]],
    target_organism: str = "",
) -> List[Dict]:
    combined = []
    for result in primer_results or []:
        gene = result.get("gene", "")
        probes = probes_by_gene.get(gene, [])
        primer_status = result.get("specificity_status", "")
        unresolved = primer_status in {"Genus-Specific", "Non-Specific", "No Target Hits"}
        best_probe = probes[0] if probes else None

        out = dict(result)
        if not unresolved:
            out["primer_probe_status"] = "Primer-specific"
            out["assay_specificity_status"] = "Primer-specific"
        elif best_probe:
            evaluation = _evaluate_probe_against_amplicons(
                best_probe,
                result.get("amplicons", []),
                target_organism=target_organism,
            )
            out["primer_probe_status"] = evaluation["status"]
            out["assay_specificity_status"] = evaluation["status"]
            out["probe_rank"] = best_probe.get("rank")
            out["probe_sequence"] = best_probe.get("formatted_sequence") or best_probe.get("sequence")
            out["probe_mm_covered"] = best_probe.get("mm_covered", 0)
            out["probe_species_covered"] = "; ".join(best_probe.get("species", []))
            out["probe_target_amplicon_hits"] = evaluation["target_hits"]
            out["probe_offtarget_amplicons"] = evaluation["off_targets"]
            out["probe_offtarget_blocked"] = evaluation["off_targets_blocked"]
            out["probe_offtarget_unblocked"] = evaluation["off_targets_unblocked"]
            out["probe_unassessed_amplicons"] = evaluation["unassessed_amplicons"]
        else:
            out["primer_probe_status"] = "Unresolved"
            out["assay_specificity_status"] = "Unresolved"
        combined.append(out)
    return combined
