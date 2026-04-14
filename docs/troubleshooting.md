# Troubleshooting

> Common issues and their solutions

---

## NCBI Rate Limits

**Problem:** Requests to NCBI are slow or return HTTP 429 errors.

**Cause:** NCBI enforces rate limits: 3 requests/second without an API key, 10 requests/second with one. Primery uses `time.sleep(0.34)` between Entrez requests.

**Solution:**
1. Get a free API key at [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/)
2. Enter it in the **API Key** field in the toolbar
3. The key is passed to `Entrez.api_key`, increasing the rate limit to 10 req/s

---

## BLAST Timeouts

**Problem:** BLAST analysis hangs or times out after 30 minutes.

**Cause:** The default `max_wait_s=1800` (30 minutes) may not be enough for large databases or complex queries. BLAST polling occurs at 5-second intervals.

**Solution:**
- For CLI usage, the timeout is hardcoded. Consider running during off-peak hours.
- The BLAST endpoint returns status `WAITING` while processing. If it returns `UNKNOWN`, the code retries. If it returns `FAILED`, a `RuntimeError` is raised.
- Using `core_nt` (curated database) instead of full `nt` significantly reduces wait times.

---

## BLAST FAILED or UNKNOWN Status

**Problem:** BLAST returns `Status=FAILED` or `Status=UNKNOWN`.

**Cause:**
- `FAILED`: The BLAST job encountered a server-side error. This raises a `RuntimeError` with the response text.
- `UNKNOWN`: Temporary status — the RID may not be recognized yet. The code retries after `poll_interval` seconds.

**Solution:**
- Check the error message in the log dock for details
- Re-submit the analysis (it will get a new RID)
- If persistent, verify your query sequence is valid (no empty sequences, reasonable length)

---

## Primer3 Returns No Results

**Problem:** The "Design Primers" step produces zero primer pairs.

**Possible causes:**
1. No valid cluster pairs exist within the product size range
2. The template sequence is too short for the selected preset
3. No conservative mismatch positions were found

**Solutions:**
- Check `{Gene}_cluster_meta.json` — if the `clusters` array is empty, no mismatch clusters were identified
- Try a different preset with a wider product size range (e.g., PCR: 100–500 bp)
- Use a longer reference sequence (the longest FASTA per gene is used as template)
- If no valid cluster pairs are found, Primer3 falls back to unclustered design (`_design_unclustered()`), but results will have `fwd_cluster_id=0` and `score=0`
- Open **Advanced Settings** and adjust primer size, Tm, or product range

---

## GUI Freezes

**Problem:** The application becomes unresponsive during analysis.

**Cause:** Normally impossible — all NCBI, BLAST, Primer3, and report operations run in `BaseWorker(QThread)` threads. A freeze indicates an operation running on the main thread.

**Solution:**
1. Check the **Log** dock for error messages or stack traces
2. Worker errors are caught and emitted via `error_occurred` signal — look for traceback output
3. If the GUI is completely frozen, it may be a Qt rendering issue (see Windows-specific section below)
4. Restart the application

---

## Conda Environment Issues

**Problem:** The application fails to start from `run.bat`.

**Cause:** The launcher script (`run.bat`) auto-installs Miniforge and creates a `primery` Conda environment with Python 3.12.

**Solutions:**
- **Fresh start:** Run `clean_install.bat` to remove the embedded Python environment, then rerun `run.bat`
- **Debug mode:** Run `debug.bat` for verbose output showing exactly where startup fails
- **Manual setup:** Create the environment yourself:

```bash
conda create -n primery python=3.12 -y
conda activate primery
pip install -r requirements.txt
python primery_app.py
```

---

## Import Errors

**Problem:** `ModuleNotFoundError` for PySide6, biopython, primer3-py, etc.

**Cause:** Dependencies are not installed in the active Python environment. The `python_embed/` directory contains bundled packages for Windows distribution, but may not cover all cases.

**Solution:**
1. Activate your Conda environment: `conda activate primery`
2. Install all dependencies: `pip install -r requirements.txt`
3. If using the embedded Python (`python_embed/`), ensure `python_embed/Lib/site-packages` is on `sys.path` (the code appends it automatically)

---

## Windows-Specific Issues

### Qt OpenGL Problems

**Problem:** Black screens, rendering artifacts, or crashes related to OpenGL on Windows.

**Solution:** Set the Qt OpenGL rendering backend before launching:

```cmd
set QT_OPENGL=angle
python primery_app.py
```

Or try `QT_OPENGL=desktop` if `angle` doesn't work.

### Explorer Integration

**Problem:** "Open in Explorer" doesn't work.

**Cause:** Primery uses `subprocess.Popen(['explorer', path])` to open folders. This may fail if the path contains special characters.

**Solution:** Verify the workspace path doesn't contain characters that CMD cannot handle. Unicode paths (like Cyrillic) generally work on modern Windows.

---

## Empty Search Results

**Problem:** "Search Genes" returns no results.

**Possible causes:**
1. Organism name is misspelled
2. No sequences in the 200–10,000 bp range exist for that organism
3. NCBI query syntax issue

**Solutions:**
- Try the genus name only (e.g., `Fusarium` instead of `Fusarium culmorum`)
- Check the organism name against [NCBI Taxonomy](https://www.ncbi.nlm.nih.gov/taxonomy)
- The search query excludes whole genome shotguns and genome assemblies — if the organism only has genome data, no results will appear
- The sequence length filter (200–10,000 bp) excludes very short or very long sequences

---

## QC Failures

**Problem:** Downloaded sequences are marked as `verified=NO` and skipped.

**Cause:** The `strict_qc` option checks GenBank records for specific keywords in the `/gene=` and `/product=` annotations. Records without these annotations fail QC.

**Solutions:**
- Use `keep_unverified=True` to save sequences that fail QC (they are still downloaded but flagged)
- In non-strict mode (`strict_qc=False`), the entire GenBank text is searched, which is more permissive
- Check the `qc_note` column in the manifest for the specific failure reason (e.g., `failed_qc` means no verify terms matched)

---

## Large Workspace Performance

**Problem:** The Files dock is slow to load with many files.

**Cause:** `QFileSystemModel` monitors the entire workspace directory tree.

**Solution:**
- Keep workspaces focused — avoid placing large non-project directories inside the workspace
- The `python_embed/` directory contains thousands of files; consider placing it outside the workspace

---

## Report Generation Failures

**Problem:** PDF or DOCX report generation fails.

**Possible causes:**
1. Missing `reportlab` or `python-docx` packages
2. Google Sans font not installed (PDF falls back to Helvetica automatically)
3. No analysis data found for the selected organism/gene

**Solutions:**
- Ensure `pip install reportlab python-docx` succeeds
- Check that `{Gene}_cluster_meta.json` and `{Gene}_*_primers.json` exist in the BLAST directory
- Font fallback is automatic — Helvetica is used if Google Sans is not available
- Check the Log dock for specific error messages
