"""
blast_analyzer.py

GUI-facing wrapper around the original blast_mismatch_analyzer module.
Delegates heavy lifting (BLAST submission, mismatch tallying, XLSX/FASTA output)
to the battle-tested functions in blast_mismatch_analyzer.py.

Directory contract:
  Input:   {workspace}/{Organism}/Genes/{GeneName}/*.fasta
  Output:  {workspace}/{Organism}/BLAST/{GeneName}/<result files>
"""

import os
import sys
import time
import hashlib
import json
from typing import Dict, List, Optional, Tuple, Set

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

# Import local blast_mismatch_analyzer from core package
try:
    from . import blast_mismatch_analyzer as bma
except ImportError:
    # If running standalone or directly, try import without dot
    import blast_mismatch_analyzer as bma


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _derive_gene_from_path(fasta_path: str) -> str:
    parent = os.path.basename(os.path.dirname(fasta_path))
    grandparent = os.path.basename(os.path.dirname(os.path.dirname(fasta_path)))
    if grandparent.lower() == "genes" and parent:
        return parent
    return bma.derive_locus_from_filename(fasta_path)


def _cluster_positions(positions: List[int], primer_len: int = 25) -> List[List[int]]:
    """
    Group mismatch positions into primer-length-sized clusters.

    Positions within *primer_len* bp of each other belong to the same cluster,
    because a single primer can physically span all of them. This produces
    tight "landing zones" where a primer can be placed to overlap multiple
    mismatches for species-specific annealing.

    Args:
        positions: 1-based mismatch positions.
        primer_len: maximum primer length for the assay type (e.g. 25 for PCR,
                    35 for RPA). Positions within this distance are grouped.
    """
    if not positions:
        return []
    positions = sorted(set(positions))
    clusters: List[List[int]] = [[positions[0]]]
    for p in positions[1:]:
        # Can a single primer span from the first position of this cluster to p?
        if p - clusters[-1][0] < primer_len:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return clusters


def _score_cluster(
    positions: List[int],
    pos_data: dict,
    n_total_acc: int,
) -> dict:
    """
    Score a single cluster. Returns a dict with:
      - species: set of all off-target species discriminated
      - n_species: count of species
      - mean_acc_frac: mean fraction of accessions where these positions appear
      - score: n_species * mean_acc_frac (higher = better discrimination)
    """
    species: Set[str] = set()
    frac_sum = 0.0
    n = 0
    for pos in positions:
        if pos not in pos_data:
            continue
        for (qbase, alt), entry in pos_data[pos].items():
            species.update(entry["species"])
            frac_sum += len(entry["accessions"]) / max(n_total_acc, 1)
            n += 1
    mean_frac = frac_sum / max(n, 1)
    return {
        "species": species,
        "n_species": len(species),
        "mean_acc_frac": round(mean_frac, 3),
        "score": round(len(species) * mean_frac, 2),
    }


def _rank_clusters(
    clusters: List[List[int]],
    pos_data: dict,
    n_total_acc: int,
) -> List[dict]:
    """Score and rank clusters by species discrimination power."""
    scored = []
    for cid, positions in enumerate(clusters):
        info = _score_cluster(positions, pos_data, n_total_acc)
        scored.append({
            "cluster_id": cid + 1,
            "positions": positions,
            "span_start": min(positions),
            "span_end": max(positions),
            "n_positions": len(positions),
            "n_species": info["n_species"],
            "species": sorted(info["species"], key=str.lower),
            "mean_acc_frac": info["mean_acc_frac"],
            "score": info["score"],
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    for rank, c in enumerate(scored, 1):
        c["cluster_rank"] = rank
    return scored


# ---------------------------------------------------------------------------
#  Main class
# ---------------------------------------------------------------------------

class BlastAnalyzer:
    """Thin wrapper that exposes the original blast_mismatch_analyzer logic to the GUI."""

    def __init__(self, email: str, api_key: Optional[str] = None):
        self.email = email
        self.api_key = api_key

    def run_analysis(
        self,
        fasta_paths: List[str],
        target_sciname: str,
        target_taxid: int,
        workspace: str,
        max_hits: int = 200,
        megablast: bool = True,
        db: str = "core_nt",
        limit: str = None,
        excluded_species: List[str] = None,
        force: bool = False,
    ) -> List[Dict]:
        results = []
        gene_groups: Dict[str, List[Dict]] = {}

        for path in fasta_paths:
            try:
                gene = _derive_gene_from_path(path)
                print(f"Analyzing {gene}/{os.path.basename(path)}...")
                res = self._analyze_single(
                    path, target_sciname, target_taxid, workspace, gene,
                    max_hits=max_hits, megablast=megablast, force=force,
                    limit=limit, excluded_species=excluded_species,
                )
                results.append(res)
                gene_groups.setdefault(gene, []).append(res)
            except Exception as e:
                print(f"Failed analysis for {path}: {e}")
                import traceback; traceback.print_exc()

        for gene, res_list in gene_groups.items():
            try:
                self._generate_general_summary(
                    gene, res_list, workspace, target_sciname,
                    analysis_scope={
                        "limit": limit or "Species",
                        "excluded_species": excluded_species or [],
                    },
                )
            except Exception as e:
                print(f"Failed general summary for {gene}: {e}")
                import traceback; traceback.print_exc()

        return results

    # ------------------------------------------------------------------
    def _analyze_single(
        self, path, target_sciname, target_taxid, workspace, gene,
        max_hits=200, megablast=True, force=False,
        limit=None, excluded_species=None,
    ) -> Dict:
        query_header, query_seq = bma.read_first_fasta(path)
        query_acc = bma.derive_accession_from_filename(path)
        expect = 10.0
        key = bma.analysis_key(
            query_seq, database="core_nt", program="blastn",
            hitlist_size=max_hits, expect=expect, megablast=megablast,
        )
        scope_key = json.dumps(
            {"limit": limit or "Species", "excluded_species": excluded_species or []},
            sort_keys=True,
        )
        key = f"{key}__scope_{hashlib.sha1(scope_key.encode('utf-8')).hexdigest()[:8]}"

        safe_org = target_sciname.replace(" ", "_")
        analysis_dir = os.path.join(workspace, safe_org, "BLAST", gene)
        os.makedirs(analysis_dir, exist_ok=True)

        tag = f"{key}__{query_acc or 'query'}"
        raw_zip_path      = os.path.join(analysis_dir, f"{tag}__blast_JSON2.zip")
        raw_done_path      = os.path.join(analysis_dir, f"{tag}__.done.json")
        aligned_fasta_path = os.path.join(analysis_dir, f"{tag}__aligned_query_anchored.fasta")
        xlsx_path          = os.path.join(analysis_dir, f"{tag}__mismatch_summary.xlsx")

        if not force and os.path.exists(raw_done_path) and os.path.exists(xlsx_path):
            print(f"  SKIP (cached): {os.path.basename(path)}")
            return {
                "status": "skipped", "path": xlsx_path,
                "aligned_fasta": aligned_fasta_path, "raw_zip": raw_zip_path,
                "file": path, "gene": gene, "accession": query_acc,
                "seq_len": len(query_seq), "limit": limit or "Species",
            }

        fasta_for_blast = f">{query_header}\n{query_seq}\n"
        ua = f"fusarium-blast-mismatch-analyzer/1.0 ({self.email})"
        print(f"  Submitting BLAST: gene={gene}, acc={query_acc or query_header}")
        rid = bma.blast_put(
            fasta_for_blast, database="core_nt", program="blastn",
            megablast=megablast, hitlist_size=max_hits, expect=expect, user_agent=ua,
        )
        print(f"  RID={rid}")

        zip_bytes = bma.blast_get_json2_zip(rid, user_agent=ua)
        bma.save_bytes(raw_zip_path, zip_bytes)
        obj = bma.load_blastoutput2_from_zip(zip_bytes)
        query_len, hits = bma.extract_hits(obj)
        if query_len <= 0 or query_len != len(query_seq):
            query_len = len(query_seq)

        min_cov = 0.5
        hit_aligned = []
        for hi in hits[:max_hits]:
            anchored, covered, _ = bma.build_query_anchored_seq(query_len, hi.hsp)
            cov = covered / max(1, query_len)
            if cov < min_cov:
                continue
            header = f"{hi.accession}|{hi.sciname or 'unknown'}|cov={cov:.3f}"
            hit_aligned.append((header, "".join(anchored)))

        bma.write_aligned_fasta(
            aligned_fasta_path,
            f"{query_acc or 'QUERY'}|{target_sciname}|{gene}",
            query_seq, hit_aligned,
        )

        mismatch_counts, mismatch_species, hits_rows = bma.tally_mismatches(
            query_seq, hits,
            target_sciname=target_sciname,
            target_taxid=target_taxid if target_taxid else None,
            limit_mode=limit or "Species",
            excluded_scinames=set(excluded_species or []),
            max_hits_used=max_hits, min_coverage_frac=min_cov,
        )

        bma.write_xlsx(
            xlsx_path,
            target_sciname=target_sciname, locus=gene,
            query_accession=query_acc, query_header=query_header,
            query_seq=query_seq, mismatch_counts=mismatch_counts,
            mismatch_species=mismatch_species, hits_rows=hits_rows, top_n=500,
        )

        done = {
            "analysis_key": key,
            "query_fasta_path": os.path.abspath(path),
            "query_header": query_header, "query_accession": query_acc,
            "gene": gene, "target_sciname": target_sciname,
            "target_taxid": target_taxid,
            "analysis_scope": {
                "limit": limit or "Species",
                "excluded_species": excluded_species or [],
            },
            "blast": {"database": "core_nt", "program": "blastn",
                      "hitlist_size": max_hits, "expect": expect,
                      "megablast": megablast, "rid": rid},
            "outputs": {"raw_zip": os.path.abspath(raw_zip_path),
                        "aligned_fasta": os.path.abspath(aligned_fasta_path),
                        "xlsx": os.path.abspath(xlsx_path)},
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(raw_done_path, "w", encoding="utf-8") as f:
            json.dump(done, f, ensure_ascii=False, indent=2)

        print(f"  Saved: {xlsx_path}")
        return {
            "status": "done", "path": xlsx_path,
            "aligned_fasta": aligned_fasta_path, "raw_zip": raw_zip_path,
            "file": path, "gene": gene, "accession": query_acc,
            "seq_len": len(query_seq), "limit": limit or "Species",
        }

    # ------------------------------------------------------------------
    #  General summary with primer-length clustering
    # ------------------------------------------------------------------
    def _generate_general_summary(
        self, gene: str, res_list: List[Dict], workspace: str, organism: str,
        analysis_scope: Dict = None,
    ):
        """
        Aggregate per-accession mismatch results, find conservative mutations,
        cluster them into primer-length landing zones, rank clusters by
        species discrimination, and write XLSX + JSON metadata.
        """
        from openpyxl import load_workbook
        from collections import defaultdict
        import glob, json

        safe_org = organism.replace(" ", "_")
        out_dir = os.path.join(workspace, safe_org, "BLAST", gene)
        os.makedirs(out_dir, exist_ok=True)
        summary_path = os.path.join(out_dir, f"{gene}_general_summary.xlsx")

        # ── Collect mismatch data from all per-accession XLSX files ──
        pos_data = defaultdict(lambda: defaultdict(lambda: {
            "accessions": set(), "n_hits_max": 0, "n_species_max": 0, "species": set()
        }))
        accession_stats = []
        longest_fasta = {"path": "", "accession": "", "length": 0}

        xlsx_files = [r["path"] for r in res_list
                      if r.get("path") and os.path.exists(r.get("path", ""))]
        if not xlsx_files:
            xlsx_files = glob.glob(os.path.join(out_dir, "*__mismatch_summary.xlsx"))
        path_to_acc = {
            os.path.abspath(r.get("path", "")): r.get("accession", "")
            for r in res_list if r.get("path")
        }

        for res in res_list:
            sl = res.get("seq_len", 0)
            if sl > longest_fasta["length"]:
                longest_fasta = {
                    "path": res.get("file", ""),
                    "accession": res.get("accession", ""),
                    "length": sl,
                }

        for xlsx_path in xlsx_files:
            try:
                wb = load_workbook(xlsx_path, read_only=True, data_only=True)
                if "summary" not in wb.sheetnames:
                    wb.close(); continue
                ws = wb["summary"]
                rows = list(ws.iter_rows(values_only=True))
                wb.close()
                if len(rows) < 2:
                    continue

                headers = [str(h or "").lower().strip() for h in rows[0]]
                col = {h: i for i, h in enumerate(headers)}
                fname = os.path.basename(xlsx_path)
                acc = path_to_acc.get(os.path.abspath(xlsx_path), "")
                if not acc:
                    stem = fname.replace("__mismatch_summary.xlsx", "")
                    parts = stem.split("__")
                    acc = parts[-1] if len(parts) >= 2 else stem

                total_positions = 0
                for row in rows[1:]:
                    def g(key, _row=row, _col=col):
                        idx = _col.get(key)
                        return _row[idx] if idx is not None and idx < len(_row) else None

                    pos = g("pos_1based")
                    qbase = g("query_base") or ""
                    alt = g("alt") or ""
                    n_hits = g("n_hits_non_target") or 0
                    n_species = g("n_species_non_target") or 0
                    sp_examples = g("species_examples") or ""

                    if pos is None: continue
                    try:
                        pos = int(pos); n_hits = int(n_hits); n_species = int(n_species)
                    except (ValueError, TypeError): continue

                    total_positions += 1
                    entry = pos_data[pos][(str(qbase), str(alt))]
                    entry["accessions"].add(acc)
                    entry["n_hits_max"] = max(entry["n_hits_max"], n_hits)
                    entry["n_species_max"] = max(entry["n_species_max"], n_species)
                    if sp_examples:
                        for sp in str(sp_examples).split(";"):
                            sp = sp.strip()
                            if sp and sp != "…":
                                entry["species"].add(sp)

                accession_stats.append({
                    "accession": acc, "xlsx_path": xlsx_path,
                    "mismatch_positions": total_positions, "status": "done",
                })
            except Exception as e:
                print(f"  Warning: could not read {xlsx_path}: {e}")

        n_total_acc = max(len(accession_stats), 1)

        # ── Conservative positions (in 2+ accessions) ──
        conservative_positions = set()
        conservative_rows = []
        for pos, alts in pos_data.items():
            for (qbase, alt), entry in alts.items():
                n_acc = len(entry["accessions"])
                conservative_rows.append((
                    n_acc, entry["n_species_max"], entry["n_hits_max"],
                    pos, qbase, alt, entry["accessions"], entry["species"],
                ))
                if n_acc >= 2:
                    conservative_positions.add(pos)
        conservative_rows.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)

        # ── Cluster into primer-length landing zones ──
        # Use 25bp as default (good for PCR/qPCR). Primer designer will
        # re-cluster if method needs different length (e.g. 35 for RPA).
        clusters_raw = _cluster_positions(sorted(conservative_positions), primer_len=25)
        ranked_clusters = _rank_clusters(clusters_raw, pos_data, n_total_acc)

        pos_to_cluster = {}
        for cl in ranked_clusters:
            for p in cl["positions"]:
                pos_to_cluster[p] = cl["cluster_id"]

        # ── Write XLSX ──
        wb_out = Workbook()
        hfont = Font(bold=True)
        wrap = Alignment(wrap_text=True, vertical="top")

        # Sheet 1: Clusters (primer landing zones)
        ws_cl = wb_out.active
        ws_cl.title = "clusters"
        ws_cl.append([
            "cluster_rank", "cluster_id", "n_positions", "span_start", "span_end",
            "span_length_bp", "n_species", "mean_acc_frac", "score",
            "positions", "species_examples",
        ])
        for c in ws_cl[1]:
            c.font = hfont; c.alignment = wrap
        for cl in ranked_clusters:
            sp_str = "; ".join(cl["species"][:15]) + ("; …" if len(cl["species"]) > 15 else "")
            pos_str = ", ".join(str(p) for p in cl["positions"][:30])
            ws_cl.append([
                cl["cluster_rank"], cl["cluster_id"], cl["n_positions"],
                cl["span_start"], cl["span_end"],
                cl["span_end"] - cl["span_start"] + 1,
                cl["n_species"], cl["mean_acc_frac"], cl["score"],
                pos_str, sp_str,
            ])

        # Sheet 2: Conservative mismatches
        ws_cm = wb_out.create_sheet("conservative_mismatches")
        ws_cm.append([
            "pos_1based", "query_base", "alt", "cluster_id", "cluster_rank",
            "n_accessions", "accession_fraction", "max_n_hits", "max_n_species",
            "accessions", "species_examples",
        ])
        for c in ws_cm[1]:
            c.font = hfont; c.alignment = wrap
        for n_acc, n_sp_max, n_hits_max, pos, qbase, alt, accs, species in conservative_rows:
            if n_acc < 2: continue
            cid = pos_to_cluster.get(pos, "")
            crank = ""
            for cl in ranked_clusters:
                if cl["cluster_id"] == cid:
                    crank = cl["cluster_rank"]; break
            frac = round(n_acc / n_total_acc, 3)
            sp_list = sorted(species, key=str.lower)
            sp_str = "; ".join(sp_list[:15]) + ("; …" if len(sp_list) > 15 else "")
            ws_cm.append([pos, qbase, alt, cid, crank, n_acc, frac, n_hits_max, n_sp_max,
                          "; ".join(sorted(accs)), sp_str])

        # Sheet 3: Per-accession
        ws_pa = wb_out.create_sheet("per_accession")
        ws_pa.append(["accession", "mismatch_positions", "status", "xlsx_path"])
        for c in ws_pa[1]:
            c.font = hfont; c.alignment = wrap
        for stat in accession_stats:
            ws_pa.append([stat["accession"], stat["mismatch_positions"], stat["status"], stat["xlsx_path"]])

        # Sheet 4: All positions
        ws_all = wb_out.create_sheet("all_positions")
        ws_all.append(["pos_1based", "query_base", "alt", "n_accessions", "cluster_id",
                        "max_n_hits", "max_n_species", "species_examples"])
        for c in ws_all[1]:
            c.font = hfont; c.alignment = wrap
        for n_acc, n_sp_max, n_hits_max, pos, qbase, alt, accs, species in conservative_rows:
            cid = pos_to_cluster.get(pos, "")
            sp_list = sorted(species, key=str.lower)
            sp_str = "; ".join(sp_list[:15]) + ("; …" if len(sp_list) > 15 else "")
            ws_all.append([pos, qbase, alt, n_acc, cid, n_hits_max, n_sp_max, sp_str])

        for ws in [ws_cl, ws_cm, ws_pa, ws_all]:
            for col_cells in ws.columns:
                col_letter = get_column_letter(col_cells[0].column)
                max_len = max((len(str(cell.value or "")) for cell in col_cells), default=10)
                ws.column_dimensions[col_letter].width = min(max_len + 2, 70)

        wb_out.save(summary_path)
        print(f"General summary saved: {summary_path}")
        print(f"  {len(ranked_clusters)} clusters from {len(conservative_positions)} conservative positions")

        # ── Save cluster metadata JSON (for primer designer) ──
        meta = {
            "gene": gene,
            "organism": organism,
            "analysis_scope": analysis_scope or {},
            "n_accessions": n_total_acc,
            "longest_fasta": longest_fasta,
            "clusters": [{
                "cluster_rank": cl["cluster_rank"],
                "cluster_id": cl["cluster_id"],
                "positions": cl["positions"],
                "span_start": cl["span_start"],
                "span_end": cl["span_end"],
                "score": cl["score"],
                "n_positions": cl["n_positions"],
                "n_species": cl["n_species"],
                "species": cl["species"],
            } for cl in ranked_clusters],
        }
        meta_path = os.path.join(out_dir, f"{gene}_cluster_meta.json")
        import json as json_mod
        with open(meta_path, "w", encoding="utf-8") as f:
            json_mod.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"  Cluster metadata: {meta_path}")
