"""
primer_designer.py

Cluster-pair primer design: forward primer on cluster A, reverse on cluster B.

Algorithm:
  1. Re-cluster conservative positions using method-specific primer length
  2. Enumerate valid (fwd_cluster, rev_cluster) pairs where:
     - distance between outer nucleotides fits product size range
  3. For each pair, use Primer3 SEQUENCE_PRIMER_PAIR_OK_REGION_LIST to
     constrain forward primer to fwd_cluster region, reverse to rev_cluster
  4. Score by: species_union_coverage + mismatch_coverage + 3'_bonus − thermals
  5. Pick top N non-repeating across all cluster pairs
"""

import os
import json
from typing import Dict, List, Optional, Tuple, Set

try:
    import primer3
except ImportError:
    primer3 = None


# ---------------------------------------------------------------------------
#  Method presets: primer length ranges and product sizes
# ---------------------------------------------------------------------------

METHOD_PARAMS = {
    "pcr":   {"min_size": 18, "opt_size": 22, "max_size": 25, "product": [100, 500],
              "min_tm": 55.0, "opt_tm": 60.0, "max_tm": 65.0},
    "qpcr":  {"min_size": 18, "opt_size": 20, "max_size": 25, "product": [70, 180],
              "min_tm": 58.0, "opt_tm": 60.0, "max_tm": 62.0},
    "rpa":   {"min_size": 30, "opt_size": 33, "max_size": 36, "product": [100, 300],
              "min_tm": 50.0, "opt_tm": 54.0, "max_tm": 58.0},
    "nasba": {"min_size": 20, "opt_size": 25, "max_size": 30, "product": [100, 250],
              "min_tm": 55.0, "opt_tm": 60.0, "max_tm": 65.0},
    "lamp":  {"min_size": 18, "opt_size": 22, "max_size": 25, "product": [150, 350],
              "min_tm": 58.0, "opt_tm": 62.0, "max_tm": 68.0},
}

_PRIMER3_TEMPLATE_BASES = set("ACGTN")


def _sanitize_template(seq: str) -> Tuple[str, int]:
    """Return a Primer3-safe template and count non-ACGTN IUPAC bases."""
    clean = []
    n_ambiguous = 0
    for base in (seq or "").upper():
        if base in _PRIMER3_TEMPLATE_BASES:
            clean.append(base)
        elif base.isalpha():
            clean.append("N")
            n_ambiguous += 1
    return "".join(clean), n_ambiguous


def _excluded_n_regions(seq: str) -> List[List[int]]:
    """Contiguous N blocks for Primer3 SEQUENCE_EXCLUDED_REGION."""
    regions = []
    start = None
    for i, base in enumerate(seq):
        if base == "N":
            if start is None:
                start = i
        elif start is not None:
            regions.append([start, i - start])
            start = None
    if start is not None:
        regions.append([start, len(seq) - start])
    return regions


def _cluster_for_primers(positions: List[int], primer_len: int) -> List[List[int]]:
    """
    Group positions into primer-length-sized clusters.
    Positions within primer_len of each other can be covered by one primer.
    """
    if not positions:
        return []
    positions = sorted(set(positions))
    clusters: List[List[int]] = [[positions[0]]]
    for p in positions[1:]:
        if p - clusters[-1][0] < primer_len:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return clusters


class PrimerDesigner:
    def __init__(self):
        self.tool = "Primery_Designer"

    def design_primers_from_clusters(
        self,
        seq: str,
        mode: str,
        clusters: List[Dict],
        n_per_pair: int = 50,
        n_top: int = 10,
        n_cluster_pairs: int = 20,
        custom_settings: Dict = None,
        require_3prime_mm: bool = True,
        three_prime_window: int = 3,
    ) -> List[Dict]:
        """
        Cluster-pair primer design.

        Args:
            seq: template sequence (longest FASTA of the gene)
            mode: PCR, qPCR, RPA, NASBA, LAMP
            clusters: from cluster_meta.json ranked list
            n_per_pair: candidates to request from Primer3 per cluster pair
            n_top: total top non-repeating primers to return
            custom_settings: optional Primer3 overrides
            require_3prime_mm: discard pairs where either primer does not place
                a species-discriminating mismatch near its 3' end.
            three_prime_window: allowed distance from the 3' terminal base
                (0 means terminal base only; 3 allows offsets 0..3).
        """
        if not primer3:
            raise ImportError("primer3-py not installed")

        mode_lc = mode.lower()
        params = METHOD_PARAMS.get(mode_lc, METHOD_PARAMS["pcr"])
        primer_max_len = params["max_size"]
        product_min, product_max = params["product"]
        template_seq, n_ambiguous = _sanitize_template(seq)
        excluded_regions = _excluded_n_regions(template_seq)
        if n_ambiguous:
            print(
                f"  Template contains {n_ambiguous} non-ACGTN IUPAC base(s); "
                "Primer3 template sanitized to N and N regions excluded."
            )

        # --- Re-cluster using method-specific primer_max_len ---
        # Extract all mismatch positions from the clusters
        all_positions = []
        # Also build a species lookup per position for scoring
        pos_species: Dict[int, Set[str]] = {}
        for cl in clusters:
            for p in cl.get("positions", []):
                all_positions.append(p)
            # Map each position to the cluster's species
            sp_set = set(cl.get("species", []))
            for p in cl.get("positions", []):
                pos_species.setdefault(p, set()).update(sp_set)

        if not all_positions:
            return self._design_unclustered(template_seq, mode, n_return=n_top,
                                            custom_settings=custom_settings)

        reclustered = _cluster_for_primers(all_positions, primer_max_len)

        # Score each re-clustered group
        scored_clusters = []
        for i, positions in enumerate(reclustered):
            species = set()
            for p in positions:
                species.update(pos_species.get(p, set()))
            scored_clusters.append({
                "id": i + 1,
                "positions": positions,
                "start": min(positions),
                "end": max(positions),
                "n_mm": len(positions),
                "species": species,
                "n_species": len(species),
            })
        scored_clusters.sort(key=lambda c: c["n_species"], reverse=True)
        for rank, c in enumerate(scored_clusters, 1):
            c["rank"] = rank

        # --- Enumerate valid (forward, reverse) cluster pairs ---
        # Forward cluster must be upstream of reverse cluster.
        # Distance from fwd_cluster.start to rev_cluster.end must fit product size.
        valid_pairs = []
        for fi, fwd in enumerate(scored_clusters):
            for ri, rev in enumerate(scored_clusters):
                if fwd["start"] >= rev["start"]:
                    continue  # fwd must be upstream
                product_span = rev["end"] - fwd["start"] + 1
                if product_span < product_min or product_span > product_max:
                    continue
                # Score: union of species discriminated by fwd + rev primers
                union_species = fwd["species"] | rev["species"]
                pair_score = len(union_species) + fwd["n_mm"] + rev["n_mm"]
                valid_pairs.append({
                    "fwd": fwd, "rev": rev,
                    "product_span": product_span,
                    "union_species": union_species,
                    "n_union_species": len(union_species),
                    "pair_score": pair_score,
                })

        # Sort by species union desc, then by total mismatches
        valid_pairs.sort(key=lambda p: (p["n_union_species"], p["pair_score"]), reverse=True)

        if not valid_pairs:
            print(f"  No valid cluster pairs within product range [{product_min}-{product_max}]")
            return self._design_unclustered(seq, mode, n_return=n_top,
                                            custom_settings=custom_settings)

        # --- Run Primer3 for each valid cluster pair ---
        settings = self._build_primer3_settings(params, custom_settings)
        all_candidates = []

        seq_len = len(template_seq)
        primer3_errors = {}
        for vp in valid_pairs[:n_cluster_pairs]:
            fwd_cl = vp["fwd"]
            rev_cl = vp["rev"]

            # STRICT cluster binding: OK_REGION tightly wraps the cluster
            # so primers must overlap with cluster mismatch positions.
            # Positions are 1-based in metadata, Primer3 needs 0-based.
            # Allow primer to start up to (primer_max_len - 1) before the
            # first mismatch so the primer body still covers the cluster.
            fwd_start_0 = max(fwd_cl["start"] - 1 - (primer_max_len - 1), 0)
            fwd_end_0 = fwd_cl["end"] - 1 + (primer_max_len - 1)
            fwd_end_0 = min(fwd_end_0, seq_len - 1)
            fwd_region_start = fwd_start_0
            fwd_region_len = fwd_end_0 - fwd_start_0 + 1

            rev_start_0 = max(rev_cl["start"] - 1 - (primer_max_len - 1), 0)
            rev_end_0 = rev_cl["end"] - 1 + (primer_max_len - 1)
            rev_end_0 = min(rev_end_0, seq_len - 1)
            rev_region_start = rev_start_0
            rev_region_len = rev_end_0 - rev_start_0 + 1

            pair_settings = dict(settings)
            pair_settings["PRIMER_NUM_RETURN"] = n_per_pair

            try:
                seq_args = {
                    "SEQUENCE_ID": f"fwd{fwd_cl['id']}_rev{rev_cl['id']}",
                    "SEQUENCE_TEMPLATE": template_seq,
                    "SEQUENCE_PRIMER_PAIR_OK_REGION_LIST": [
                        [fwd_region_start, fwd_region_len,
                         rev_region_start, rev_region_len],
                    ],
                }
                if excluded_regions:
                    seq_args["SEQUENCE_EXCLUDED_REGION"] = excluded_regions
                results = primer3.design_primers(
                    seq_args,
                    pair_settings,
                )
            except Exception as e:
                msg = str(e).splitlines()[0]
                primer3_errors[msg] = primer3_errors.get(msg, 0) + 1
                continue

            count = results.get("PRIMER_PAIR_NUM_RETURNED", 0)
            for i in range(count):
                try:
                    pair = self._extract_pair(
                        results, i, template_seq,
                        fwd_cluster=fwd_cl, rev_cluster=rev_cl,
                        union_species=vp["union_species"],
                        pos_species=pos_species,
                        require_3prime_mm=require_3prime_mm,
                        three_prime_window=three_prime_window,
                    )
                    if pair is None:
                        continue
                    all_candidates.append(pair)
                except (KeyError, IndexError):
                    continue

        # --- Global ranking and non-repeating selection ---
        if primer3_errors:
            summary = "; ".join(
                f"{count}x {msg}" for msg, count in sorted(primer3_errors.items())
            )
            print(f"  Primer3 rejected {sum(primer3_errors.values())} cluster pair(s): {summary}")

        all_candidates.sort(key=lambda x: (-x["score"], x["thermal_penalty"]))

        picked = []
        used_keys: Set[Tuple[int, int]] = set()
        for c in all_candidates:
            if len(picked) >= n_top:
                break
            if self._is_duplicate(c, picked, used_keys, min_dist=15):
                continue
            picked.append(c)
            used_keys.add((c["left_pos"], c["right_pos"]))

        for i, p in enumerate(picked):
            p["global_rank"] = i + 1

        return picked

    def _extract_pair(
        self, results: Dict, i: int, seq: str,
        fwd_cluster: Dict, rev_cluster: Dict,
        union_species: Set[str],
        pos_species: Dict[int, Set[str]],
        require_3prime_mm: bool = True,
        three_prime_window: int = 3,
    ) -> Dict:
        """Extract, score, and annotate a primer pair from Primer3 output."""
        left_seq  = results[f"PRIMER_LEFT_{i}_SEQUENCE"]
        right_seq = results[f"PRIMER_RIGHT_{i}_SEQUENCE"]
        left_pos  = results[f"PRIMER_LEFT_{i}"][0]       # 0-based start
        left_len  = results[f"PRIMER_LEFT_{i}"][1]
        right_pos = results[f"PRIMER_RIGHT_{i}"][0]       # 0-based, rightmost on plus strand
        right_len = results[f"PRIMER_RIGHT_{i}"][1]
        left_tm   = results[f"PRIMER_LEFT_{i}_TM"]
        right_tm  = results[f"PRIMER_RIGHT_{i}_TM"]

        left_hairpin  = results.get(f"PRIMER_LEFT_{i}_HAIRPIN_TH", 0.0)
        right_hairpin = results.get(f"PRIMER_RIGHT_{i}_HAIRPIN_TH", 0.0)
        left_dimer    = results.get(f"PRIMER_LEFT_{i}_SELF_ANY_TH", 0.0)
        right_dimer   = results.get(f"PRIMER_RIGHT_{i}_SELF_ANY_TH", 0.0)
        pair_compl    = results.get(f"PRIMER_PAIR_{i}_COMPL_ANY_TH", 0.0)
        product_size  = results.get(f"PRIMER_PAIR_{i}_PRODUCT_SIZE", 0)
        penalty       = results.get(f"PRIMER_PAIR_{i}_PENALTY", 0.0)

        # Forward primer physical range (0-based)
        l_range = set(range(left_pos, left_pos + left_len))
        # Reverse primer physical range (0-based)
        r_phys_start = right_pos - right_len + 1
        r_range = set(range(r_phys_start, right_pos + 1))

        # Convert mismatch positions to 0-based
        fwd_mm_0 = {p - 1 for p in fwd_cluster["positions"]}
        rev_mm_0 = {p - 1 for p in rev_cluster["positions"]}

        # Mismatch coverage: how many mismatches each primer overlaps
        fwd_hits = l_range & fwd_mm_0
        rev_hits = r_range & rev_mm_0
        fwd_mm_count = len(fwd_hits)
        rev_mm_count = len(rev_hits)
        total_mm = fwd_mm_count + rev_mm_count

        # Species from covered positions
        covered_species = set()
        for p0 in fwd_hits | rev_hits:
            covered_species.update(pos_species.get(p0 + 1, set()))

        # --- Scoring ---
        score = 0.0

        # Species discrimination (main metric)
        score += len(covered_species) * 10.0

        # Mismatch coverage
        score += total_mm * 5.0

        # 3' end offset: mismatches closest to the terminal base are most useful
        # for allele/species discrimination because polymerase extension is then
        # disfavored on non-target templates.
        fwd_3p_mm_offset = None
        left_3prime = left_pos + left_len - 1  # 0-based
        for offset in range(max(0, three_prime_window) + 1):
            if (left_3prime - offset) in fwd_mm_0:
                fwd_3p_mm_offset = offset
                score += 15.0 if offset == 0 else 5.0
                break

        rev_3p_mm_offset = None
        right_3prime = r_phys_start  # 3' end of reverse on plus strand
        for offset in range(max(0, three_prime_window) + 1):
            if (right_3prime + offset) in rev_mm_0:
                rev_3p_mm_offset = offset
                score += 15.0 if offset == 0 else 5.0
                break

        if require_3prime_mm and (fwd_3p_mm_offset is None or rev_3p_mm_offset is None):
            return None

        # Thermal penalty (lower is better)
        worst_hairpin = max(left_hairpin, right_hairpin)
        worst_dimer = max(left_dimer, right_dimer)
        thermal_penalty = worst_hairpin + worst_dimer + pair_compl
        score -= thermal_penalty * 0.5

        return {
            "fwd_cluster_id": fwd_cluster["id"],
            "rev_cluster_id": rev_cluster["id"],
            "fwd_cluster_rank": fwd_cluster["rank"],
            "rev_cluster_rank": rev_cluster["rank"],
            "left": left_seq,
            "right": right_seq,
            "left_pos": left_pos,
            "left_len": left_len,
            "right_pos": right_pos,
            "right_len": right_len,
            "left_tm": round(left_tm, 1),
            "right_tm": round(right_tm, 1),
            "left_hairpin_tm": round(left_hairpin, 1),
            "right_hairpin_tm": round(right_hairpin, 1),
            "left_dimer_tm": round(left_dimer, 1),
            "right_dimer_tm": round(right_dimer, 1),
            "pair_compl_tm": round(pair_compl, 1),
            "thermal_penalty": round(thermal_penalty, 1),
            "product_size": product_size,
            "primer3_penalty": round(penalty, 2),
            "fwd_mm_covered": fwd_mm_count,
            "rev_mm_covered": rev_mm_count,
            "fwd_mismatch_positions": sorted(p + 1 for p in fwd_hits),
            "rev_mismatch_positions": sorted(p + 1 for p in rev_hits),
            "fwd_3p_mm_offset": fwd_3p_mm_offset,
            "rev_3p_mm_offset": rev_3p_mm_offset,
            "total_mm_covered": total_mm,
            "n_species_covered": len(covered_species),
            "score": round(score, 1),
        }

    def _is_duplicate(
        self, candidate: Dict, picked: List[Dict],
        used_keys: Set[Tuple[int, int]], min_dist: int = 15,
    ) -> bool:
        for existing in picked:
            if (candidate["left"] == existing["left"] or
                    candidate["right"] == existing["right"]):
                return True
            if (abs(candidate["left_pos"] - existing["left_pos"]) < min_dist and
                    abs(candidate["right_pos"] - existing["right_pos"]) < min_dist):
                return True
        return (candidate["left_pos"], candidate["right_pos"]) in used_keys

    def _design_unclustered(
        self, seq: str, mode: str, n_return: int = 10,
        custom_settings: Dict = None,
    ) -> List[Dict]:
        """Fallback when no valid cluster pairs found."""
        mode_lc = mode.lower()
        params = METHOD_PARAMS.get(mode_lc, METHOD_PARAMS["pcr"])
        seq, n_ambiguous = _sanitize_template(seq)
        excluded_regions = _excluded_n_regions(seq)
        if n_ambiguous:
            print(
                f"  Template contains {n_ambiguous} non-ACGTN IUPAC base(s); "
                "Primer3 template sanitized to N and N regions excluded."
            )
        settings = self._build_primer3_settings(params, custom_settings)
        settings["PRIMER_NUM_RETURN"] = n_return * 5

        seq_args = {"SEQUENCE_ID": "target", "SEQUENCE_TEMPLATE": seq}
        if excluded_regions:
            seq_args["SEQUENCE_EXCLUDED_REGION"] = excluded_regions
        results = primer3.design_primers(
            seq_args, settings,
        )
        pairs = []
        count = results.get("PRIMER_PAIR_NUM_RETURNED", 0)
        for i in range(count):
            try:
                pairs.append({
                    "fwd_cluster_id": 0, "rev_cluster_id": 0,
                    "fwd_cluster_rank": 0, "rev_cluster_rank": 0,
                    "left": results[f"PRIMER_LEFT_{i}_SEQUENCE"],
                    "right": results[f"PRIMER_RIGHT_{i}_SEQUENCE"],
                    "left_pos": results[f"PRIMER_LEFT_{i}"][0],
                    "left_len": results[f"PRIMER_LEFT_{i}"][1],
                    "right_pos": results[f"PRIMER_RIGHT_{i}"][0],
                    "right_len": results[f"PRIMER_RIGHT_{i}"][1],
                    "left_tm": round(results[f"PRIMER_LEFT_{i}_TM"], 1),
                    "right_tm": round(results[f"PRIMER_RIGHT_{i}_TM"], 1),
                    "left_hairpin_tm": 0, "right_hairpin_tm": 0,
                    "left_dimer_tm": 0, "right_dimer_tm": 0,
                    "pair_compl_tm": 0, "thermal_penalty": 0,
                    "product_size": results.get(f"PRIMER_PAIR_{i}_PRODUCT_SIZE", 0),
                    "primer3_penalty": round(results.get(f"PRIMER_PAIR_{i}_PENALTY", 0), 2),
                    "fwd_mm_covered": 0, "rev_mm_covered": 0,
                    "fwd_3p_mm_offset": None, "rev_3p_mm_offset": None,
                    "total_mm_covered": 0, "n_species_covered": 0, "score": 0,
                })
            except KeyError:
                continue

        picked = []
        for p in pairs:
            if len(picked) >= n_return: break
            if any(p["left"] == e["left"] or p["right"] == e["right"] for e in picked):
                continue
            picked.append(p)
        for i, p in enumerate(picked):
            p["global_rank"] = i + 1
        return picked

    def _build_primer3_settings(self, params: Dict, custom: Dict = None) -> Dict:
        settings = {
            "PRIMER_MAX_NS_ACCEPTED": 0,
            "PRIMER_TM_FORMULA": 1,
            "PRIMER_SALT_CORRECTIONS": 1,
            "PRIMER_MIN_SIZE": params["min_size"],
            "PRIMER_OPT_SIZE": params["opt_size"],
            "PRIMER_MAX_SIZE": params["max_size"],
            "PRIMER_MIN_TM": params["min_tm"],
            "PRIMER_OPT_TM": params["opt_tm"],
            "PRIMER_MAX_TM": params["max_tm"],
            "PRIMER_PRODUCT_SIZE_RANGE": [params["product"]],
        }
        if custom:
            settings.update({
                k: v for k, v in custom.items()
                if not str(k).startswith("PRIMERY_")
            })
        return settings
