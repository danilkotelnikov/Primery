# Getting Started with Primery

> **Quick Start Guide** - Get Primery up and running in minutes

---

## What is Primery?

**Primery** is a comprehensive bioinformatics application for designing **species-specific primers** for molecular diagnostics. The software automates the complete workflow from gene sequence retrieval to primer validation, featuring:

- 🧬 **NCBI Integration** - Automatic download of gene/locus sequences from NCBI Nucleotide database
- 🔍 **BLAST Mismatch Analysis** - Identify positions where non-target species differ from target
- 🎯 **Primer3 Design** - Intelligent primer design with clustering based on mismatch patterns
- ✅ **Primer-BLAST Validation** - Check primer specificity against NCBI databases
- 📊 **Visualization** - Built-in sequence viewer with mismatch tracks and JBrowse2 integration
- 📝 **Report Generation** - Professional HTML/PDF reports
- 🌐 **Bilingual Interface** - Full Russian/English localization

### Supported Amplification Methods

| Method | Description | Typical Use Case |
|--------|-------------|------------------|
| **PCR** | Standard polymerase chain reaction | General diagnostics |
| **qPCR** | Quantitative real-time PCR | Gene expression, viral load |
| **RPA** | Recombinase Polymerase Amplification | Field diagnostics, point-of-care |
| **LAMP** | Loop-mediated Isothermal Amplification | Rapid isothermal amplification |
| **NASBA** | Nucleic Acid Sequence-Based Amplification | RNA detection |

---

## System Requirements

### Minimum Requirements

| Component | Requirement |
|-----------|-------------|
| **Operating System** | Windows 10/11, Linux (Ubuntu 20.04+), macOS 11+ |
| **Python** | 3.12 or higher |
| **RAM** | 4 GB minimum, 8 GB recommended |
| **Disk Space** | 2 GB for installation + space for output data |
| **Internet** | Required for NCBI downloads and BLAST |

### Optional

- **NCBI API Key** - Increases request rate limits (free from NCBI)
- **GPU** - For hardware-accelerated visualization (QtWebEngine)

---

## Installation

### Method 1: Quick Install (Recommended)

The easiest way to install Primery is using the included launcher script that automatically sets up everything:

#### Windows

```batch
# Double-click run.bat or run from command line:
cd C:\path\to\Primery
run.bat
```

#### Linux/macOS

```bash
cd /path/to/Primery
chmod +x run.bat
./run.bat
```

**What the launcher does:**

1. ✅ Checks for Miniforge3 conda installation
2. ✅ Downloads and installs Miniforge3 if missing
3. ✅ Creates a `primery` conda environment with Python 3.12
4. ✅ Installs all dependencies from `requirements.txt`
5. ✅ Creates a desktop shortcut (Windows)
6. ✅ Launches the application

> **Note:** First run may take 5-10 minutes to download and install all dependencies.

---

### Method 2: Manual Installation

If you prefer to manage your own Python environment:

#### Step 1: Create Environment

```bash
# Using conda (recommended)
conda create -n primery python=3.12
conda activate primery

# Or using venv
python -m venv primery_env
# Windows:
primery_env\Scripts\activate
# Linux/macOS:
source primery_env/bin/activate
```

#### Step 2: Install Dependencies

```bash
cd C:\path\to\Primery
pip install -r requirements.txt
```

#### Step 3: Launch Application

```bash
python primery_app.py
```

---

### Method 3: Windows EXE Distribution

For Windows users, Primery can be distributed as a standalone executable:

```batch
# Build the executable (developers only)
pyinstaller primery.spec
```

The executable will be created in `dist/primery.exe` and can be run without Python installation.

---

## Dependencies

Primery requires the following Python packages (automatically installed):

```txt
PySide6>=6.0.0          # Qt6 GUI framework
biopython>=1.80         # Bioinformatics (NCBI access, sequence handling)
openpyxl>=3.0.0         # Excel file support
reportlab>=3.6.0        # PDF generation
python-docx>=0.8.11     # Word document support
requests>=2.28.0        # HTTP requests
primer3-py>=2.0.0       # Primer design engine
```

---

## First Run Setup

### 1. Launch the Application

After installation, launch Primery:

- **Windows:** Double-click the desktop shortcut or `run.bat`
- **Linux/macOS:** Run `./run.bat` from the Primery directory

You'll see a splash screen with the Primery logo. Click **Start** to begin.

### 2. Configure NCBI Credentials

NCBI requires an email address for API access:

1. Go to **Settings** → **NCBI Configuration**
2. Enter your email address (required)
3. (Optional) Enter your NCBI API key for higher rate limits

> **Getting an API Key:** Register at [https://www.ncbi.nlm.nih.gov/account/](https://www.ncbi.nlm.nih.gov/account/)

### 3. Set Up Workspace

Choose a working directory for your projects:

1. Click **File** → **Set Workspace**
2. Select or create a folder for your primer design projects
3. All output files will be saved here

---

## Quick Start Example: Designing Primers for *Fusarium culmorum*

This walkthrough shows the complete workflow for designing species-specific primers.

### Step 1: Download Loci

1. Click the **Download Loci** tab
2. Select **NCBI Organism** mode
3. Enter your email address
4. Type `Fusarium culmorum` in the organism query field
5. Click **Search NCBI**
6. Select the correct taxon from results (taxid: 5516)
7. Click **List Loci** to see available markers
8. Select loci of interest (e.g., TEF1, RPB2, ITS)
9. Set **Sequences per locus** (e.g., 10)
10. Click **Download Selected**

**Output:**
- `manifest.tsv` - Summary of downloaded sequences
- `Genes/{LOCUS}/*.fasta` - FASTA files for each locus

---

### Step 2: BLAST Mismatch Analysis

1. Switch to **Mismatch Analysis** tab
2. Select your `manifest.tsv` file
3. Enter target taxid (5516 for *F. culmorum*)
4. Set **Max hits** (e.g., 200)
5. Click **Run BLAST Mismatch Analysis**

**Output:**
- `BLAST/{LOCUS}/*_cluster_meta.json` - Cluster metadata
- `BLAST/{LOCUS}/*.xlsx` - Mismatch summary tables
- `BLAST/{LOCUS}/*_aligned_query_anchored.fasta` - Alignments

---

### Step 3: Primer3 Design

1. Go to **Primer Design** tab
2. Select template FASTA file
3. Load mismatch XLSX file
4. Choose preset (e.g., **qPCR**)
5. Configure parameters:
   - Min mismatch% in window: 50%
   - Top windows: 10
   - N pairs to return: 5
6. Click **Run Primer3**

**Output:**
- `primer3_pairs.json` - Designed primer pairs with Tm, hairpin, dimer analysis

---

### Step 4: Primer-BLAST Validation

1. Switch to **Primer-BLAST** tab
2. Enter forward and reverse primer sequences
3. Set target taxid (5516)
4. Choose database (`core_nt` recommended)
5. Set scope (e.g., **genus**)
6. Click **Run Primer-BLAST**

**Output:**
- Specificity report showing on-target vs off-target amplification
- CSV/TSV files with detailed results

---

### Step 5: View Results

1. Open **Viewer** tab
2. Load FASTA file
3. (Optional) Load `mismatch_map.json` for mismatch visualization
4. (Optional) Load `primer3_pairs.json` to see primer positions
5. Use **JBrowse2** for interactive genome-style view

---

### Step 6: Generate Report

1. Go to **Reports** tab
2. Click **Build HTML+PDF Report**
3. Select output directory
4. Review generated report

---

## Project Structure

After running the workflow, your workspace will look like:

```
workspace/
├── manifest.tsv                    # Download manifest
├── Genes/
│   ├── TEF1/
│   │   ├── TEF1__KU171719.fasta
│   │   └── ...
│   └── ...
├── BLAST/
│   ├── TEF1/
│   │   ├── TEF1_cluster_meta.json
│   │   ├── TEF1_pcr_primers.json
│   │   ├── TEF1_mismatch_summary.xlsx
│   │   └── ...
│   └── ...
└── reports/
    ├── report.html
    └── report.pdf
```

---

## Next Steps

- 📖 Read the [[user_manual]] for detailed GUI documentation
- 🔧 Check [[cli_reference]] for command-line usage
- 🐛 Having issues? See [[troubleshooting]]
- 🧬 Learn the science behind [[science]]

---

## Support

- **Documentation:** This documentation folder
- **Issues:** Report bugs and feature requests
- **NCBI Help:** [https://www.ncbi.nlm.nih.gov/books/NBK25501/](https://www.ncbi.nlm.nih.gov/books/NBK25501/)

---

*Last updated: March 2026*
