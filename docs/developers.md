# Developer Guide

> Setting up a development environment and extending Primery

---

## Development Environment Setup

### Prerequisites

- Python 3.12 (via Miniforge/Conda recommended)
- Git

### Setup Steps

```bash
# Create a dedicated environment
conda create -n primery-dev python=3.12 -y
conda activate primery-dev

# Install dependencies
pip install -r requirements.txt

# Launch the application
python primery_app.py
```

### Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| PySide6 | ≥ 6.0.0 | Qt GUI framework |
| biopython | ≥ 1.80 | NCBI Entrez, SeqIO, BLAST XML parsing |
| primer3-py | ≥ 2.0.0 | Primer3 thermodynamic engine |
| openpyxl | ≥ 3.0.0 | Excel spreadsheet I/O |
| reportlab | ≥ 3.6.0 | PDF generation |
| python-docx | ≥ 0.8.11 | DOCX generation |
| requests | ≥ 2.28.0 | HTTP client for BLAST API |

---

## Project Layout

The codebase follows a strict separation between business logic and UI:

```
core/           Business logic — zero GUI imports
  ├── ncbi_downloader.py      Entrez search + download
  ├── blast_analyzer.py       High-level BLAST wrapper
  ├── blast_mismatch_analyzer.py   Low-level BLAST + mismatch engine
  ├── primer_designer.py      Primer3 cluster-pair design
  ├── primer_specificity.py   Primer-BLAST specificity check
  └── report_generator.py     PDF/DOCX report output

gui/            PySide6 interface
  ├── main_window.py          MainWindow with docks, toolbar, menu
  ├── sequence_viewer.py      QGraphicsView sequence viewer
  ├── workers.py              BaseWorker QThread
  ├── gui_context.py          Global state (singleton)
  ├── i18n.py                 EN/RU translations
  ├── dialogs.py              Settings dialogs
  ├── selection_dialog.py     Organism/gene picker
  ├── report_dialog.py        Report options
  └── widgets.py              Reusable small widgets
```

**Key principle:** `core/` modules can be used independently (CLI, scripts, tests) without importing anything from `gui/`. The `gui/` layer calls `core/` through `BaseWorker` threads.

---

## Code Conventions

- **Language:** Python 3.12
- **Type hints:** Used in all public method signatures
- **String formatting:** f-strings preferred
- **Imports:** Standard library first, then third-party, then local modules
- **Error handling:** Workers catch all exceptions and emit `error_occurred` signals; tracebacks are printed via `traceback.print_exc()`
- **File encoding:** UTF-8 everywhere, with `errors="ignore"` or `errors="replace"` where external data is read
- **Naming:** snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants

---

## Adding New Amplification Presets

To add a new amplification method (e.g., HDA — helicase-dependent amplification):

### 1. Add to METHOD_PARAMS

In `core/primer_designer.py`:

```python
METHOD_PARAMS = {
    # ... existing presets ...
    "hda": {
        "min_size": 20, "opt_size": 24, "max_size": 28,
        "product": [80, 120],
        "min_tm": 60.0, "opt_tm": 64.0, "max_tm": 68.0
    },
}
```

### 2. Add to GUI dropdown

In `gui/main_window.py`, find the `combo_preset` creation and add the new entry:

```python
self.combo_preset.addItems(["PCR", "qPCR", "RPA", "NASBA", "LAMP Outer", "HDA"])
```

### 3. Add translations (optional)

In `gui/i18n.py`, add tooltip text for both languages:

```python
'en': {
    'tooltip_hda': 'Helicase-dependent amplification: isothermal, 60-65°C, 80-120bp amplicons.',
}
'ru': {
    'tooltip_hda': 'Хеликаза-зависимая амплификация: изотермальная, 60-65°C, ампликоны 80-120 п.о.',
}
```

---

## Adding New Loci Panels

The `loci_config` format used by `NCBIDownloader.fetch_loci()`:

```python
loci_config = {
    "locus_key": {
        "search_terms": ["term1", "term2"],  # ORed in Entrez query
        "verify_terms": ["verify1", "verify2"]  # Checked in GenBank annotations
    }
}
```

**Example:** Adding a new Fusarium panel for trichothecene biosynthesis genes:

```python
trichothecene_panel = {
    "TRI5": {
        "search_terms": ["trichodiene synthase", "TRI5", "Tri5"],
        "verify_terms": ["trichodiene", "tri5"]
    },
    "TRI6": {
        "search_terms": ["TRI6", "transcription factor"],
        "verify_terms": ["tri6"]
    }
}
```

Pass this to `fetch_loci()` as the `loci_config` parameter.

---

## Adding Translations

The i18n system uses a flat dictionary in `gui/i18n.py`:

### 1. Add the key to both language dicts

```python
STRINGS = {
    'en': {
        # ... existing keys ...
        'my_new_feature': 'My New Feature',
    },
    'ru': {
        # ... existing keys ...
        'my_new_feature': 'Моя новая функция',
    },
}
```

### 2. Use in GUI code

```python
from gui.i18n import tr
from gui.gui_context import context

label.setText(tr(context.lang, 'my_new_feature'))
```

### Rules

- Every key must exist in both `'en'` and `'ru'` dicts
- If a key is missing, `tr()` returns the key string itself as a fallback
- Use descriptive, snake_case key names
- Tooltip keys conventionally start with `tooltip_`

---

## Building a Windows Executable

A legacy PyInstaller spec exists at `_legacy/pyinstaller.spec`. It targets `gui_app.py` (the old entry point).

To build with the current entry point:

```bash
pip install pyinstaller

pyinstaller --name Primery \
    --windowed \
    --icon assets/Logo.ico \
    --add-data "assets;assets" \
    --add-data "gui;gui" \
    --add-data "core;core" \
    primery_app.py
```

**Note:** The bundled `python_embed/` directory is an alternative distribution mechanism for Windows that avoids PyInstaller — it ships an embedded Python interpreter with pre-installed packages.

---

## Testing

Primery does not currently have an automated test suite. A recommended testing approach:

### Unit Tests

Create a `tests/` directory with test files mirroring the source structure:

```
tests/
├── test_ncbi_downloader.py     # Mock Entrez calls
├── test_blast_analyzer.py      # Test clustering, scoring
├── test_primer_designer.py     # Test METHOD_PARAMS, scoring formula
├── test_blast_mismatch.py      # Test tally_mismatches, build_query_anchored_seq
└── test_report_generator.py    # Test data collection, output format
```

**Suggested framework:** `pytest` with `unittest.mock` for NCBI API calls.

**Key areas to test:**
- `_cluster_positions()` — clustering logic with known position sets
- `_rank_clusters()` — scoring formula correctness
- `_extract_pair()` — scoring formula: species coverage, mismatch overlap, 3' bonus, thermal penalty
- `build_query_anchored_seq()` — alignment logic with known HSP data
- `tally_mismatches()` — correct exclusion of target species
- `_verify_qc()` — GenBank text parsing

### Integration Tests

- Download a small set of known sequences and verify manifest content
- Run a mock BLAST analysis with pre-recorded JSON2 ZIP files
- Design primers from known cluster data and verify output format

### GUI Tests

- Use `pytest-qt` for testing PySide6 widgets
- Test `SequenceViewer` rendering with known sequence + annotation data
- Test dialog input/output

---

## Debugging

### debug.bat

The `debug.bat` launcher runs `primery_app.py` with the bundled or system Python, with output visible in the console window (not backgrounded like `run.bat`'s `pythonw`).

### Log Dock

`StreamRedirector` captures `sys.stdout` and `sys.stderr`:

```python
class StreamRedirector(QObject):
    message = Signal(str)
```

All `print()` statements in `core/` modules appear in the Log dock. Worker exceptions trigger `traceback.print_exc()` which also appears in the log.

### Worker Errors

`BaseWorker` catches all exceptions in `run()`:

```python
def run(self):
    try:
        res = self.func(*self.args, **self.kwargs)
        self.finished_result.emit(res)
    except Exception as e:
        traceback.print_exc()
        self.error_occurred.emit(str(e))
```

Connect to `error_occurred` to see error messages in the GUI.

---

## Contributing

### Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes following the code conventions above
4. Test your changes manually (run the GUI, verify output files)
5. Submit a pull request with a clear description of changes

### Code Review Checklist

- [ ] `core/` modules have no GUI imports
- [ ] All new public methods have type hints
- [ ] New UI strings are added to both `'en'` and `'ru'` dicts in `i18n.py`
- [ ] New presets are added to `METHOD_PARAMS` and the GUI dropdown
- [ ] Output files follow the directory contract in `architecture.md`
- [ ] Error handling uses worker pattern (no blocking calls on main thread)
