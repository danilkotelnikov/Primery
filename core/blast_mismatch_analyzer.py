#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
blast_mismatch_analyzer.py

Берёт входную FASTA-последовательность (ген/локус), отправляет BLASTN на NCBI по базе core_nt,
скачивает результат (FORMAT_TYPE=JSON2), формирует query-anchored "мультивыравнивание" (aligned FASTA),
и на основе выравнивания подсчитывает позиции/диапазоны, где НЕцелевые виды чаще всего отличаются
от целевой последовательности.

Что делает:
  1) Submit BLAST (blastn, core_nt) через BLAST Common URL API (Blast.cgi, CMD=Put/Get).
  2) Забирает JSON2 (в ZIP-контейнере) и сохраняет его как "сырые" результаты.
  3) Извлекает топ-N hit'ов, строит query-anchored MSA (длина = длина query; вне покрытия = 'N';
     делеции в hit = '-').
  4) Считает несовпадения по позициям (1-based):
       - SNP/замена: query_base != hit_base (A/C/G/T/…)
       - DEL: hit_base == '-' при query_base != '-'
     Вставки в hit относительно query (qseq имеет '-') игнорируются, так как они не имеют однозначной
     координаты в query-anchored системе.
  5) Суммирует:
       - сколько НЕцелевых последовательностей (hits) имеют несовпадение в позиции
       - сколько НЕцелевых ВИДОВ (unique sciname) имеют несовпадение в позиции
  6) Пишет отчёт XLSX.

Важно:
  - Скрипт рассчитан на диагностический контекст (праймер-дизайн). Для него чаще достаточно
    query-anchored несовпадений (SNP/делеции) по координатам целевой последовательности.
  - Для "истинного" MSA с учётом вставок лучше дополнительно прогнать MAFFT/MUSCLE локально,
    но это вне задач данного скрипта.

Зависимости:
  - requests
  - openpyxl

Примеры:
  # Анализ одного файла
  python blast_mismatch_analyzer.py --email you@lab.org --target-sciname "Fusarium culmorum" \
      --query-fasta Fusarium_culmorum__ITS__OK123456.fasta --outdir analysis_out

  # Анализ всех локусов из manifest.tsv (создан download_fusarium_loci.py)
  python blast_mismatch_analyzer.py --email you@lab.org --manifest fusarium_fasta/manifest.tsv \
      --outdir fusarium_fasta --analyze-from-manifest --max-hits 200

Параметры "самопроверки":
  - Для каждого анализа создаётся файл .done.json (с хэшем query и параметрами BLAST).
    Если он есть и выходные файлы присутствуют, анализ пропускается (можно --force).

Ссылки на документацию:
  - BLAST Common URL API: https://blast.ncbi.nlm.nih.gov/doc/blast-help/urlapi.html
  - core_nt: https://blast.ncbi.nlm.nih.gov/doc/blast-help/blastdatabases.html

"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Iterable, Set

import requests
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter


BLAST_ENDPOINT = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"


ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "blue": "\033[34m",
}


def log(msg: str, level: str = "INFO", *, interactive: bool = False) -> None:
    color = {"INFO": "blue", "OK": "green", "WARN": "yellow", "ERROR": "red"}.get(level, "blue")
    prefix = f"{ANSI['bold']}{ANSI[color]}[{level}]{ANSI['reset']}"
    if interactive:
        # overwrite current line
        sys.stderr.write("\r" + prefix + " " + msg + " " * 20)
        sys.stderr.flush()
    else:
        sys.stderr.write(prefix + " " + msg + "\n")
        sys.stderr.flush()


def safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def read_first_fasta(path: str) -> Tuple[str, str]:
    """Возвращает (header, seq) для первой записи FASTA в файле."""
    header = None
    seq_parts: List[str] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is None:
                    header = line[1:].strip()
                else:
                    break
            else:
                if header is not None:
                    seq_parts.append(re.sub(r"\s+", "", line))
    if header is None:
        raise ValueError(f"FASTA header not found in {path}")
    seq = "".join(seq_parts).upper()
    seq = re.sub(r"[^ACGTNRYKMSWBDHV-]", "N", seq)
    seq = seq.replace("-", "")
    if len(seq) == 0:
        raise ValueError(f"Empty sequence in {path}")
    return header, seq


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def blast_put(
    query_fasta: str,
    *,
    program: str = "blastn",
    database: str = "core_nt",
    megablast: bool = True,
    hitlist_size: int = 200,
    expect: float = 10.0,
    user_agent: str = "fusarium-blast-mismatch-analyzer/1.0",
    timeout: int = 60,
) -> str:
    """
    Отправляет BLAST запрос. Возвращает RID.
    """
    params = {
        "CMD": "Put",
        "PROGRAM": program,
        "DATABASE": database,
        "QUERY": query_fasta,
        "HITLIST_SIZE": str(int(hitlist_size)),
        "EXPECT": str(expect),
    }
    if megablast and program == "blastn":
        params["MEGABLAST"] = "on"

    headers = {"User-Agent": user_agent}
    r = requests.post(BLAST_ENDPOINT, data=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    text = r.text

    # RID обычно вида "RID = XXXXXXXX"
    m = re.search(r"\bRID\s*=\s*([A-Z0-9]+)\b", text)
    if not m:
        # иногда RID возвращается как "Request ID"
        m = re.search(r"\bRequest\s+ID\s*[:=]\s*([A-Z0-9]+)\b", text, flags=re.IGNORECASE)
    if not m:
        raise RuntimeError("RID not found in BLAST response (Put). Response snippet:\n" + text[:4000])
    rid = m.group(1)
    return rid


def blast_get_json2_zip(
    rid: str,
    *,
    poll_interval: float = 5.0,
    max_wait_s: int = 60 * 30,
    user_agent: str = "fusarium-blast-mismatch-analyzer/1.0",
    timeout: int = 60,
) -> bytes:
    """
    Пуллинг до готовности и скачивание FORMAT_TYPE=JSON2 (ZIP).
    Возвращает bytes ZIP.
    """
    headers = {"User-Agent": user_agent}
    t0 = time.time()
    while True:
        if time.time() - t0 > max_wait_s:
            raise TimeoutError(f"BLAST RID={rid} not ready after {max_wait_s}s")

        params = {"CMD": "Get", "RID": rid, "FORMAT_TYPE": "JSON2"}
        r = requests.get(BLAST_ENDPOINT, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        data = r.content

        # JSON2 возвращается в zip (magic PK..)
        if data[:4] == b"PK\x03\x04":
            log(f"RID={rid} ready (JSON2 ZIP)", "OK", interactive=False)
            return data

        # Иначе обычно возвращается HTML/Text со статусом
        text = ""
        try:
            text = r.text
        except Exception:
            text = data[:2000].decode("utf-8", errors="ignore")

        if re.search(r"Status\s*=\s*FAILED", text, flags=re.IGNORECASE):
            raise RuntimeError(f"BLAST RID={rid} failed. Response:\n{text[:2000]}")
        if re.search(r"Status\s*=\s*UNKNOWN", text, flags=re.IGNORECASE):
            # подождём чуть дольше, потом повтор
            log(f"RID={rid} status UNKNOWN; polling…", "WARN", interactive=True)
            time.sleep(poll_interval)
            continue

        # Обычно "WAITING"
        log(f"RID={rid} waiting…", "INFO", interactive=True)
        time.sleep(poll_interval)


def load_blastoutput2_from_zip(zip_bytes: bytes) -> Dict:
    """
    JSON2 приходит как ZIP с двумя json файлами (index + data).
    Возвращает словарь с ключом BlastOutput2.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        # читаем все json, ищем где есть BlastOutput2
        for name in zf.namelist():
            if not name.lower().endswith(".json"):
                continue
            raw = zf.read(name)
            try:
                obj = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if "BlastOutput2" in obj:
                return obj
        # иногда index указывает на файл в списке
        # попробуем раскрыть BlastJSON индекс
        for name in zf.namelist():
            if not name.lower().endswith(".json"):
                continue
            raw = zf.read(name)
            try:
                obj = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if "BlastJSON" in obj and isinstance(obj["BlastJSON"], list):
                for item in obj["BlastJSON"]:
                    file_name = item.get("File")
                    if file_name and file_name in zf.namelist():
                        raw2 = zf.read(file_name)
                        obj2 = json.loads(raw2.decode("utf-8"))
                        if "BlastOutput2" in obj2:
                            return obj2
    raise ValueError("BlastOutput2 not found in JSON2 ZIP")


def _get(d: Dict, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def pick_best_hsp(hsps: List[Dict]) -> Optional[Dict]:
    if not hsps:
        return None
    # max by bit_score, then align_len
    def key(h):
        bs = h.get("bit_score") or h.get("bit-score") or 0
        al = h.get("align_len") or h.get("align-len") or 0
        return (float(bs), int(al))
    return sorted(hsps, key=key, reverse=True)[0]


@dataclass
class HitInfo:
    accession: str
    title: str
    sciname: str
    taxid: Optional[int]
    hsp: Dict


def extract_hits(blast_json: Dict) -> Tuple[int, List[HitInfo]]:
    """
    Возвращает (query_len, hits[])
    """
    search = _get(blast_json, "BlastOutput2", "report", "results", "search", default={})
    query_len = int(search.get("query_len") or search.get("query-len") or 0)
    hits_raw = search.get("hits") or []
    hits: List[HitInfo] = []
    for h in hits_raw:
        desc0 = (h.get("description") or [{}])[0]
        accession = (desc0.get("accession") or "").strip()
        title = (desc0.get("title") or "").strip()
        sciname = (desc0.get("sciname") or "").strip()
        taxid = desc0.get("taxid")
        try:
            taxid = int(taxid) if taxid is not None else None
        except Exception:
            taxid = None
        hsps = h.get("hsps") or []
        best = pick_best_hsp(hsps)
        if not best:
            continue
        hits.append(HitInfo(accession=accession, title=title, sciname=sciname, taxid=taxid, hsp=best))
    return query_len, hits


def build_query_anchored_seq(query_len: int, hsp: Dict) -> Tuple[List[str], int, int]:
    """
    Строит query-anchored последовательность длины query_len.
    Вне покрытия: 'N'. Делеции в hit: '-'.
    Возвращает (char_list, covered_bases, aligned_columns_used).
    """
    qseq = hsp.get("qseq") or ""
    hseq = hsp.get("hseq") or ""
    if not qseq or not hseq or len(qseq) != len(hseq):
        return (["N"] * query_len, 0, 0)

    q_from = hsp.get("query_from") or hsp.get("query-from") or 1
    q_to = hsp.get("query_to") or hsp.get("query-to") or q_from
    try:
        q_from = int(q_from)
        q_to = int(q_to)
    except Exception:
        q_from, q_to = 1, 1

    # 1-based -> 0-based start index in query coordinate system.
    start = min(q_from, q_to) - 1
    anchored = ["N"] * query_len
    qpos = start
    covered = 0
    used_cols = 0
    for qc, hc in zip(qseq.upper(), hseq.upper()):
        if qc == "-":
            # insertion relative to query: skip (no query coordinate)
            continue
        if 0 <= qpos < query_len:
            anchored[qpos] = hc if hc in "ACGTNRYKMSWBDHV-" else "N"
            covered += 1
            used_cols += 1
        qpos += 1
    return anchored, covered, used_cols


def _normalize_limit_mode(value: Optional[str]) -> str:
    mode = re.sub(r"\s+", " ", (value or "species").strip().lower())
    mode = mode.replace(" / ", "/").replace("/ ", "/").replace(" /", "/")
    if mode in {"isolate/strain", "isolates/strains", "isolate", "strain"}:
        return "isolate"
    if mode in {"clade/species complex", "species complex", "clade", "complex"}:
        return "clade"
    if mode == "genus":
        return "genus"
    if mode == "none":
        return "none"
    return "species"


def tally_mismatches(
    query_seq: str,
    hits: List[HitInfo],
    *,
    target_sciname: Optional[str] = None,
    target_taxid: Optional[int] = None,
    limit_mode: Optional[str] = "species",
    excluded_scinames: Optional[Set[str]] = None,
    max_hits_used: int = 200,
    min_coverage_frac: float = 0.5,
) -> Tuple[Dict[int, Dict[str, int]], Dict[int, Dict[str, Set[str]]], List[Dict]]:
    """
    Возвращает:
      counts[pos][alt] = n_hits
      species[pos][alt] = set(sciname)
      hits_rows: список строк для отчёта по hit'ам
    """
    L = len(query_seq)
    target_sciname_norm = (target_sciname or "").strip().lower()
    target_genus = target_sciname_norm.split()[0] if target_sciname_norm else ""
    mode = _normalize_limit_mode(limit_mode)
    excluded_norm = {s.strip().lower() for s in (excluded_scinames or set()) if s}
    counts: Dict[int, Dict[str, int]] = {}
    species: Dict[int, Dict[str, Set[str]]] = {}
    hits_rows: List[Dict] = []

    used = 0
    for hi in hits:
        if used >= max_hits_used:
            break
        sciname_norm = (hi.sciname or "").strip().lower()
        same_species = bool(target_sciname_norm and sciname_norm == target_sciname_norm)
        same_taxid = target_taxid is not None and hi.taxid is not None and hi.taxid == target_taxid
        same_genus = bool(target_genus and sciname_norm.startswith(target_genus + " "))

        if mode == "species":
            if same_taxid or same_species or sciname_norm in excluded_norm:
                continue
        elif mode == "clade":
            if same_taxid or same_species or sciname_norm in excluded_norm:
                continue
        elif mode == "genus":
            if same_taxid or same_species or not same_genus:
                continue
        elif mode == "isolate":
            # Keep same-species hits so isolate/strain markers can be discovered
            # relative to the selected query/reference accession.
            pass
        elif mode == "none":
            pass

        anchored, covered, _ = build_query_anchored_seq(L, hi.hsp)
        cov_frac = covered / max(1, L)
        if cov_frac < min_coverage_frac:
            continue

        # метрики для строки
        mism_ct = 0
        del_ct = 0
        snp_ct = 0

        for i, (qbase, hbase) in enumerate(zip(query_seq, anchored), start=1):
            if hbase == "N" or qbase == "N":
                continue
            if hbase == qbase:
                continue
            alt = "DEL" if hbase == "-" else hbase
            if alt == "DEL":
                del_ct += 1
            else:
                snp_ct += 1
            mism_ct += 1

            counts.setdefault(i, {}).setdefault(alt, 0)
            counts[i][alt] += 1
            species.setdefault(i, {}).setdefault(alt, set())
            species[i][alt].add(hi.sciname or "unknown")

        hits_rows.append(
            {
                "accession": hi.accession,
                "sciname": hi.sciname,
                "taxid": hi.taxid,
                "title": hi.title,
                "coverage_frac": cov_frac,
                "mismatches": mism_ct,
                "snps": snp_ct,
                "dels": del_ct,
                "bit_score": hi.hsp.get("bit_score") or hi.hsp.get("bit-score"),
                "evalue": hi.hsp.get("evalue"),
                "align_len": hi.hsp.get("align_len") or hi.hsp.get("align-len"),
                "identity": hi.hsp.get("identity"),
            }
        )
        used += 1

    return counts, species, hits_rows


def write_aligned_fasta(
    out_path: str,
    query_header: str,
    query_seq: str,
    hit_seqs: List[Tuple[str, str]],
    line_width: int = 80,
) -> None:
    """
    hit_seqs: list of (header, aligned_seq) where aligned_seq same length as query_seq,
              includes 'N' for uncovered and '-' for deletions.
    """
    def wrap(seq: str) -> str:
        return "\n".join(seq[i:i+line_width] for i in range(0, len(seq), line_width))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f">{query_header}\n{wrap(query_seq)}\n")
        for h, s in hit_seqs:
            f.write(f">{h}\n{wrap(s)}\n")


def autosize_columns(ws, max_width: int = 60) -> None:
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            v = cell.value
            if v is None:
                continue
            v = str(v)
            if len(v) > max_len:
                max_len = len(v)
        ws.column_dimensions[col_letter].width = min(max(10, max_len + 2), max_width)


def write_xlsx(
    out_path: str,
    *,
    target_sciname: str,
    locus: str,
    query_accession: str,
    query_header: str,
    query_seq: str,
    mismatch_counts: Dict[int, Dict[str, int]],
    mismatch_species: Dict[int, Dict[str, Set[str]]],
    hits_rows: List[Dict],
    top_n: int = 200,
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "summary"

    header_font = Font(bold=True)
    ws.append(
        [
            "target_sciname",
            "locus",
            "query_accession",
            "query_len",
            "pos_1based",
            "query_base",
            "alt",
            "n_hits_non_target",
            "n_species_non_target",
            "species_examples",
        ]
    )
    for c in ws[1]:
        c.font = header_font
        c.alignment = Alignment(wrap_text=True, vertical="top")

    # Сортировка: сначала по числу видов, потом по числу hits
    rows = []
    for pos, alts in mismatch_counts.items():
        qbase = query_seq[pos - 1]
        for alt, n_hits in alts.items():
            sp_set = mismatch_species.get(pos, {}).get(alt, set())
            rows.append((len(sp_set), n_hits, pos, qbase, alt, sp_set))
    rows.sort(key=lambda t: (t[0], t[1]), reverse=True)

    for i, (n_sp, n_hits, pos, qbase, alt, sp_set) in enumerate(rows[:top_n], start=1):
        sp_list = sorted([s for s in sp_set if s], key=lambda x: x.lower())
        sp_examples = "; ".join(sp_list[:12]) + ("; …" if len(sp_list) > 12 else "")
        ws.append(
            [
                target_sciname,
                locus,
                query_accession,
                len(query_seq),
                pos,
                qbase,
                alt,
                n_hits,
                n_sp,
                sp_examples,
            ]
        )

    autosize_columns(ws)

    # Sheet 2: hits
    ws2 = wb.create_sheet("hits")
    ws2.append(
        [
            "accession",
            "sciname",
            "taxid",
            "coverage_frac",
            "mismatches",
            "snps",
            "dels",
            "bit_score",
            "evalue",
            "align_len",
            "identity",
            "title",
        ]
    )
    for c in ws2[1]:
        c.font = header_font
        c.alignment = Alignment(wrap_text=True, vertical="top")

    # сортируем по coverage и bit_score
    hits_rows_sorted = sorted(
        hits_rows,
        key=lambda r: (float(r.get("coverage_frac") or 0), float(r.get("bit_score") or 0)),
        reverse=True,
    )
    for r in hits_rows_sorted:
        ws2.append(
            [
                r.get("accession"),
                r.get("sciname"),
                r.get("taxid"),
                round(float(r.get("coverage_frac") or 0), 4),
                r.get("mismatches"),
                r.get("snps"),
                r.get("dels"),
                r.get("bit_score"),
                r.get("evalue"),
                r.get("align_len"),
                r.get("identity"),
                r.get("title"),
            ]
        )

    autosize_columns(ws2, max_width=80)

    # Sheet 3: meta
    ws3 = wb.create_sheet("meta")
    ws3.append(["key", "value"])
    ws3["A1"].font = header_font
    ws3["B1"].font = header_font
    ws3.append(["target_sciname", target_sciname])
    ws3.append(["locus", locus])
    ws3.append(["query_accession", query_accession])
    ws3.append(["query_header", query_header])
    ws3.append(["query_len", len(query_seq)])
    ws3.append(["generated_utc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())])
    autosize_columns(ws3, max_width=80)


    # Sheet 4: deletion ranges (query-anchored)
    ws4 = wb.create_sheet("del_ranges")
    ws4.append(["start_1based", "end_1based", "len", "min_n_species", "max_n_species", "min_n_hits", "max_n_hits", "species_examples"])
    for c in ws4[1]:
        c.font = header_font
        c.alignment = Alignment(wrap_text=True, vertical="top")

    del_pos = []
    for pos, alts in mismatch_counts.items():
        if "DEL" in alts:
            n_hits = alts["DEL"]
            n_sp = len(mismatch_species.get(pos, {}).get("DEL", set()))
            del_pos.append((pos, n_sp, n_hits, mismatch_species.get(pos, {}).get("DEL", set())))
    del_pos.sort(key=lambda x: x[0])

    # merge consecutive positions into ranges
    ranges = []
    cur = None
    for pos, n_sp, n_hits, sp_set in del_pos:
        if cur is None:
            cur = [pos, pos, [n_sp], [n_hits], set(sp_set)]
        elif pos == cur[1] + 1:
            cur[1] = pos
            cur[2].append(n_sp)
            cur[3].append(n_hits)
            cur[4].update(sp_set)
        else:
            ranges.append(cur)
            cur = [pos, pos, [n_sp], [n_hits], set(sp_set)]
    if cur is not None:
        ranges.append(cur)

    for start, end, n_sps, n_hits_list, sp_set in ranges:
        sp_list = sorted([s for s in sp_set if s], key=lambda x: x.lower())
        sp_examples = "; ".join(sp_list[:12]) + ("; …" if len(sp_list) > 12 else "")
        ws4.append([
            start, end, end - start + 1,
            min(n_sps), max(n_sps),
            min(n_hits_list), max(n_hits_list),
            sp_examples
        ])
    autosize_columns(ws4, max_width=80)

    wb.save(out_path)


def derive_locus_from_filename(path: str) -> str:
    base = os.path.basename(path)
    # ожидаем формат: Species__Locus__ACCESSION.fasta
    m = re.search(r"__([^_]+?)__[^_]+\.fasta$", base)
    if m:
        return m.group(1)
    return "unknown_locus"


def derive_accession_from_filename(path: str) -> str:
    base = os.path.basename(path)
    m = re.search(r"__([A-Z0-9_.]+)\.fasta$", base, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def analysis_key(query_seq: str, *, database: str, program: str, hitlist_size: int, expect: float, megablast: bool) -> str:
    core = f"{sha256_text(query_seq)}|{database}|{program}|{hitlist_size}|{expect}|{int(megablast)}"
    return sha256_text(core)[:24]


def save_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def load_manifest(manifest_path: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            rows.append(r)
    return rows


def pick_queries_from_manifest(rows: List[Dict[str, str]], *, prefer_verified: bool = True) -> List[str]:
    """
    Возвращает список путей FASTA, по одному на (species,locus).
    Логика:
      - если prefer_verified: берём первую запись с qc_pass==true/1/yes
      - иначе первую вообще
    """
    grouped: Dict[Tuple[str, str], List[Dict[str, str]]] = {}
    for r in rows:
        sp = r.get("species") or r.get("sp_key") or ""
        locus = r.get("locus") or r.get("locus_key") or ""
        fasta = r.get("fasta_path") or r.get("path") or r.get("file") or ""
        if not fasta:
            continue
        grouped.setdefault((sp, locus), []).append(r)

    picked: List[str] = []
    for (sp, locus), rr in sorted(grouped.items()):
        chosen = None
        if prefer_verified:
            for r in rr:
                v = (r.get("qc_pass") or r.get("verified") or "").strip().lower()
                if v in {"1", "true", "yes", "ok", "pass"}:
                    chosen = r
                    break
        if chosen is None:
            chosen = rr[0]
        fasta = chosen.get("fasta_path") or chosen.get("path") or chosen.get("file")
        if fasta:
            picked.append(fasta)
    return picked


def run_single(
    query_fasta_path: str,
    *,
    outdir: str,
    email: str,
    api_key: Optional[str],
    target_sciname: str,
    target_taxid: Optional[int],
    max_hits: int,
    expect: float,
    megablast: bool,
    min_cov: float,
    force: bool,
) -> Tuple[str, str, str]:
    """
    Выполняет полный цикл для одного query fasta.
    Возвращает пути (xlsx, aligned_fasta, raw_zip)
    """
    query_header, query_seq = read_first_fasta(query_fasta_path)
    locus = derive_locus_from_filename(query_fasta_path)
    query_acc = derive_accession_from_filename(query_fasta_path)

    key = analysis_key(query_seq, database="core_nt", program="blastn", hitlist_size=max_hits, expect=expect, megablast=megablast)
    subdir = os.path.join(outdir, "blast_analysis", target_sciname.replace(" ", "_"), locus)
    safe_mkdir(subdir)

    raw_zip_path = os.path.join(subdir, f"{key}__{query_acc or 'query'}__blast_JSON2.zip")
    raw_done_path = os.path.join(subdir, f"{key}__{query_acc or 'query'}__.done.json")
    aligned_fasta_path = os.path.join(subdir, f"{key}__{query_acc or 'query'}__aligned_query_anchored.fasta")
    xlsx_path = os.path.join(subdir, f"{key}__{query_acc or 'query'}__mismatch_summary.xlsx")

    # самопроверка
    if not force and os.path.exists(raw_done_path) and os.path.exists(aligned_fasta_path) and os.path.exists(xlsx_path):
        log(f"SKIP (already done): {os.path.basename(query_fasta_path)}", "OK")
        return xlsx_path, aligned_fasta_path, raw_zip_path

    # BLAST submission
    fasta_for_blast = f">{query_header}\n{query_seq}\n"
    ua = f"fusarium-blast-mismatch-analyzer/1.0 ({email})"
    log(f"Submitting BLAST: locus={locus}, query={query_acc or query_header}", "INFO")
    rid = blast_put(
        fasta_for_blast,
        database="core_nt",
        program="blastn",
        megablast=megablast,
        hitlist_size=max_hits,
        expect=expect,
        user_agent=ua,
    )
    log(f"RID={rid}", "OK")

    # get
    zip_bytes = blast_get_json2_zip(rid, user_agent=ua)
    save_bytes(raw_zip_path, zip_bytes)

    obj = load_blastoutput2_from_zip(zip_bytes)
    query_len, hits = extract_hits(obj)
    if query_len <= 0:
        query_len = len(query_seq)
    if query_len != len(query_seq):
        # иногда query_len != len(seq) из-за символов; используем фактическую
        query_len = len(query_seq)

    # Build aligned sequences (top hits, включая и целевые и нецелевые — но мы добавим только нецелевые для компактности)
    hit_aligned: List[Tuple[str, str]] = []
    for hi in hits[:max_hits]:
        anchored, covered, _ = build_query_anchored_seq(query_len, hi.hsp)
        cov = covered / max(1, query_len)
        if cov < min_cov:
            continue
        header = f"{hi.accession}|{hi.sciname or 'unknown'}|cov={cov:.3f}"
        hit_aligned.append((header, "".join(anchored)))

    write_aligned_fasta(aligned_fasta_path, f"{query_acc or 'QUERY'}|{target_sciname}|{locus}", query_seq, hit_aligned)

    # tally mismatches (только нецелевые)
    mismatch_counts, mismatch_species, hits_rows = tally_mismatches(
        query_seq,
        hits,
        target_sciname=target_sciname,
        target_taxid=target_taxid,
        max_hits_used=max_hits,
        min_coverage_frac=min_cov,
    )

    write_xlsx(
        xlsx_path,
        target_sciname=target_sciname,
        locus=locus,
        query_accession=query_acc,
        query_header=query_header,
        query_seq=query_seq,
        mismatch_counts=mismatch_counts,
        mismatch_species=mismatch_species,
        hits_rows=hits_rows,
        top_n=500,
    )

    done = {
        "analysis_key": key,
        "query_fasta_path": os.path.abspath(query_fasta_path),
        "query_header": query_header,
        "query_accession": query_acc,
        "locus": locus,
        "target_sciname": target_sciname,
        "target_taxid": target_taxid,
        "blast": {
            "database": "core_nt",
            "program": "blastn",
            "hitlist_size": max_hits,
            "expect": expect,
            "megablast": megablast,
            "rid": rid,
        },
        "outputs": {
            "raw_zip": os.path.abspath(raw_zip_path),
            "aligned_fasta": os.path.abspath(aligned_fasta_path),
            "xlsx": os.path.abspath(xlsx_path),
        },
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(raw_done_path, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=2)

    log(f"Saved: {xlsx_path}", "OK")
    return xlsx_path, aligned_fasta_path, raw_zip_path


def main() -> int:
    p = argparse.ArgumentParser(description="BLAST core_nt mismatch analyzer (query-anchored) -> aligned FASTA + XLSX")
    p.add_argument("--email", required=True, help="Email for NCBI etiquette (used in User-Agent)")
    p.add_argument("--api-key", default=None, help="NCBI api_key (не обязателен; для BLAST сейчас не используется)")
    p.add_argument("--outdir", required=True, help="Output directory (analysis will be placed under outdir/blast_analysis/)")
    p.add_argument("--target-sciname", default="Fusarium culmorum", help="Target species scientific name")
    p.add_argument("--target-taxid", type=int, default=None, help="Target taxid (optional; used to exclude target hits)")
    p.add_argument("--query-fasta", default=None, help="Single query fasta file")
    p.add_argument("--manifest", default=None, help="manifest.tsv path (from download_fusarium_loci.py)")
    p.add_argument("--analyze-from-manifest", action="store_true", help="Analyze all loci from manifest (one query per species×locus)")
    p.add_argument("--max-hits", type=int, default=200, help="HITLIST_SIZE for BLAST and max hits used in analysis")
    p.add_argument("--expect", type=float, default=10.0, help="BLAST EXPECT value")
    p.add_argument("--no-megablast", action="store_true", help="Disable megablast")
    p.add_argument("--min-cov", type=float, default=0.5, help="Min coverage fraction of query to keep a hit")
    p.add_argument("--force", action="store_true", help="Re-run even if analysis already exists")
    args = p.parse_args()

    safe_mkdir(args.outdir)

    if not args.query_fasta and not args.analyze_from_manifest:
        p.error("Provide --query-fasta or --analyze-from-manifest (with --manifest).")

    megablast = not args.no_megablast

    if args.query_fasta:
        run_single(
            args.query_fasta,
            outdir=args.outdir,
            email=args.email,
            api_key=args.api_key,
            target_sciname=args.target_sciname,
            target_taxid=args.target_taxid,
            max_hits=args.max_hits,
            expect=args.expect,
            megablast=megablast,
            min_cov=args.min_cov,
            force=args.force,
        )
        return 0

    # from manifest
    if not args.manifest:
        p.error("--manifest is required with --analyze-from-manifest")

    rows = load_manifest(args.manifest)
    queries = pick_queries_from_manifest(rows, prefer_verified=True)

    if not queries:
        raise SystemExit("No queries picked from manifest (check manifest columns).")

    log(f"Picked {len(queries)} query FASTA files from manifest", "INFO")
    ok = 0
    for q in queries:
        try:
            run_single(
                q,
                outdir=args.outdir,
                email=args.email,
                api_key=args.api_key,
                target_sciname=args.target_sciname,
                target_taxid=args.target_taxid,
                max_hits=args.max_hits,
                expect=args.expect,
                megablast=megablast,
                min_cov=args.min_cov,
                force=args.force,
            )
            ok += 1
        except Exception as e:
            log(f"Failed {q}: {e}", "ERROR")

    log(f"Done: {ok}/{len(queries)} analyses succeeded", "OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
