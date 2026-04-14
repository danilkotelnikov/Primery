# Primery — Species-Specific Primer Design

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

**Primery** is a bioinformatics desktop application for designing species-specific diagnostic primers. It automates the full workflow — from gene sequence retrieval to primer validation — through an intuitive PySide6 GUI, replacing what traditionally requires multiple disconnected tools and manual steps.

The application targets researchers and diagnosticians who need primers that reliably amplify a **target organism** while avoiding cross-reactivity with closely related non-target species. Primery achieves this by analyzing BLAST mismatch patterns across homologous sequences, clustering discriminatory positions into primer landing zones, and scoring candidates by their species discrimination power.

---

## Features

| Feature | Description |
|---------|-------------|
| **NCBI Integration** | Search and download gene/locus sequences from NCBI Nucleotide with automatic QC |
| **BLAST Mismatch Analysis** | Identify positions where non-target species differ; cluster them into primer landing zones |
| **Primer3 Design** | Cluster-pair design with mismatch-aware scoring and 3′ end bonus |
| **Primer-BLAST Validation** | Check primer specificity against NCBI databases |
| **Sequence Viewer** | Dark-themed viewer with mismatch heatmap, cluster regions, primer arrows, and amplicon brackets; JBrowse2 integration |
| **Amplification Presets** | PCR · qPCR · RPA · NASBA · LAMP (outer primers) |
| **Report Generation** | PDF and DOCX reports with colored tables and optional sequence maps |
| **Bilingual Interface** | Full English / Russian localization |

---

## Quick Start

### Option 1 — Automated Setup (Windows, one click)

```
1. Clone or download this repository
2. Double-click  install.bat   ← downloads portable Python + all dependencies
3. Double-click  run.bat       ← launches the app
```

No system Python required — everything is self-contained.

### Option 2 — Conda / pip

```bash
conda create -n primery python=3.12 -y
conda activate primery
pip install -r requirements.txt
python primery_app.py
```

> **First run:** The `run.bat` launcher automatically installs Miniforge, creates a `primery` Conda environment, installs dependencies, and creates a desktop shortcut. Allow 5–10 minutes on first run.

---

## Complete Workflow

```
1. Download reference sequences
   Organism name → Search NCBI → Select loci → Download Selected

2. Analyze mismatch patterns
   Analyze Specificity → Select organisms and genes → BLAST runs remotely

3. Design primers
   Select preset (PCR / qPCR / RPA / NASBA / LAMP) → Design Primers → Review

4. Validate specificity
   Enter primer sequences → Run Primer-BLAST → Check on/off-target amplicons

5. Generate report
   Build HTML + PDF Report → Ready-to-share PDF or DOCX
```

### Example: Primers for *Fusarium culmorum*

```
Step 1  Download Loci
        Organism: Fusarium culmorum (taxid 5516) → loci: TEF1, RPB2, ITS
        Output: manifest.tsv, Genes/{LOCUS}/*.fasta

Step 2  BLAST Mismatch Analysis
        Input: manifest.tsv, target taxid 5516, max hits 200
        Output: BLAST/{LOCUS}/*_cluster_meta.json, *_mismatch_summary.xlsx

Step 3  Primer3 Design
        Preset: qPCR, min mismatch 50 %, top windows 10, return 5 pairs
        Output: BLAST/{LOCUS}/*_qpcr_primers.json

Step 4  Primer-BLAST
        Database: core_nt, scope: genus
        Output: Primer-BLAST/PrimerBLAST_{timestamp}.txt

Step 5  Report → Reports/report.pdf
```

---

## Algorithm

### 1. Sequence Retrieval

Entrez `esearch` / `efetch` pull GenBank records. QC filters by length and annotation completeness.

### 2. BLAST Mismatch Analysis

- Target sequence is submitted to **BLASTN** against `core_nt` via the [NCBI BLAST Common URL API](https://blast.ncbi.nlm.nih.gov/doc/blast-help/urlapi.html).
- Hits matching the target taxid are excluded; only **non-target species** are retained.
- Each HSP is projected onto the query coordinate system (query-anchored alignment). Positions outside the HSP → `N`; deletions in the hit → `-`.
- At every query position, substitutions (SNPs) and deletions are counted across all non-target hits, recording both **hit count** and **species count**.

### 3. Cluster Detection

Mismatch-rich positions are grouped into primer-length-sized landing zones ("clusters"). Two positions belong to the same cluster if they are within `primer_len` bp of each other (25 bp for PCR, 35 bp for RPA).

Cluster score:

```
score = n_species × mean_accession_fraction
```

### 4. Primer Design (Primer3)

Valid forward/reverse cluster pairs within the product-size window are passed to Primer3 via `SEQUENCE_PRIMER_PAIR_OK_REGION_LIST`. Candidates are scored:

```
score = (n_species_covered × 10)
      + (total_mismatches_covered × 5)
      + 3′_end_bonus           (+15 at position 0, +5 at positions −1 and −2)
      − (thermal_penalty × 0.5)
```

Thermal penalty = `max(hairpin_Tm) + max(self_dimer_Tm) + pair_complementarity_Tm`.

### 5. Specificity Verification

Top candidates are re-submitted to Primer-BLAST (`blastn-short`, word size 7, expect 1000) for cross-reactivity screening.

---

## Amplification Presets

| Method | Primer Length | Tm Range | Product Size | Notes |
|--------|:------------:|:--------:|:------------:|-------|
| **PCR** | 18–25 bp | 55–65 °C | 100–500 bp | General diagnostics |
| **qPCR** | 18–25 bp | 58–62 °C | 70–180 bp | Short amplicons preferred; tight ΔTm |
| **RPA** | 30–36 bp | 50–58 °C | 100–300 bp | Isothermal (37–42 °C); point-of-care |
| **NASBA** | 20–30 bp | 55–65 °C | 100–250 bp | RNA detection; one primer carries T7 |
| **LAMP (outer)** | 18–25 bp | 58–68 °C | 150–350 bp | F3/B3 only; inner FIP/BIP designed separately |

### Thermodynamics

Primery uses the **SantaLucia nearest-neighbor method** (Primer3 `PRIMER_TM_FORMULA=1`) with **SantaLucia 1998 salt correction** (`PRIMER_SALT_CORRECTIONS=1`). Hairpin, self-dimer, and heterodimer Tm values are computed for each candidate and factored into the penalty score.

---

## Architecture

### Technology Stack

| Component | Library | Purpose |
|-----------|---------|---------|
| GUI | PySide6 ≥ 6.0 | Qt for Python — widgets, graphics, threading |
| Bioinformatics | Biopython ≥ 1.80 | Entrez API, SeqIO, BLAST wrappers |
| Primer Design | primer3-py ≥ 2.0 | Primer3 thermodynamic engine |
| Spreadsheets | openpyxl ≥ 3.0 | XLSX read/write |
| PDF | ReportLab ≥ 3.6 | A4 reports with custom typography |
| DOCX | python-docx ≥ 0.8.11 | Styled Word documents |
| HTTP | requests ≥ 2.28 | NCBI BLAST Common URL API |

### Data Flow

```
Organism name
    └─▶ NCBI Entrez ──▶ FASTA files + manifest.tsv
                              │
                              ▼
                      BLAST Mismatch Analysis
                              │
                    ┌─────────┴──────────┐
              mismatch.xlsx        cluster_meta.json
                                         │
                                         ▼
                                  Primer3 Design ──▶ primers.json
                                         │
                                         ▼
                                  Primer-BLAST ──▶ specificity.txt
                                         │
                              ┌──────────┴──────────┐
                        SequenceViewer          Report Generator
                                                     │
                                               PDF / DOCX
```

### Threading Model

All long-running operations (NCBI downloads, BLAST, Primer3, report generation) run in `BaseWorker(QThread)` background threads. Results are delivered back to the Qt main thread via `finished_result = Signal(object)`. `StreamRedirector` captures stdout/stderr and pipes each line to the log dock.

### Project Structure

```
Primery/
├── primery_app.py              # Entry point
├── requirements.txt
├── run.bat / install.bat       # Windows launchers
│
├── core/                       # Business logic — no GUI imports
│   ├── ncbi_downloader.py          NCBI Entrez search & download
│   ├── blast_analyzer.py           GUI-facing BLAST wrapper
│   ├── blast_mismatch_analyzer.py  Query-anchored MSA & mismatch stats
│   ├── primer_designer.py          Cluster-pair design + Primer3 scoring
│   ├── primer_specificity.py       Primer-BLAST validation
│   └── report_generator.py         PDF / DOCX export
│
├── gui/                        # PySide6 interface
│   ├── main_window.py              Docks, toolbar, menu
│   ├── sequence_viewer.py          Mismatch heatmap & primer visualization
│   ├── workers.py                  BaseWorker QThread
│   ├── gui_context.py              Global state singleton
│   ├── i18n.py                     EN / RU string dictionary
│   ├── dialogs.py
│   ├── selection_dialog.py
│   ├── report_dialog.py
│   └── widgets.py
│
├── assets/                     # Logo, loading SVG, fonts
└── docs/                       # Markdown documentation
    ├── getting_started.md
    ├── user_manual.md
    ├── cli_reference.md
    ├── api_reference.md
    ├── architecture.md
    ├── output_format.md
    ├── troubleshooting.md
    ├── developers.md
    └── science.md
```

### Workspace Layout (runtime output)

```
{Workspace}/{Organism}/
├── Genes/{Gene}/{Gene}__{Accession}.fasta
├── BLAST/{Gene}/
│   ├── {hash}__mismatch_summary.xlsx
│   ├── {hash}__aligned_query_anchored.fasta
│   ├── {hash}__blast_JSON2.zip
│   ├── {Gene}_general_summary.xlsx
│   ├── {Gene}_cluster_meta.json
│   └── {Gene}_{method}_primers.json
├── Primer-BLAST/PrimerBLAST_{timestamp}.txt
├── Reports/report.pdf
└── {Organism}_loci.tsv
```

`{hash}` is a 24-character SHA-256 of the query sequence + BLAST parameters, enabling automatic result caching.

---

## System Requirements

| Component | Requirement |
|-----------|-------------|
| OS | Windows 10/11 · Ubuntu 20.04+ · macOS 11+ |
| Python | 3.12+ |
| RAM | 4 GB min, 8 GB recommended |
| Disk | 2 GB for installation + output |
| Internet | Required for NCBI downloads and BLAST |

Optional: NCBI API key (free, increases rate limits).

---

## References

- SantaLucia, J. (1998). A unified view of polymer, dumbbell, and oligonucleotide DNA nearest-neighbor thermodynamics. *PNAS*, 95(4), 1460–1465.
- Untergasser, A. et al. (2012). Primer3 — new capabilities and interfaces. *Nucleic Acids Research*, 40(15), e115.
- Ye, J. et al. (2012). Primer-BLAST: A tool to design target-specific primers for PCR. *BMC Bioinformatics*, 13, 134.
- NCBI. [BLAST Common URL API](https://blast.ncbi.nlm.nih.gov/doc/blast-help/urlapi.html).

---

## License

[MIT](LICENSE)

---

## See Also

[README_ru.md](README_ru.md) — Документация на русском языке
