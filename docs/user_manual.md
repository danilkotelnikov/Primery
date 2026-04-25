# User Manual

> Complete guide to the Primery graphical interface

---

## New In v0.2.0

Primery now includes the workflow changes below:

- broader NCBI gene discovery with canonical names, aliases, examples, and
  per-locus FASTA download limits
- explicit gene/folder selection before BLAST analysis, primer design, probe
  design, specificity analysis, and mapping
- editable FASTA sequence views with validation, reverse complement,
  translation, trimming, and IUPAC motif search
- mismatch limit modes for species, isolate/strain, genus, and clade/species
  complex analysis
- Primer3 design that avoids invalid IUPAC template crashes and favors
  discriminatory mismatches near the primer 3' end
- qPCR/TaqMan, MGB-style, molecular beacon, and RPA/exo probe design
- primer plus probe assay-specificity evaluation
- nucleotide-resolution primer and probe mapping arrows
- in-app primer table and specificity report viewers
- settings for editor, application, analysis, and keyboard behavior

For the recommended workflow and interpretation of new specificity statuses,
see [Feature Guidelines](feature_guidelines.md).

---

## Interface Overview

Primery uses a dock-based IDE-style layout built with PySide6. The main window consists of:

- **Central Area** — A tabbed `QTabWidget` with closable `SequenceViewer` tabs. An initial "Start" tab is created on launch.
- **Files Dock** (left) — A `QTreeView` powered by `QFileSystemModel` showing the workspace directory. Right-click context menu opens files or folders in Explorer.
- **NCBI Tools Dock** (right) — Controls for organism search and locus download.
- **Analysis & Design Dock** (right) — BLAST mismatch analysis, Primer3 design, and Primer-BLAST specificity controls.
- **Log Dock** (bottom) — Captures `stdout` and `stderr` via `StreamRedirector`, showing real-time progress of all background tasks.

Additional docks (**Primer Results**, **Specificity Results**) appear dynamically when primers are designed or specificity checks complete.

---

## Toolbar

The toolbar runs across the top of the window and contains:

| Control | Description |
|---------|-------------|
| **Workspace** path + **Change** button | Sets the working directory for all file operations |
| **API Key** field | Optional NCBI API key (increases rate limit from 3 to 10 req/s) |
| **References** dropdown | Quick-open buttons for BLAST, Genes, and Workspace folders in the system file manager |
| **Map** dropdown | Mapping actions: *Mismatches & Clusters*, *Primers & Amplicons*, *Map All* |
| **Color Scheme** selector | Choose nucleotide coloring: Classic, Nucleotide, Shapely, or Rasmol |
| **Font** selector | Monospace font for the viewer: Consolas, Courier New, Lucida Console, DejaVu Sans Mono, Source Code Pro, JetBrains Mono, Fira Code, IBM Plex Mono |
| **Report** button | Opens the Report generation dialog |

---

## Menu Bar

| Menu | Items |
|------|-------|
| **View** | Toggle visibility of each dock (Files, NCBI Tools, Analysis & Design, Log) |
| **Map** | Mismatches & Clusters, Primers & Amplicons, Map All |
| **References** | Open BLAST folder, Genes folder, Workspace folder in system file manager |
| **Report** | Generate Report |

---

## Step-by-Step Workflow

### Step 1: Download Loci

1. Enter the **organism name** (e.g., `Fusarium culmorum`) in the NCBI Tools dock.
2. Click **Search Genes**. This calls `NCBIDownloader.p_search_loci_candidates()` which searches NCBI nuccore (sequence length 200–10,000 bp, excluding whole genomes), clusters results by gene name heuristic, and returns them sorted by count.
3. A table appears listing available loci with their counts and example accessions.
4. **Check** the loci you want to download.
5. Click **Download Selected**. This calls `NCBIDownloader.fetch_loci()` which:
   - Searches `nuccore` with taxid-specific queries
   - Filters by length (200–10,000 bp)
   - Fetches GenBank records for quality control (`_verify_qc` checks `/gene=` and `/product=` annotations)
   - Downloads FASTA sequences
   - Rate-limits at 0.34 s/request

**Output directory structure:**

```
{Workspace}/{Organism}/
├── Genes/
│   ├── {Locus1}/
│   │   ├── {Locus}__{Accession}.fasta
│   │   └── ...
│   └── {Locus2}/
│       └── ...
└── {Organism}_loci.tsv          # manifest
```

### Step 2: BLAST Mismatch Analysis

1. In the Analysis & Design dock, click **Analyze Specificity**.
2. A `SelectionDialog` lets you choose which organisms and genes to analyze.
3. `BlastAnalyzer.run_analysis()` processes each FASTA file:
   - Submits BLASTN to NCBI `core_nt` database via the Common URL API
   - Retrieves results as JSON2 (ZIP format)
   - Builds query-anchored alignments
   - Tallies mismatches: SNP (base substitution) and DEL (deletion in hit)
   - Skips hits matching the target species (by taxid or scientific name)
   - Writes per-accession XLSX results
4. After all accessions in a gene are analyzed, `_generate_general_summary()`:
   - Aggregates mismatches across accessions
   - Identifies conservative positions (present in 2+ accessions)
   - Clusters positions into primer-length landing zones (25 bp default)
   - Ranks clusters by species discrimination score: `n_species × mean_acc_frac`
   - Writes `{Gene}_general_summary.xlsx` and `{Gene}_cluster_meta.json`

**Output:**

```
{Workspace}/{Organism}/BLAST/{Gene}/
├── {hash}__{Accession}__mismatch_summary.xlsx
├── {hash}__{Accession}__aligned_query_anchored.fasta
├── {hash}__{Accession}__blast_JSON2.zip
├── {hash}__{Accession}__.done.json
├── {Gene}_general_summary.xlsx
└── {Gene}_cluster_meta.json
```

### Step 3: Primer Design

1. Select a **Preset** from the dropdown:

| Preset | Primer Length | Tm Range | Product Size |
|--------|--------------|----------|--------------|
| PCR | 18–25 bp | 55–65 °C | 100–500 bp |
| qPCR | 18–25 bp | 58–62 °C | 70–180 bp |
| RPA | 30–36 bp | 50–58 °C | 100–300 bp |
| NASBA | 20–30 bp | 55–65 °C | 100–250 bp |
| LAMP (Outer) | 18–25 bp | 58–68 °C | 150–350 bp |

2. Click **Design Primers**. `PrimerDesigner.design_primers_from_clusters()`:
   - Re-clusters conservative mismatch positions using the method-specific maximum primer length
   - Enumerates valid `(forward_cluster, reverse_cluster)` pairs where the product span fits the size range
   - For each pair, calls Primer3 with `SEQUENCE_PRIMER_PAIR_OK_REGION_LIST` to constrain primer placement
   - Scores each candidate:
     - `+10 × n_species_covered` (species discrimination)
     - `+5 × total_mismatches_covered` (mismatch coverage)
     - `+15` for mismatch at 3' end, `+5` for 3'-1 or 3'-2 positions
     - `-0.5 × thermal_penalty` (hairpin + self-dimer + pair complementarity)
   - Picks top N non-repeating primers (minimum 15 bp positional distance)

3. **Advanced Settings** — Click the settings button to open `PrimerSettingsDialog` with tabs:
   - **Primer Size & Tm**: min/opt/max size, min/opt/max Tm
   - **Product & Output**: product size range, number of pairs to return, cluster pairs limit
   - **Thermodynamics**: Tm formula (SantaLucia), salt corrections
   - **Specificity**: database, organism filter, target organism

**Output:**

```
{Workspace}/{Organism}/BLAST/{Gene}/
└── {Gene}_{method}_primers.json
```

### Step 4: Specificity Check

1. After primers are designed, click **Run Specificity Check** in the Analysis dock.
2. `SpecificityAnalyzer.run_primer_blast()` submits each primer pair:
   - Uses `blastn-short` via Biopython's `NCBIWWW.qblast` (expect=1000, word_size=7, hitlist_size=100)
   - Identifies amplicons: forward and reverse hits on the same accession, opposite strands, distance 50–3000 bp
   - Classifies specificity:
     - **Species-Specific**: Target amplicon found, no off-target genus amplicons, no strong same-genus off-targets
     - **Genus-Specific**: Target amplicon found, same-genus off-targets with < 3 total mismatches
     - **Non-Specific**: Off-target amplicons from different genera
     - **No Hits**: No amplicons detected
   - Rate-limits at 2 s between requests

**Output:**

```
{Workspace}/{Organism}/Primer-BLAST/
└── PrimerBLAST_{timestamp}.txt
```

---

## Sequence Viewer

The `SequenceViewer` is a `QGraphicsView`-based component with a dark background (`#1C1C20`) and multiple annotation tracks:

| Track | Height | Description |
|-------|--------|-------------|
| **Ruler** | 18 px | Position numbers at regular intervals |
| **Sequence** | 18 px | Color-coded nucleotide letters (A/T/G/C/N) |
| **Mismatch Heatmap** | 8 px | Red intensity proportional to mismatch frequency |
| **Cluster Regions** | 10 px | Colored rectangles marking cluster spans |
| **Primer Arrows** | 8 px per primer | Green arrows (forward), red arrows (reverse) |
| **Amplicon Brackets** | 10 px | Brackets spanning the amplicon region |

**Color Schemes** (all share the dark background):

| Scheme | A | T | G | C |
|--------|---|---|---|---|
| Classic | Green | Red | White/Gray | Blue |
| Nucleotide | Bright Green | Bright Red | Yellow | Blue |
| Shapely | Light Green | Orange | Pink | Yellow |
| Rasmol | Dark Red | Blue | Yellow | Green |

**Interactions:**
- **Selection**: Click and drag to select a sequence region
- **Copy**: Right-click → Copy, or Ctrl+C to copy selected sequence
- **Export**: Right-click → Export to Image saves the visible view as PNG

---

## Mapping

Use the **Map** menu or toolbar dropdown to overlay analysis results onto the sequence viewer:

| Action | Data Sources | Visual Result |
|--------|-------------|---------------|
| **Mismatches & Clusters** | `{Gene}_general_summary.xlsx` + `{Gene}_cluster_meta.json` | Mismatch heatmap + cluster rectangles |
| **Primers & Amplicons** | `{Gene}_{method}_primers.json` | Forward/reverse primer arrows + amplicon brackets |
| **Map All** | All of the above | Combined overlay |

Each action opens a `SelectionDialog` to pick organisms and genes from the workspace.

---

## Reports

1. Go to **Report → Generate Report** (or click the Report toolbar button).
2. `ReportDialog` opens with:
   - A tree view to select organisms and genes
   - Format options: PDF, DOCX, or Both
   - Option to include a sequence map screenshot
   - Nucleotides-per-row setting for the screenshot
3. Click **Generate**. `ReportDataCollector` gathers:
   - Reference FASTA info (longest sequence)
   - Cluster composition from `{Gene}_cluster_meta.json`
   - Primer sets from `{Gene}_*_primers.json`
   - Specificity results from `PrimerBLAST_*.txt`
4. `generate_pdf()` creates an A4 PDF using ReportLab with Google Sans typography, colored tables (green for gene info, blue for primers, purple for specificity), and optional sequence map image.
5. `generate_docx()` creates an A4 DOCX using python-docx with matching styling.

---

## Internationalization

The interface supports English and Russian. The `gui/i18n.py` module contains a `STRINGS` dictionary with `'en'` and `'ru'` sub-dictionaries mapping 100+ UI string keys to translations. The `tr(lang, key)` function performs lookups. Language is stored in `GUIContext.lang` and can be switched at runtime via the `language_changed` signal.
