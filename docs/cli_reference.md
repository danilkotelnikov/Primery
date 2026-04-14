# CLI Reference

> Command-line scripts for batch processing without the GUI

---

All CLI scripts are located in the `_legacy/` directory. They provide the same core functionality as the GUI but are designed for terminal-based workflows and automation.

---

## blast_mismatch_analyzer.py

The primary standalone CLI tool for BLAST mismatch analysis. Located at `core/blast_mismatch_analyzer.py` with a `main()` entry point.

```
python -m core.blast_mismatch_analyzer [OPTIONS]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--email` | Yes | — | Contact email for NCBI (used in User-Agent header) |
| `--outdir` | Yes | — | Output directory (results placed under `outdir/blast_analysis/`) |
| `--target-sciname` | No | `Fusarium culmorum` | Target species scientific name (hits matching this are excluded from mismatch tallying) |
| `--target-taxid` | No | `None` | Target NCBI Taxonomy ID (alternative exclusion criterion) |
| `--query-fasta` | No* | — | Single query FASTA file to analyze |
| `--manifest` | No* | — | Path to `manifest.tsv` (from download scripts) |
| `--analyze-from-manifest` | No | `False` | Analyze all loci from the manifest (one query per species×locus) |
| `--max-hits` | No | `200` | BLAST HITLIST_SIZE and max hits used in analysis |
| `--expect` | No | `10.0` | BLAST E-value threshold |
| `--no-megablast` | No | `False` | Disable megablast (use standard blastn) |
| `--min-cov` | No | `0.5` | Minimum query coverage fraction to retain a hit |
| `--force` | No | `False` | Re-run even if `.done.json` exists |

*Either `--query-fasta` or `--analyze-from-manifest` (with `--manifest`) is required.

### Examples

Analyze a single sequence:

```bash
python -m core.blast_mismatch_analyzer \
    --email you@lab.org \
    --target-sciname "Fusarium culmorum" \
    --query-fasta Fusarium_culmorum/Genes/TEF1/TEF1__OK123456.fasta \
    --outdir analysis_out
```

Analyze all loci from a manifest:

```bash
python -m core.blast_mismatch_analyzer \
    --email you@lab.org \
    --manifest Fusarium_culmorum/Fusarium_culmorum_loci.tsv \
    --outdir workspace \
    --analyze-from-manifest \
    --max-hits 200
```

---

## fusarium_pipeline.py

*Location: `_legacy/fusarium_pipeline.py`*

Unified pipeline script with subcommands for the complete workflow.

```
python _legacy/fusarium_pipeline.py <subcommand> [OPTIONS]
```

### Subcommands

| Subcommand | Description |
|------------|-------------|
| `all` | Run the complete pipeline (download → analyze → design → report) |
| `download` | Download loci from NCBI |
| `analyze` | Run BLAST mismatch analysis |
| `design` | Run Primer3 design |
| `primerblast` | Run Primer-BLAST specificity check |
| `report` | Generate report |
| `gui` | Launch the GUI application |

---

## download_fusarium_loci.py

*Location: `_legacy/download_fusarium_loci.py`*

Downloads reference sequences for Fusarium species from NCBI.

```
python _legacy/download_fusarium_loci.py [OPTIONS]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--email` | Yes | — | NCBI contact email |
| `--panel` | No | `all` | Loci panel: `mlst`, `rdna`, `mito`, `diagnostic`, `toxin`, or `all` |
| `--n-per-locus` | No | `10` | Number of sequences to download per locus |
| `--outdir` | No | `fusarium_fasta` | Output directory |
| `--zip` | No | `False` | Create a ZIP archive of downloaded files |
| `--api-key` | No | `None` | NCBI API key for higher rate limits |

### Example

```bash
python _legacy/download_fusarium_loci.py \
    --email you@lab.org \
    --panel mlst \
    --n-per-locus 15 \
    --outdir workspace
```

---

## ncbi_loci_interactive.py

*Location: `_legacy/ncbi_loci_interactive.py`*

Interactive CLI for downloading loci from any organism (not Fusarium-specific).

```
python _legacy/ncbi_loci_interactive.py [OPTIONS]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--email` | Yes | — | NCBI contact email |
| `--outdir` | No | `ncbi_loci` | Output directory |
| `--n-per-locus` | No | `10` | Number of sequences per locus |

The script prompts interactively for organism name and locus selection.

---

## primer3_designer.py

*Location: `_legacy/primer3_designer.py`*

Standalone Primer3 design script using mismatch-aware window placement.

```
python _legacy/primer3_designer.py [OPTIONS]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--template-fasta` | Yes | — | Template FASTA sequence file |
| `--mismatch-xlsx` | Yes | — | Mismatch summary XLSX from BLAST analysis |
| `--preset` | No | `pcr` | Amplification preset: `pcr`, `qpcr`, `rpa`, `nasba`, `lamp` |
| `--outdir` | No | `primer_output` | Output directory |

### Example

```bash
python _legacy/primer3_designer.py \
    --template-fasta workspace/Fusarium/Genes/TEF1/TEF1__OK123456.fasta \
    --mismatch-xlsx workspace/Fusarium/BLAST/TEF1/TEF1_mismatch_summary.xlsx \
    --preset qpcr \
    --outdir primer_results
```

---

## primerblast_interactive.py

*Location: `_legacy/primerblast_interactive.py`*

Interactive Primer-BLAST specificity check. Requires `beautifulsoup4`.

```
python _legacy/primerblast_interactive.py [OPTIONS]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--email` | Yes | — | NCBI contact email |
| `--outdir` | No | `primerblast_output` | Output directory |

---

## report_builder.py

*Location: `_legacy/report_builder.py`*

Generates HTML and PDF reports from workspace analysis results.

```
python _legacy/report_builder.py [OPTIONS]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--workdir` | Yes | — | Workspace directory containing analysis results |
| `--outdir` | No | `reports` | Output directory for generated reports |

---

## Exit Codes

All scripts return `0` on success and non-zero on failure. Errors are printed to stderr with ANSI color coding (INFO=blue, OK=green, WARN=yellow, ERROR=red).
