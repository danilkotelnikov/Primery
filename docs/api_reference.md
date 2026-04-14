# API Reference

> Public classes, methods, and functions in the Primery codebase

---

## Core Modules

### `core.ncbi_downloader` — NCBIDownloader

Handles NCBI sequence search and download via Biopython's Entrez API.

```python
class NCBIDownloader:
    def __init__(self, email: str, api_key: Optional[str] = None)
```

Sets `Entrez.email` and `Entrez.api_key`. Registers a tool name `"Primery_NCBI_Downloader"`.

#### Methods

**`p_search_loci_candidates(query: str, limit: int = 500) -> List[Dict]`**

Searches NCBI nuccore for potential loci. Uses an Entrez query filtering for sequences 200–10,000 bp, excluding whole genome shotguns and genome assemblies. Clusters results by gene name using regex heuristics on titles. Returns a list sorted by count descending, where each entry contains:

| Key | Type | Description |
|-----|------|-------------|
| `uid` | `str` | Cluster key (normalized gene name) |
| `title` | `str` | Representative title with gene key |
| `accession` | `str` | Example accession numbers (up to 3) |
| `count` | `int` | Number of matching sequences |
| `length` | `int` | Always 0 (not relevant for clusters) |

**`fetch_loci(taxid: int, organism_label: str, loci_config: Dict[str, Dict], outdir: str, n_per_locus: int = 10, strict_qc: bool = True, keep_unverified: bool = False) -> str`**

Downloads sequences for specified loci. Parameters:

- `taxid`: NCBI Taxonomy ID
- `organism_label`: Display name for directory creation
- `loci_config`: Dictionary of `{locus_key: {"search_terms": [...], "verify_terms": [...]}}`. Search terms are ORed in the Entrez query; verify terms are checked against GenBank annotations.
- `outdir`: Workspace root directory
- `n_per_locus`: Maximum sequences per locus (default 10)
- `strict_qc`: When `True`, verify terms are checked only against `/gene=`, `/product=`, and DEFINITION fields. When `False`, the entire GenBank text is searched.
- `keep_unverified`: Save sequences that fail QC (default `False`)

Returns the path to the created manifest TSV file.

**`_verify_qc(gb_text: str, verify_terms: List[str], strict: bool) -> Tuple[bool, str]`**

Checks GenBank record text for the presence of verify terms in `/gene=`, `/product=`, DEFINITION, and KEYWORDS fields. Returns `(is_verified, note)`.

**`_safe_name(s: str) -> str`**

Sanitizes a string for filesystem use: strips whitespace, replaces spaces with underscores, removes non-alphanumeric characters.

---

### `core.blast_analyzer` — BlastAnalyzer

GUI-facing wrapper around `blast_mismatch_analyzer`. Delegates BLAST submission, mismatch tallying, and output generation.

```python
class BlastAnalyzer:
    def __init__(self, email: str, api_key: Optional[str] = None)
```

#### Methods

**`run_analysis(fasta_paths: List[str], target_sciname: str, target_taxid: int, workspace: str, max_hits: int = 200, megablast: bool = True, db: str = "core_nt", limit: str = None, force: bool = False) -> List[Dict]`**

Analyzes multiple FASTA files. For each file, calls `_analyze_single()`. After all files in a gene group are processed, calls `_generate_general_summary()`. Returns a list of result dicts with keys: `status`, `path`, `aligned_fasta`, `raw_zip`, `file`, `gene`, `accession`, `seq_len`.

**`_analyze_single(path, target_sciname, target_taxid, workspace, gene, max_hits=200, megablast=True, force=False) -> Dict`**

Processes a single FASTA file:
1. Computes an analysis key (SHA-256 hash of query + BLAST parameters)
2. Checks for cached results (`.done.json`)
3. Submits BLAST via `blast_put()`
4. Retrieves JSON2 ZIP via `blast_get_json2_zip()`
5. Builds query-anchored alignments
6. Tallies mismatches (excluding target species)
7. Writes XLSX and aligned FASTA

**`_generate_general_summary(gene, res_list, workspace, organism)`**

Aggregates per-accession mismatch results:
1. Reads all `*__mismatch_summary.xlsx` files
2. Identifies conservative positions (present in 2+ accessions)
3. Clusters positions using `_cluster_positions(positions, primer_len=25)`
4. Ranks clusters via `_rank_clusters()` with score = `n_species × mean_acc_frac`
5. Writes `{gene}_general_summary.xlsx` (4 sheets: clusters, conservative_mismatches, per_accession, all_positions)
6. Writes `{gene}_cluster_meta.json`

#### Module-level Functions

**`_cluster_positions(positions: List[int], primer_len: int = 25) -> List[List[int]]`**

Groups mismatch positions into primer-length-sized clusters. Positions within `primer_len` bp of each other are grouped together.

**`_rank_clusters(clusters, pos_data, n_total_acc) -> List[dict]`**

Scores and ranks clusters by species discrimination power.

---

### `core.blast_mismatch_analyzer` — Standalone Functions

Low-level BLAST operations and mismatch analysis. Uses NCBI's Common URL API directly via `requests`.

**Constants:**

- `BLAST_ENDPOINT = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"`

**Dataclass:**

```python
@dataclass
class HitInfo:
    accession: str
    title: str
    sciname: str
    taxid: Optional[int]
    hsp: Dict
```

#### Functions

**`blast_put(query_fasta: str, *, program="blastn", database="core_nt", megablast=True, hitlist_size=200, expect=10.0, user_agent=..., timeout=60) -> str`**

Submits a BLAST query to NCBI. Returns the Request ID (RID). Parameters are sent via POST to `Blast.cgi` with `CMD=Put`.

**`blast_get_json2_zip(rid: str, *, poll_interval=5.0, max_wait_s=1800, user_agent=..., timeout=60) -> bytes`**

Polls NCBI for BLAST results. Returns the raw ZIP bytes containing JSON2 output. Raises `TimeoutError` after `max_wait_s` seconds (default 30 minutes). Raises `RuntimeError` on BLAST FAILED status.

**`load_blastoutput2_from_zip(zip_bytes: bytes) -> Dict`**

Extracts `BlastOutput2` JSON from a ZIP archive. Handles both direct JSON files and BlastJSON index files.

**`extract_hits(blast_json: Dict) -> Tuple[int, List[HitInfo]]`**

Extracts query length and hit information from parsed BLAST JSON. Selects the best HSP per hit (highest bit_score, then align_len).

**`build_query_anchored_seq(query_len: int, hsp: Dict) -> Tuple[List[str], int, int]`**

Builds a query-anchored alignment of length `query_len`. Positions outside HSP coverage are marked `N`. Deletions in the hit are marked `-`. Insertions in the hit (gaps in query) are skipped. Returns `(char_list, covered_bases, aligned_columns_used)`.

**`tally_mismatches(query_seq, hits, *, target_sciname=None, target_taxid=None, max_hits_used=200, min_coverage_frac=0.5) -> Tuple[counts, species, hits_rows]`**

Counts mismatches per position across non-target hits. Returns:
- `counts[pos][alt]` — number of hits with that mismatch
- `species[pos][alt]` — set of species names
- `hits_rows` — list of per-hit statistics dicts

**`write_aligned_fasta(out_path, query_header, query_seq, hit_seqs, line_width=80)`**

Writes a multi-sequence FASTA file. First record is the query; remaining records are aligned hits (same length, `N` for uncovered, `-` for deletions).

**`write_xlsx(out_path, *, target_sciname, locus, query_accession, query_header, query_seq, mismatch_counts, mismatch_species, hits_rows, top_n=200)`**

Creates an XLSX workbook with 4 sheets: `summary` (mismatch positions), `hits` (per-hit statistics), `meta` (key-value metadata), `del_ranges` (deletion ranges).

**`read_first_fasta(path: str) -> Tuple[str, str]`**

Reads the first FASTA record from a file. Returns `(header, sequence)`. Sanitizes non-standard characters to `N`, removes gaps.

**`analysis_key(query_seq, *, database, program, hitlist_size, expect, megablast) -> str`**

Computes a 24-character SHA-256 hash key for caching analysis results.

**`load_manifest(manifest_path: str) -> List[Dict[str, str]]`**

Reads a TSV manifest file into a list of dictionaries.

**`pick_queries_from_manifest(rows, *, prefer_verified=True) -> List[str]`**

Selects one FASTA path per (species, locus) pair from manifest rows. Prefers verified sequences when `prefer_verified=True`.

---

### `core.primer_designer` — PrimerDesigner

Cluster-pair primer design using Primer3.

**Constants:**

```python
METHOD_PARAMS = {
    "pcr":   {"min_size": 18, "opt_size": 22, "max_size": 25,
              "product": [100, 500], "min_tm": 55.0, "opt_tm": 60.0, "max_tm": 65.0},
    "qpcr":  {"min_size": 18, "opt_size": 20, "max_size": 25,
              "product": [70, 180],  "min_tm": 58.0, "opt_tm": 60.0, "max_tm": 62.0},
    "rpa":   {"min_size": 30, "opt_size": 33, "max_size": 36,
              "product": [100, 300], "min_tm": 50.0, "opt_tm": 54.0, "max_tm": 58.0},
    "nasba": {"min_size": 20, "opt_size": 25, "max_size": 30,
              "product": [100, 250], "min_tm": 55.0, "opt_tm": 60.0, "max_tm": 65.0},
    "lamp":  {"min_size": 18, "opt_size": 22, "max_size": 25,
              "product": [150, 350], "min_tm": 58.0, "opt_tm": 62.0, "max_tm": 68.0},
}
```

```python
class PrimerDesigner:
    def __init__(self)
```

#### Methods

**`design_primers_from_clusters(seq: str, mode: str, clusters: List[Dict], n_per_pair: int = 50, n_top: int = 10, n_cluster_pairs: int = 20, custom_settings: Dict = None) -> List[Dict]`**

Main design method. Algorithm:
1. Re-clusters all mismatch positions using method-specific `max_size`
2. Scores clusters by species union size
3. Enumerates valid (forward, reverse) cluster pairs within product size range
4. Runs Primer3 for each pair with `SEQUENCE_PRIMER_PAIR_OK_REGION_LIST`
5. Scores and ranks candidates globally
6. Returns top non-repeating primer pairs

Each returned dict contains:
`fwd_cluster_id`, `rev_cluster_id`, `left`, `right`, `left_pos`, `left_len`, `right_pos`, `right_len`, `left_tm`, `right_tm`, `left_hairpin_tm`, `right_hairpin_tm`, `left_dimer_tm`, `right_dimer_tm`, `pair_compl_tm`, `thermal_penalty`, `product_size`, `primer3_penalty`, `fwd_mm_covered`, `rev_mm_covered`, `total_mm_covered`, `n_species_covered`, `score`, `global_rank`.

**`_extract_pair(results, i, seq, fwd_cluster, rev_cluster, union_species, pos_species) -> Dict`**

Extracts a single primer pair from Primer3 output and computes the composite score.

**`_design_unclustered(seq, mode, n_return=10, custom_settings=None) -> List[Dict]`**

Fallback when no valid cluster pairs exist. Runs Primer3 without region constraints.

**`_build_primer3_settings(params, custom=None) -> Dict`**

Builds the Primer3 global settings dictionary. Key settings: `PRIMER_TM_FORMULA=1` (SantaLucia), `PRIMER_SALT_CORRECTIONS=1`, `PRIMER_MAX_NS_ACCEPTED=1`.

---

### `core.primer_specificity` — SpecificityAnalyzer

Primer-BLAST-like specificity checking using remote NCBI BLAST.

```python
class SpecificityAnalyzer:
    def __init__(self)
```

#### Methods

**`run_primer_blast(primers: List[Dict], database: str = "nt", organism_filter: str = "", target_organism: str = "", output_dir: str = None) -> List[Dict]`**

Checks specificity for a list of primers. Each primer dict must have `fwd`/`left` and `rev`/`right` keys containing sequences.

BLAST parameters: `program="blastn"`, `expect=1000`, `word_size=7`, `hitlist_size=100`.

Amplicon detection: Both primers hit the same accession on opposite strands, distance 50–3000 bp.

Classification logic:
- **Species-Specific**: Target amplicons present, no off-target genus amplicons, no strong same-genus off-targets (< 3 mismatches)
- **Genus-Specific**: Target amplicons present, same-genus off-targets with < 3 total mismatches
- **Non-Specific**: Off-target amplicons from different genera (< 5 total mismatches)
- **No Hits**: No amplicons detected

Returns the input list with added fields: `specificity_status`, `target_hits`, `off_target_hits`.

---

### `core.report_generator`

Report generation in PDF and DOCX formats.

**`class ReportDataCollector(workspace: str)`**

Collects analysis data from the filesystem.

**`collect(organism: str, gene: str) -> dict`**

Returns a dictionary with:
- `organism`, `gene`, `timestamp`
- `reference`: dict with `file`, `header`, `length`, `accession` from the longest FASTA
- `clusters`: list from `{gene}_cluster_meta.json`
- `primer_sets`: list from `{gene}_*_primers.json` files
- `specificity`: list parsed from `PrimerBLAST_*.txt` files
- `specificity_table`: flat list of per-pair specificity rows

**`generate_pdf(all_data: List[dict], output_path: str, screenshot_path: str = None) -> str`**

Generates an A4 PDF report using ReportLab. Features:
- Google Sans Flex typography (falls back to Helvetica)
- Color-coded tables: green (gene info), blue (primers), purple (specificity)
- Gold decorative accents
- Page numbers in footer
- Optional sequence map screenshot

**`generate_docx(all_data: List[dict], output_path: str, screenshot_path: str = None) -> str`**

Generates an A4 DOCX report using python-docx. Mirrors the PDF layout with matching colors and typography.

---

## GUI Modules

### `gui.main_window` — MainWindow

The primary application window. Extends `QMainWindow`.

Key methods:
- `run_worker(func, *args, on_result=None, on_error=None)` — Runs a function in a `BaseWorker` thread
- `log_message(msg)` — Appends text to the log dock
- Tab/viewer management, NCBI/BLAST/primer/specificity/report handler methods
- `map_mismatches()`, `map_primers()`, `map_all()` — Mapping functions

**`class StreamRedirector(QObject)`**:
- `message = Signal(str)` — Emitted for each line of redirected output
- Used to capture `stdout`/`stderr` to the log dock

### `gui.sequence_viewer` — SequenceViewer

`QGraphicsView`-based sequence visualization with annotation tracks.

Key methods:
- `set_font(font_family: str)` — Sets the monospace font
- `set_color_scheme(scheme_name: str)` — Changes nucleotide colors
- `set_cols_per_row(n: int)` — Sets sequence wrapping width
- `load_sequence(header: str, seq: str)` — Loads a FASTA sequence
- `add_mismatches(mismatch_data)` — Adds mismatch heatmap track
- `add_clusters(cluster_data)` — Adds cluster region track
- `add_primers(primer_data)` — Adds primer arrow track
- `add_amplicons(amplicon_data)` — Adds amplicon bracket track
- `finish_annotations()` — Finalizes layout after adding annotations
- `export_to_image(path: str)` — Exports the scene to PNG
- `copy_sel()` — Copies selected sequence to clipboard

Constants: `COLOR_SCHEMES`, `MONOSPACE_FONTS`, track heights (`RULER_H=18`, `SEQ_H=18`, `MM_H=8`, `CLUSTER_H=10`, `PRIMER_H=8`, `AMPLICON_H=10`, `TRACK_GAP=2`, `HEADER_W=55`).

### `gui.workers` — BaseWorker

```python
class BaseWorker(QThread):
    finished_result = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, func, *args, **kwargs)
```

Generic background worker. Executes `func(*args, **kwargs)` in a separate thread. Emits `finished_result` on success, `error_occurred` on exception.

### `gui.gui_context` — GUIContext

```python
class GUIContext(QObject):
    workspace_changed = Signal(str)
    language_changed = Signal(str)

    def __init__(self)
```

Global state singleton. Properties: `workspace_path`, `lang`, `email`, `api_key`. Methods: `set_workspace(path)`, `set_language(lang)`. A module-level `context` instance is created on import.

### `gui.i18n` — Internationalization

```python
STRINGS = {
    'en': { ... },  # 100+ keys
    'ru': { ... },  # 100+ keys (Russian translations)
}

def tr(lang: str, key: str) -> str
```

Dictionary-based translation. Returns `STRINGS[lang][key]` or the key itself if not found.

### `gui.dialogs`

**`class MismatchDialog(QDialog)`** — Viewer for mismatch analysis results. Methods: `load_general()`, `load_specific()`.

**`class PrimerSettingsDialog(QDialog)`** — Advanced primer design settings with tabbed interface. Constructor: `__init__(current_settings=None, preset_params=None, parent=None)`. Methods: `load_preset()`, `get_settings()`, `get_max_pairs()`, `get_cluster_pairs_limit()`, `get_specificity_settings()`.

### `gui.selection_dialog`

**`class SelectionDialog(QDialog)`** — Tree-based selection of organisms and genes from the workspace. Constructor: `__init__(workspace, title="Select Targets", parent=None)`. Returns list of `{"organism": str, "genes": [str]}`. Methods: `select_all()`, `deselect_all()`, `accept_selection()`.

### `gui.report_dialog`

**`class ReportDialog(QDialog)`** — Report generation options. Constructor: `__init__(workspace, parent=None)`. Provides: organism/gene tree selection, format choice (PDF/DOCX/Both), screenshot inclusion toggle, nucleotides-per-row setting. Properties: `selections`, `output_format`, `output_dir`.

### `gui.widgets`

**`class HintLabel(QLabel)`** — Label with tooltip hint. Constructor: `__init__(text, hint="", parent=None)`.

**`class Separator(QFrame)`** — Horizontal or vertical separator line. Constructor: `__init__(vertical=False)`.
