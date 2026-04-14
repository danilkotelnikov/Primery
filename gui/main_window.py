"""
main_window.py

The main GUI window for Primery.
Uses a Dock-based layout for an IDE-like experience.
"""

import os
import sys
import shutil
import subprocess
import glob
import json
from functools import partial
from datetime import datetime

from PySide6.QtWidgets import (QMainWindow, QDockWidget, QWidget, QVBoxLayout,
                               QFileSystemModel, QTreeView, QPlainTextEdit,
                               QToolBar, QLabel, QLineEdit, QPushButton, QComboBox,
                               QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                               QGroupBox, QFormLayout, QInputDialog, QMenu, QToolButton,
                               QFileDialog, QTabWidget, QTabBar)
from PySide6.QtCore import Qt, QSize, QObject, Signal
from PySide6.QtGui import QIcon, QAction

from gui.sequence_viewer import SequenceViewer
from gui.i18n import tr
from gui.gui_context import context
# Import core logical components
from core.ncbi_downloader import NCBIDownloader
from core.blast_analyzer import BlastAnalyzer
# We will use threading (QThread) for long running tasks, similar to old gui_app.py but cleaner

class StreamRedirector(QObject):
    """Redirects stream output to a Qt signal."""
    message = Signal(str)
    
    def __init__(self, stream=None):
        super().__init__()
        self.stream = stream

    def write(self, text):
        self.message.emit(str(text))
        if self.stream:
            self.stream.write(text) # Also write to original stream

    def flush(self):
        if self.stream:
            self.stream.flush()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Primery") # Simplified title
        
        # Setup Log Redirection
        self.stdout_redirector = StreamRedirector(sys.stdout)
        self.stderr_redirector = StreamRedirector(sys.stderr)
        self.stdout_redirector.message.connect(self.log_message)
        self.stderr_redirector.message.connect(self.log_message)
        sys.stdout = self.stdout_redirector
        sys.stderr = self.stderr_redirector
        
        self.resize(1200, 800)
        
        # Initialize Core Context
        self.downloader = NCBIDownloader("user@example.com") # User should set this
        
        # --- Central Widget: Tabs for Sequence Viewers ---
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close)
        self.setCentralWidget(self.tabs)
        

        
        # Initial empty tab (optional, or just start empty)
        # --- Docks ---
        self._create_file_dock()
        self._create_ncbi_dock()
        self._create_properties_dock() # For logic params (Mismatch/Primer3)
        self._create_log_dock()
        
        # --- Menu ---
        self._create_menu()
        
        # --- Toolbar ---
        self._create_toolbar()
        
        # --- Logic State ---
        self.current_seq = None
        
        # Status
        self.statusBar().showMessage("Ready")
        
        # Initial empty tab (optional, or just start empty)
        self.add_viewer_tab("Start") 

    @property
    def current_viewer(self):
        """Return the currently active SequenceViewer, or None."""
        w = self.tabs.currentWidget()
        if isinstance(w, SequenceViewer):
            return w
        return None

    def add_viewer_tab(self, gene_name, switch_to=True):
        """Create a new tab for a gene (or focus existing)."""
        # Check if exists
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == gene_name:
                if switch_to:
                    self.tabs.setCurrentIndex(i)
                return self.tabs.widget(i)
        
        # Create new
        sv = SequenceViewer()
        if hasattr(self, 'combo_font'):
            sv.set_font(self.combo_font.currentText())
        if hasattr(self, 'combo_scheme'):
            sv.set_color_scheme(self.combo_scheme.currentText())
        
        idx = self.tabs.addTab(sv, gene_name)
        if switch_to:
            self.tabs.setCurrentIndex(idx)
        return sv

    def _on_tab_close(self, index):
        self.tabs.removeTab(index)

    def _create_file_dock(self):
        self.dock_files = QDockWidget("Files", self)
        self.dock_files.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(os.getcwd())
        
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(os.getcwd()))
        self.tree.hideColumn(1)
        self.tree.hideColumn(2)
        self.tree.setColumnWidth(0, 200)
        self.tree.doubleClicked.connect(self.on_file_double_click)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._file_tree_context_menu)
        
        self.dock_files.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_files)

    # --- File Manager Context Menu ---
    def _file_tree_context_menu(self, pos):
        index = self.tree.indexAt(pos)
        menu = QMenu(self)

        if index.isValid():
            path = self.fs_model.filePath(index)
            is_dir = self.fs_model.isDir(index)

            ac_rename = QAction("Rename", self)
            ac_rename.triggered.connect(lambda: self._fm_rename(path))
            menu.addAction(ac_rename)

            ac_delete = QAction("Delete", self)
            ac_delete.triggered.connect(lambda: self._fm_delete(path, is_dir))
            menu.addAction(ac_delete)

            menu.addSeparator()

        # Always available: new folder
        ac_newfolder = QAction("New Folder", self)
        ac_newfolder.triggered.connect(lambda: self._fm_new_folder(index))
        menu.addAction(ac_newfolder)

        if index.isValid():
            menu.addSeparator()
            ac_explorer = QAction("Open in Explorer", self)
            ac_explorer.triggered.connect(lambda: self._fm_open_explorer(
                self.fs_model.filePath(index)))
            menu.addAction(ac_explorer)

        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def _fm_rename(self, path):
        old_name = os.path.basename(path)
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(path), new_name)
            try:
                os.rename(path, new_path)
                self.log_message(f"Renamed: {old_name} → {new_name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Rename failed: {e}")

    def _fm_delete(self, path, is_dir):
        name = os.path.basename(path)
        kind = "folder" if is_dir else "file"
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {kind} '{name}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                if is_dir:
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.log_message(f"Deleted: {name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Delete failed: {e}")

    def _fm_new_folder(self, index):
        if index.isValid() and self.fs_model.isDir(index):
            parent_dir = self.fs_model.filePath(index)
        elif index.isValid():
            parent_dir = os.path.dirname(self.fs_model.filePath(index))
        else:
            parent_dir = self.le_ws.text() or os.getcwd()
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            new_path = os.path.join(parent_dir, name)
            try:
                os.makedirs(new_path, exist_ok=True)
                self.log_message(f"Created folder: {name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Create failed: {e}")

    def _fm_open_explorer(self, path):
        target = path if os.path.isdir(path) else os.path.dirname(path)
        try:
            subprocess.Popen(['explorer', target])
        except Exception as e:
            self.log_message(f"Could not open explorer: {e}")

    def _create_ncbi_dock(self):
        self.dock_ncbi = QDockWidget("NCBI Tools", self)
        self.dock_ncbi.setAllowedAreas(Qt.RightDockWidgetArea)
        
        w = QWidget()
        layout = QVBoxLayout(w)
        
        # Search Box
        form = QFormLayout()
        self.le_organism = QLineEdit()
        self.le_organism.setPlaceholderText("e.g. Fusarium graminearum")
        form.addRow("Organism:", self.le_organism)
        
        layout.addLayout(form)
        
        # Buttons
        self.btn_search = QPushButton("Search Genes")
        self.btn_search.clicked.connect(self.on_search_loci)
        layout.addWidget(self.btn_search)
        
        # Results Table
        self.table_loci = QTableWidget(0, 3)
        self.table_loci.setHorizontalHeaderLabels(["Name", "Count", "Examples"])
        self.table_loci.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_loci)
        
        # Action Buttons
        self.btn_download = QPushButton("Download Selected")
        self.btn_download.clicked.connect(self.on_download_loci)
        layout.addWidget(self.btn_download)
        
        self.dock_ncbi.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_ncbi)

    def _create_properties_dock(self):
        self.dock_props = QDockWidget("Analysis & Design", self)
        self.dock_props.setAllowedAreas(Qt.RightDockWidgetArea)

        w = QWidget()
        layout = QVBoxLayout(w)

        # Mismatch Settings
        grp_mm = QGroupBox("Blast Mismatch")
        l_mm = QFormLayout(grp_mm)

        self.combo_db = QComboBox()
        self.combo_db.addItems(["nt", "refseq_rna", "core_nt"])
        l_mm.addRow("Database:", self.combo_db)

        self.combo_limit = QComboBox()
        self.combo_limit.addItems(["None", "Genus", "Species"])
        l_mm.addRow("Limit By:", self.combo_limit)

        self.btn_mm_view = QPushButton("Open Mismatch Viewer")
        self.btn_mm_view.clicked.connect(self.open_mismatch_viewer)
        l_mm.addRow(self.btn_mm_view)

        self.btn_run_blast = QPushButton("Analyze Specificity")
        self.btn_run_blast.clicked.connect(self.on_run_blast)
        l_mm.addRow(self.btn_run_blast)
        layout.addWidget(grp_mm)

        # Primer3 Settings
        grp_p3 = QGroupBox("Primer Design")
        l_p3 = QFormLayout(grp_p3)
        self.combo_preset = QComboBox()
        self.combo_preset.addItems(["PCR (Generic)", "qPCR", "RPA", "NASBA", "LAMP (Outer)"])
        self.combo_preset.currentTextChanged.connect(self._on_preset_changed)
        l_p3.addRow("Preset:", self.combo_preset)

        self.btn_adv_settings = QPushButton("Advanced Settings")
        self.btn_adv_settings.clicked.connect(self.open_primer_settings)
        l_p3.addRow(self.btn_adv_settings)

        self.btn_design = QPushButton("Design Primers")
        self.btn_design.clicked.connect(self.on_design_primers)
        l_p3.addRow(self.btn_design)
        layout.addWidget(grp_p3)
        
        # --- Specificity (Primer-BLAST) ---
        grp_spec = QGroupBox("Primer Specificity")
        l_spec = QFormLayout(grp_spec)
        
        self.combo_spec_db = QComboBox()
        self.combo_spec_db.addItems([
            "nt",
            "refseq_rna",
            "refseq_representative_genomes",
            "prokaryotic_refseq_genomes"
        ])
        l_spec.addRow("Database:", self.combo_spec_db)
        
        self.le_entrez = QLineEdit()
        self.le_entrez.setPlaceholderText("e.g. fungi[organism]")
        l_spec.addRow("Entrez Query:", self.le_entrez)
        
        self.le_spec_target = QLineEdit()
        self.le_spec_target.setPlaceholderText("e.g. Fusarium nanum")
        l_spec.addRow("Target Organism:", self.le_spec_target)
        
        self.btn_load_primers_spec = QPushButton("Load Primers File")
        self.btn_load_primers_spec.clicked.connect(self.load_primers_for_specificity)
        l_spec.addRow(self.btn_load_primers_spec)
        
        self.btn_run_spec = QPushButton("Run Specificity Check")
        self.btn_run_spec.clicked.connect(self.on_run_specificity)
        l_spec.addRow(self.btn_run_spec)
        
        layout.addWidget(grp_spec)
        
        layout.addStretch()
        self.dock_props.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_props)

        # Default: sync with first preset
        self.custom_primer_settings = None
        self.max_primer_pairs = 10
        self.n_cluster_pairs = 20
        self.specificity_settings = {
            "database": "nt",
            "entrez_query": "",
            "target_organism": "",
        }

    def open_mismatch_viewer(self):
        from gui.dialogs import MismatchDialog
        dlg = MismatchDialog(self)
        dlg.exec()

    def _get_selected_preset_params(self):
        from core.primer_designer import METHOD_PARAMS
        key = self.combo_preset.currentText().split(" ")[0].lower()
        return METHOD_PARAMS.get(key, METHOD_PARAMS["pcr"])

    def _on_preset_changed(self, text):
        # Clear custom settings so the preset takes effect
        self.custom_primer_settings = None
        mode_key = text.split(" ")[0].lower()
        self.log_message(f"Preset changed to: {text} ({mode_key})")

    def open_primer_settings(self):
        from gui.dialogs import PrimerSettingsDialog
        preset_params = self._get_selected_preset_params()
        dlg = PrimerSettingsDialog(
            current_settings=getattr(self, 'custom_primer_settings', None),
            preset_params=preset_params,
            parent=self,
        )
        # Sync dialog specificity tab with dock fields
        dlg.le_target_org.setText(self.le_spec_target.text() or self.le_organism.text().strip())
        dlg.le_entrez_spec.setText(self.le_entrez.text())
        # Sync DB combo
        dock_db = self.combo_spec_db.currentText()
        idx = dlg.combo_spec_db.findText(dock_db, Qt.MatchStartsWith)
        if idx >= 0:
            dlg.combo_spec_db.setCurrentIndex(idx)
        if dlg.exec():
            self.custom_primer_settings = dlg.get_settings()
            self.max_primer_pairs = dlg.get_max_pairs()
            self.n_cluster_pairs = dlg.get_cluster_pairs_limit()
            # Sync specificity back to dock
            spec = dlg.get_specificity_settings()
            self.le_entrez.setText(spec.get('entrez_query', ''))
            self.le_spec_target.setText(spec.get('target_organism', ''))
            # Sync DB back
            db_idx = self.combo_spec_db.findText(spec.get('database', 'nt'))
            if db_idx >= 0:
                self.combo_spec_db.setCurrentIndex(db_idx)
            self.log_message(
                f"Custom primer settings applied. "
                f"Max pairs: {self.max_primer_pairs}, "
                f"Cluster pairs: {self.n_cluster_pairs}")
            
    # --- Analysis & Design ---
    def on_run_blast(self):
        ws = self.le_ws.text()
        if not ws:
             self.log_message("Please select a workspace first.")
             return

        target_org = self.le_organism.text()
        if not target_org:
            self.log_message("Please enter Target Organism name to ensure correct paths.")
            return

        # Find files in {ws}/{safe_org}/Genes/
        safe_org = target_org.replace(" ", "_")
        genes_root = os.path.join(ws, safe_org, "Genes")
        
        fasta_files = []
        if os.path.exists(genes_root):
             for root, dirs, files in os.walk(genes_root):
                for f in files:
                    if f.endswith(".fasta"):
                        fasta_files.append(os.path.join(root, f))
        
        if not fasta_files:
            self.log_message(f"No FASTA files found in {genes_root}")
            return

        # Params
        db = self.combo_db.currentText()
        
        self.log_message(f"Starting BLAST analysis ({db}) for {len(fasta_files)} files...")
        self.btn_run_blast.setEnabled(False)
        
        analyzer = BlastAnalyzer(context.email or "user@example.com", context.api_key)
        
        def run_analysis():
            return analyzer.run_analysis(
                fasta_files, target_org, 0, ws,
                max_hits=200, megablast=True, db=db, force=False,
            )
            
        def on_blast_done(results):
            self.log_message(f"Analysis complete. Processed {len(results)} files.")
            self.btn_run_blast.setEnabled(True)
            self.log_message(f"Results saved in {ws}/{safe_org}/BLAST/")
            # Auto-map: load reference and top-10 clusters
            self.map_mismatches_and_clusters()

        self.run_worker(run_analysis, on_blast_done)


    def _create_log_dock(self):
        self.dock_log = QDockWidget("Log", self)
        self.dock_log.setAllowedAreas(Qt.BottomDockWidgetArea)
        
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        self.dock_log.setWidget(self.log_widget)
        
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_log)

    def _create_menu(self):
        menubar = self.menuBar()

        # View menu
        view_menu = menubar.addMenu("View")
        view_menu.addAction(self.dock_files.toggleViewAction())
        view_menu.addAction(self.dock_ncbi.toggleViewAction())
        view_menu.addAction(self.dock_props.toggleViewAction())
        view_menu.addAction(self.dock_log.toggleViewAction())

        # Map menu
        map_menu = menubar.addMenu("Map")
        ac_map_mm = QAction("Map Mismatches && Clusters", self)
        ac_map_mm.triggered.connect(self.map_mismatches_and_clusters)
        map_menu.addAction(ac_map_mm)

        ac_map_pr = QAction("Map Primers && Amplicons", self)
        ac_map_pr.triggered.connect(self.map_primers_and_amplicons)
        map_menu.addAction(ac_map_pr)

        map_menu.addSeparator()
        ac_map_all = QAction("Map All", self)
        ac_map_all.triggered.connect(self.map_all)
        map_menu.addAction(ac_map_all)

        # References menu
        ref_menu = menubar.addMenu("References")
        ac_open_blast = QAction("Open BLAST Folder", self)
        ac_open_blast.triggered.connect(lambda: self._open_folder("BLAST"))
        ref_menu.addAction(ac_open_blast)

        ac_open_genes = QAction("Open Genes Folder", self)
        ac_open_genes.triggered.connect(lambda: self._open_folder("Genes"))
        ref_menu.addAction(ac_open_genes)

        ac_open_ws = QAction("Open Workspace", self)
        ac_open_ws.triggered.connect(lambda: self._open_folder(""))
        ref_menu.addAction(ac_open_ws)

        # Report menu
        report_menu = menubar.addMenu("Report")
        ac_gen_report = QAction("Generate Report…", self)
        ac_gen_report.triggered.connect(self.on_generate_report)
        report_menu.addAction(ac_gen_report)

    def _open_folder(self, subfolder):
        ws = self.le_ws.text()
        org = self.le_organism.text().replace(" ", "_")
        if subfolder:
            target = os.path.join(ws, org, subfolder)
        else:
            target = ws
        if os.path.isdir(target):
            subprocess.Popen(["explorer", target])
        else:
            self.log_message(f"Folder not found: {target}")

    def _create_toolbar(self):
        tb = QToolBar("Main")
        self.addToolBar(tb)

        # Workspace selector
        tb.addWidget(QLabel(" Worksp: "))
        self.le_ws = QLineEdit(os.getcwd())
        self.le_ws.setReadOnly(True)
        tb.addWidget(self.le_ws)

        btn_ws = QPushButton("Change")
        btn_ws.clicked.connect(self.on_change_workspace)
        tb.addWidget(btn_ws)

        tb.addSeparator()

        # API Key
        tb.addWidget(QLabel(" API Key: "))
        self.le_api = QLineEdit()
        self.le_api.setEchoMode(QLineEdit.Password)
        self.le_api.setFixedWidth(100)
        tb.addWidget(self.le_api)

        tb.addSeparator()

        # References button
        btn_ref = QToolButton()
        btn_ref.setText("References")
        ref_menu = QMenu(btn_ref)
        ref_menu.addAction("Open BLAST Folder", lambda: self._open_folder("BLAST"))
        ref_menu.addAction("Open Genes Folder", lambda: self._open_folder("Genes"))
        ref_menu.addAction("Open Workspace", lambda: self._open_folder(""))
        btn_ref.setMenu(ref_menu)
        btn_ref.setPopupMode(QToolButton.InstantPopup)
        tb.addWidget(btn_ref)

        # Map button
        btn_map = QToolButton()
        btn_map.setText("Map ▾")
        map_menu = QMenu(btn_map)
        map_menu.addAction("Mismatches & Clusters", self.map_mismatches_and_clusters)
        map_menu.addAction("Primers & Amplicons", self.map_primers_and_amplicons)
        map_menu.addSeparator()
        map_menu.addAction("Map All", self.map_all)
        btn_map.setMenu(map_menu)
        btn_map.setPopupMode(QToolButton.InstantPopup)
        tb.addWidget(btn_map)

        tb.addSeparator()

        # Color scheme
        from gui.sequence_viewer import COLOR_SCHEMES, MONOSPACE_FONTS
        tb.addWidget(QLabel(" Colors: "))
        self.combo_scheme = QComboBox()
        self.combo_scheme.addItems(list(COLOR_SCHEMES.keys()))
        self.combo_scheme.currentTextChanged.connect(
            lambda s: self.current_viewer.set_color_scheme(s) if self.current_viewer else None)
        tb.addWidget(self.combo_scheme)

        # Font
        tb.addWidget(QLabel(" Font: "))
        self.combo_font = QComboBox()
        self.combo_font.addItems(MONOSPACE_FONTS)
        self.combo_font.currentTextChanged.connect(
            lambda f: self.current_viewer.set_font(f) if self.current_viewer else None)
        tb.addWidget(self.combo_font)

        tb.addSeparator()

        # Report button
        btn_report = QPushButton("📄 Report")
        btn_report.clicked.connect(self.on_generate_report)
        tb.addWidget(btn_report)

    # --- Threading Helpers ---
    def run_worker(self, func, callback, *args, **kwargs):
        from gui.workers import BaseWorker
        worker = BaseWorker(func, *args, **kwargs)
        worker.finished_result.connect(callback)
        worker.error_occurred.connect(lambda e: self.log_message(f"Error: {e}"))
        worker.finished.connect(lambda: self._worker_finished(worker))
        
        # Keep reference to avoid GC
        if not hasattr(self, "_workers"): self._workers = []
        self._workers.append(worker)
        worker.start()
        
    def _worker_finished(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)

    # --- Actions ---
    
    def on_file_double_click(self, index):
        path = self.fs_model.filePath(index)
        if path.endswith(".fasta") or path.endswith(".fa"):
            self.load_sequence(path)
            
    def load_sequence(self, path):
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            # Simple fasta parse (first rec)
            if lines and lines[0].startswith(">"):
                seq = "".join(l.strip() for l in lines[1:]) 
                # Open in new tab use filename as gene name/title
                tab_name = os.path.splitext(os.path.basename(path))[0]
                sv = self.add_viewer_tab(tab_name)
                sv.load_sequence(seq)
                
                self.current_seq = seq
                self.log_message(f"Loaded: {os.path.basename(path)}")
            else:
                self.log_message(f"Invalid FASTA: {path}")
        except Exception as e:
            self.log_message(f"Error loading file: {e}")

    def on_search_loci(self):
        query = self.le_organism.text()
        if not query: return
        
        self.log_message(f"Searching loci for {query}...")
        self.btn_search.setEnabled(False)
        
        def on_done(res):
            self.populate_loci_table(res)
            self.log_message(f"Found {len(res)} clusters.")
            self.btn_search.setEnabled(True)
            
        self.run_worker(self.downloader.p_search_loci_candidates, on_done, query, limit=100)
            
    def populate_loci_table(self, data):
        self.table_loci.setRowCount(0)
        self.table_loci.setSortingEnabled(False)
        for row in data:
            r = self.table_loci.rowCount()
            self.table_loci.insertRow(r)
            
            # Title Item with Checkbox
            item_title = QTableWidgetItem(row['title'])
            item_title.setFlags(item_title.flags() | Qt.ItemIsUserCheckable)
            item_title.setCheckState(Qt.Unchecked)
            
            self.table_loci.setItem(r, 0, item_title)
            self.table_loci.setItem(r, 1, QTableWidgetItem(str(row['count'])))
            self.table_loci.setItem(r, 2, QTableWidgetItem(row['accession']))
        self.table_loci.setSortingEnabled(True)

    def on_download_loci(self):
        # Determine selection by Checkboxes
        selected_items = []
        for r in range(self.table_loci.rowCount()):
            item = self.table_loci.item(r, 0)
            if item.checkState() == Qt.Checked:
                title = item.text()
                # Extract key from "KEY (Title...)"
                key = title.split(" (")[0]
                selected_items.append(key)
        
        # Fallback to selected rows if no checkboxes are checked (UX convenience)
        if not selected_items:
            rows = self.table_loci.selectionModel().selectedRows()
            for r in rows:
                title = self.table_loci.item(r.row(), 0).text()
                key = title.split(" (")[0]
                selected_items.append(key)

        if not selected_items:
            self.log_message("No loci selected (use checkboxes).")
            return
            
        self.log_message(f"Downloading {selected_items}...")
        
        # Prepare Config
        # We need taxid. Search gives results, but doesn't return taxid directly in this flow yet (mixed results).
        # ideally we pick taxid first. 
        # For now, let's search taxid for the query first in background or ask user.
        # User entered "Fusarium graminearum".
        # Let's just pass 0 and let downloader handle? No, fetch_loci needs taxid.
        
        # Quick hack: resolve taxid for query.
        def resolve_and_download():
            # 1. Resolve TaxID
            # (We should have done this in search, but okay)
            from Bio import Entrez
            try:
                handle = Entrez.esearch(db="taxonomy", term=self.le_organism.text())
                rec = Entrez.read(handle)
                handle.close()
                if not rec["IdList"]:
                     raise ValueError("TaxID not found")
                taxid = rec["IdList"][0]
            except Exception as e:
                return f"Error resolving TaxID: {e}"
                
            # 2. Download
            loci_config = {k: {'search_terms': [k]} for k in selected_items}
            
            # Workspace
            ws = self.le_ws.text()
            
            # Run
            path = self.downloader.fetch_loci(taxid, self.le_organism.text(), loci_config, ws)
            return path
            
        self.run_worker(resolve_and_download, 
                        lambda res: self.log_message(f"Download complete: {res}" if isinstance(res, str) else res))

    def on_change_workspace(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Select Workspace")
        if d:
            self.le_ws.setText(d)
            self.fs_model.setRootPath(d)
            self.tree.setRootIndex(self.fs_model.index(d))
            context.set_workspace(d)
            self._auto_detect_organism(d)
            self._auto_load_reference()
            self.log_message(f"Workspace changed to: {d}")

    def _auto_detect_organism(self, ws_path):
        """
        Scan workspace for a folder that looks like an organism (has Genes/BLAST).
        If found, populate the Organism field automatically.
        """
        try:
            candidates = []
            if os.path.isdir(ws_path):
                with os.scandir(ws_path) as it:
                    for entry in it:
                        if entry.is_dir() and not entry.name.startswith("."):
                            sub_genes = os.path.join(entry.path, "Genes")
                            sub_blast = os.path.join(entry.path, "BLAST")
                            if os.path.isdir(sub_genes) or os.path.isdir(sub_blast):
                                candidates.append(entry.name)
            
            if candidates:
                best = candidates[0]
                self.le_organism.setText(best)
                self.log_message(f"Auto-detected organism: {best}")
            else:
                self.log_message("No organism folders (with Genes/BLAST) found in workspace.")
        except Exception as e:
            self.log_message(f"Error auto-detecting organism: {e}")
        
    def _auto_load_reference(self):
        """Auto-detect the longest FASTA in the first gene folder and load it."""
        try:
            org_root = self._get_org_root()
            genes_dir = os.path.join(org_root, "Genes")
            if not os.path.isdir(genes_dir):
                return
            # Pick first gene subfolder
            gene_dirs = [d for d in os.listdir(genes_dir) 
                         if os.path.isdir(os.path.join(genes_dir, d))]
            if not gene_dirs:
                return
            gene_path = os.path.join(genes_dir, gene_dirs[0])
            best_path, best_seq = self._find_longest_fasta(gene_path)
            if best_path:
                self.load_sequence(best_path)
                self.log_message(f"Auto-loaded reference: {os.path.basename(best_path)}")
        except Exception as e:
            self.log_message(f"Error auto-loading reference: {e}")

    def log_message(self, msg):
        self.log_widget.appendPlainText(msg)



    def on_design_primers(self):
        """
        Design primers using the longest FASTA as reference and
        ranked mismatch clusters from BLAST analysis.

        Forward primer lands on one cluster, reverse on another.
        Distance between clusters must fit the amplification product size.
        """
        ws = self.le_ws.text()
        target_org = self.le_organism.text()
        if not ws or not target_org:
            self.log_message("Set workspace and organism first.")
            return

        safe_org = target_org.replace(" ", "_")
        blast_root = os.path.join(ws, safe_org, "BLAST")
        genes_root = os.path.join(ws, safe_org, "Genes")

        if not os.path.isdir(blast_root):
            self.log_message(f"No BLAST results found at {blast_root}")
            return


        meta_files = glob.glob(os.path.join(blast_root, "*", "*_cluster_meta.json"))
        if not meta_files:
            self.log_message("No cluster metadata found. Run BLAST analysis first.")
            return

        from core.primer_designer import PrimerDesigner
        designer = PrimerDesigner()
        mode = self.combo_preset.currentText().split(" ")[0]

        self.log_message(f"Designing {mode} primers for {len(meta_files)} gene(s)...")
        self.btn_design.setEnabled(False)

        def run_design():
            all_results = []
            for meta_path in meta_files:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                gene = meta["gene"]
                clusters = meta.get("clusters", [])
                longest = meta.get("longest_fasta", {})
                fasta_path = longest.get("path", "")

                if not fasta_path or not os.path.exists(fasta_path):
                    gene_dir = os.path.join(genes_root, gene)
                    if os.path.isdir(gene_dir):
                        best_path, best_len = "", 0
                        for fn in os.listdir(gene_dir):
                            if fn.endswith(".fasta"):
                                fp = os.path.join(gene_dir, fn)
                                try:
                                    with open(fp, "r") as ff:
                                        lines = ff.readlines()
                                    seq = "".join(l.strip() for l in lines if not l.startswith(">"))
                                    if len(seq) > best_len:
                                        best_len = len(seq)
                                        best_path = fp
                                except Exception:
                                    pass
                        fasta_path = best_path

                if not fasta_path or not os.path.exists(fasta_path):
                    print(f"  No FASTA found for gene {gene}, skipping primer design")
                    continue

                with open(fasta_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                seq = "".join(l.strip() for l in lines if not l.startswith(">"))
                if not seq:
                    continue

                print(f"  Designing primers for {gene} ({len(seq)}bp, {len(clusters)} clusters)...")
                custom = getattr(self, "custom_primer_settings", None)
                n_top = getattr(self, "max_primer_pairs", 10)
                n_cpairs = getattr(self, "n_cluster_pairs", 20)
                pairs = designer.design_primers_from_clusters(
                    seq, mode=mode, clusters=clusters,
                    n_per_pair=50, n_top=n_top,
                    n_cluster_pairs=n_cpairs,
                    custom_settings=custom,
                )
                for p in pairs:
                    p["gene"] = gene
                    p["ref_fasta"] = os.path.basename(fasta_path)
                    p["ref_len"] = len(seq)

                all_results.extend(pairs)
            return all_results

        def on_design_done(pairs):
            self.log_message(f"Designed {len(pairs)} primer pairs total.")
            self.btn_design.setEnabled(True)

            if not pairs:
                self.log_message("No primers found. Check BLAST clusters.")
                return

            self._show_primer_results(pairs)
            self._save_primers_xlsx(pairs)

            # Map results to viewers (supports multi-tab)
            self.map_primers_and_amplicons()

        self.run_worker(run_design, on_design_done)

    def _show_primer_results(self, pairs: list):
        """Create or update a dock with primer results table."""
        if not hasattr(self, "dock_primers"):
            self.dock_primers = QDockWidget("Primer Results", self)
            self.dock_primers.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
            self.primer_table = QTableWidget()
            self.dock_primers.setWidget(self.primer_table)
            self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_primers)

        headers = [
            "Rank", "Gene", "Fwd Clst", "Rev Clst", "Score", "Species",
            "Fwd MM", "Rev MM", "Forward", "Reverse",
            "Fwd Tm", "Rev Tm", "Product",
            "Hairpin", "Dimer", "Thrm Pen",
        ]
        t = self.primer_table
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setRowCount(0)

        for p in pairs:
            r = t.rowCount()
            t.insertRow(r)
            vals = [
                str(p.get("global_rank", "")),
                p.get("gene", ""),
                str(p.get("fwd_cluster_id", "")),
                str(p.get("rev_cluster_id", "")),
                str(p.get("score", "")),
                str(p.get("n_species_covered", "")),
                str(p.get("fwd_mm_covered", "")),
                str(p.get("rev_mm_covered", "")),
                p.get("left", ""),
                p.get("right", ""),
                str(p.get("left_tm", "")),
                str(p.get("right_tm", "")),
                str(p.get("product_size", "")),
                f"{p.get('left_hairpin_tm', 0)}/{p.get('right_hairpin_tm', 0)}",
                f"{p.get('left_dimer_tm', 0)}/{p.get('right_dimer_tm', 0)}",
                str(p.get("thermal_penalty", "")),
            ]
            for c, v in enumerate(vals):
                t.setItem(r, c, QTableWidgetItem(v))

        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.dock_primers.show()

    def _save_primers_xlsx(self, pairs: list):
        """Save primer pairs to {Organism}/Primers/ as XLSX."""
        if not pairs:
            return
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font as XlFont, PatternFill

            ws_path = self.le_ws.text()
            org = self.le_organism.text().replace(" ", "_")
            primer_dir = os.path.join(ws_path, org, "Primers")
            os.makedirs(primer_dir, exist_ok=True)

            # Build filename from gene + method
            gene = pairs[0].get("gene", "unknown")
            mode = self.combo_preset.currentText().split(" ")[0].lower()
            out_path = os.path.join(primer_dir, f"{gene}_{mode}_primers.xlsx")

            wb = Workbook()
            ws = wb.active
            ws.title = "Primer Pairs"

            headers = [
                "Rank", "Gene", "Fwd Cluster", "Rev Cluster",
                "Score", "Species", "Fwd Mismatches", "Rev Mismatches",
                "Forward Seq", "Reverse Seq",
                "Fwd Tm (°C)", "Rev Tm (°C)", "Product (bp)",
                "Fwd Pos", "Fwd Len", "Rev Pos", "Rev Len",
                "Hairpin (F/R)", "Dimer (F/R)", "Thermal Penalty",
            ]
            # Header style
            hdr_font = XlFont(bold=True, color="FFFFFF")
            hdr_fill = PatternFill("solid", fgColor="2C3E50")
            for c, h in enumerate(headers, 1):
                cell = ws.cell(row=1, column=c, value=h)
                cell.font = hdr_font
                cell.fill = hdr_fill

            for i, p in enumerate(pairs):
                row = i + 2
                vals = [
                    p.get("global_rank", ""),
                    p.get("gene", ""),
                    p.get("fwd_cluster_id", ""),
                    p.get("rev_cluster_id", ""),
                    p.get("score", ""),
                    p.get("n_species_covered", ""),
                    p.get("fwd_mm_covered", ""),
                    p.get("rev_mm_covered", ""),
                    p.get("left", ""),
                    p.get("right", ""),
                    p.get("left_tm", ""),
                    p.get("right_tm", ""),
                    p.get("product_size", ""),
                    p.get("left_pos", ""),
                    p.get("left_len", ""),
                    p.get("right_pos", ""),
                    p.get("right_len", ""),
                    f"{p.get('left_hairpin_tm', 0)}/{p.get('right_hairpin_tm', 0)}",
                    f"{p.get('left_dimer_tm', 0)}/{p.get('right_dimer_tm', 0)}",
                    p.get("thermal_penalty", ""),
                ]
                for c, v in enumerate(vals, 1):
                    ws.cell(row=row, column=c, value=v)

            # Auto-width columns
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = min(max_len + 3, 35)

            wb.save(out_path)
            self.log_message(f"Primers saved to {out_path}")

            # Also save JSON for map_primers_and_amplicons
            json_path = os.path.join(
                ws_path, org, "BLAST", gene, f"{gene}_{mode}_primers.json"
            )
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            import json as _jjson
            with open(json_path, "w", encoding="utf-8") as jf:
                _jjson.dump(pairs, jf, indent=2, default=str)

        except Exception as e:
            self.log_message(f"Error saving primers XLSX: {e}")

    def load_primers_for_specificity(self):
        """Load designed primers from workspace for specificity check."""
        ws = self.le_ws.text()
        
        # --- Selection Dialog ---
        from gui.selection_dialog import SelectionDialog
        dlg = SelectionDialog(ws, "Select Primers for Specificity", self)
        if not dlg.exec():
            return
            
        selected_primers = []
        
        for sel in dlg.selections:
            org = sel["organism"]
            genes = sel["genes"]
            
            # Locate primers for these genes
            # Expected path: {ws}/{org}/BLAST/{gene}/*_primers.json
            base_dir = os.path.join(ws, org, "BLAST")
            
            for gene in genes:
                gene_dir = os.path.join(base_dir, gene)
                if not os.path.isdir(gene_dir):
                    continue
                
                # Find primer json
                p_files = glob.glob(os.path.join(gene_dir, "*_primers.json"))
                for pf in p_files:
                    try:
                        with open(pf, "r", encoding="utf-8") as f:
                            pairs = json.load(f)
                        # Add to list
                        for p in pairs:
                            # Ensure name has gene info if not already unique
                            if "name" not in p:
                                rank = p.get("global_rank", "?")
                                p["name"] = f"{gene}_Rank{rank}"
                            selected_primers.append(p)
                    except Exception as e:
                        self.log_message(f"Error loading primers for {gene}: {e}")

        self.loaded_specificity_primers = selected_primers
        self.log_message(f"Loaded {len(selected_primers)} primer pairs for specificity check.")

    def on_run_specificity(self):
        primers = getattr(self, "loaded_specificity_primers", [])
        if not primers:
            self.log_message("Please load primers first.")
            return

        db_name = self.combo_spec_db.currentText()
        entrez = self.le_entrez.text().strip()
        target_org = self.le_spec_target.text().strip() or self.le_organism.text().strip()
        
        # Output directory for reports
        output_dir = os.path.join(self._get_org_root(), "Primer-BLAST")
        
        self.log_message(f"Running Primer-BLAST specificity on {len(primers)} pairs against {db_name}...")
        self.btn_run_spec.setEnabled(False)
        
        from core.primer_specificity import SpecificityAnalyzer
        analyzer = SpecificityAnalyzer()
        
        def run_spec():
            # Run blocking call in worker
            return analyzer.run_primer_blast(
                primers, 
                database=db_name, 
                organism_filter=entrez,
                target_organism=target_org,
                output_dir=output_dir
            )
            
        def on_done(results):
            self.btn_run_spec.setEnabled(True)
            self.log_message("Specificity check complete.")
            self._show_specificity_results(results)
            
        self.run_worker(run_spec, on_done)

    def _show_specificity_results(self, results):
        if not hasattr(self, "dock_spec_res"):
            self.dock_spec_res = QDockWidget("Specificity Results", self)
            self.dock_spec_res.setAllowedAreas(Qt.BottomDockWidgetArea)
            self.spec_table = QTableWidget()
            self.dock_spec_res.setWidget(self.spec_table)
            self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_spec_res)
            
        t = self.spec_table
        headers = ["Pair", "Forward", "Reverse", "Status", "Target Hits", "Off-Target Hits"]
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setRowCount(0)
        
        from PySide6.QtGui import QColor, QBrush
        
        # Helper to create styled item (defined outside loop to avoid closure issues)
        def make_item(text, bg=None, fg=Qt.white):
            it = QTableWidgetItem(str(text))
            if bg: it.setBackground(bg)
            it.setForeground(fg)
            return it

        for p in results:
            r = t.rowCount()
            t.insertRow(r)
            status = p.get('specificity_status', 'Unknown')
            
            # Color code (Darker Pastel / Material Dark)
            bg_color = QColor("#424242") # Default dark
            if status == "Species-Specific": bg_color = QColor("#2E7D32")
            elif status == "Genus-Specific": bg_color = QColor("#E65100")
            elif status == "Non-Specific": bg_color = QColor("#C62828")

            t.setItem(r, 0, make_item(p.get('name', '')))
            t.setItem(r, 1, make_item(p.get('fwd', '') or p.get('left', '')))
            t.setItem(r, 2, make_item(p.get('rev', '') or p.get('right', '')))
            t.setItem(r, 3, make_item(status, bg=bg_color))
            t.setItem(r, 4, make_item(p.get('target_hits', 0)))
            t.setItem(r, 5, make_item(p.get('off_target_hits', 0)))
            
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.dock_spec_res.show()

    # ═══════════════ MAP functions ═════════════════
    def _get_org_root(self):
        ws = self.le_ws.text()
        org = self.le_organism.text().replace(" ", "_")
        
        # If empty, try detecting again (maybe user cleared it)
        if not org:
            self._auto_detect_organism(ws)
            org = self.le_organism.text().replace(" ", "_")
            
        return os.path.join(ws, org)

    def _find_longest_fasta(self, gene_dir):
        """Return (path, sequence) for the longest FASTA in a gene folder."""
        best_path, best_len, best_seq = None, 0, ""
        for fn in os.listdir(gene_dir):
            if fn.endswith(".fasta"):
                fp = os.path.join(gene_dir, fn)
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                seq = "".join(l.strip() for l in lines if not l.startswith(">"))
                if len(seq) > best_len:
                    best_path, best_len, best_seq = fp, len(seq), seq
        return best_path, best_seq

    def map_mismatches_and_clusters(self):
        """Load reference FASTA and overlay mismatch heatmap + top-10 clusters."""
        org_root = self._get_org_root()
        blast_dir = os.path.join(org_root, "BLAST")
        genes_dir = os.path.join(org_root, "Genes")
        if not os.path.isdir(blast_dir):
            self.log_message("No BLAST results found. Run analysis first.")
            return

        # Find all cluster_meta.json files
        meta_files = glob.glob(os.path.join(blast_dir, "**", "*_cluster_meta.json"), recursive=True)
        if not meta_files:
            self.log_message("No cluster metadata files found.")
            return

        # --- Selection Dialog ---
        from gui.selection_dialog import SelectionDialog
        ws = self.le_ws.text()
        dlg = SelectionDialog(ws, "Select Genes to Map", self)
        if not dlg.exec():
            return
        
        selected_genes = set()
        for sel in dlg.selections:
            # We only mapped for the current workspace/organism structure usually
            # But dlg shows whole workspace. 
            # If user selected genes from WRONG organism, we might want to skip or handle.
            # For now, let's just collect all selected gene names.
            # Assuming uniqueness or we check organism match.
            
            # Actually, `map_mismatches_and_clusters` logic currently assumes `self.le_organism` is set
            # and `org_root` is derived from it. 
            # So we should probably filter `meta_files` based on `sel['organism'] == current_org`
            # OR we switch logic to support multi-organism mapping?
            # The current viewer tabs don't explicitly show organism, just gene name.
            # If we map TEF1 from OrgA and TEF1 from OrgB, we need distinct tab names or just support one org.
            
            # Logic: Filter to simple gene list for CURRENT organism only.
            current_org = self.le_organism.text().replace(" ", "_")
            if sel["organism"] == current_org:
                selected_genes.update(sel["genes"])
        
        if not selected_genes:
            self.log_message("No genes selected for current organism.")
            return

        self.log_message(f"Mapping results for {len(selected_genes)} selected genes...")

        for meta_path in meta_files:
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception as e:
                self.log_message(f"Error reading cluster metadata ({os.path.basename(meta_path)}): {e}")
                continue

            gene = meta.get("gene", "")
            if not gene or gene not in selected_genes: 
                continue
            
            # Create/Focus Tab for this Gene
            sv = self.add_viewer_tab(gene, switch_to=False) # Don't switch focus constantly
            
            gene_dir = os.path.join(genes_dir, gene)
            # Load longest reference FASTA
            ref_path, ref_seq = self._find_longest_fasta(gene_dir)
            if ref_seq:
                sv.load_sequence(ref_seq)
            else:
                self.log_message(f"No FASTA sequence found for {gene}")

            # Add mismatch heatmap from XLSX (all_positions sheet)
            try:
                import openpyxl
                xlsx_files = glob.glob(os.path.join(blast_dir, gene, f"{gene}_general_summary.xlsx"))
                if xlsx_files:
                    wb = openpyxl.load_workbook(xlsx_files[0], read_only=True)
                    if "all_positions" in wb.sheetnames:
                        ws_sheet = wb["all_positions"]
                        mm_data = []
                        for row in ws_sheet.iter_rows(min_row=2, values_only=True):
                            if row[0] is not None:
                                mm_data.append({
                                    "pos": int(row[0]),
                                    "count": int(row[1]) if row[1] else 1,
                                    "total": meta.get("n_accessions", 100),
                                    "variants": str(row[2]) if len(row) > 2 and row[2] else "",
                                })
                        if mm_data:
                            sv.add_mismatches(mm_data)
                    wb.close()
            except Exception as e:
                self.log_message(f"Could not load mismatch data for {gene}: {e}")

            # Add ALL clusters
            clusters_batch = []
            for cl in meta.get("clusters", []):
                clusters_batch.append({
                    "start": cl["span_start"] - 1,
                    "end": cl["span_end"] - 1,
                    "id": cl["cluster_id"],
                    "rank": cl["cluster_rank"],
                    "n_mm": cl["n_positions"],
                    "n_species": cl.get("n_species", 0),
                    "species": cl.get("species", []),
                })
            if clusters_batch:
                sv.add_clusters_batch(clusters_batch)
        
        self.log_message("Mapping complete.")

    def map_primers_and_amplicons(self):
        """Load primer results and map primers + amplicons onto the viewer."""
        org_root = self._get_org_root()
        blast_dir = os.path.join(org_root, "BLAST")

        # Find primer output JSON
        primer_files = glob.glob(os.path.join(blast_dir, "**", "*_primers.json"), recursive=True)
        if not primer_files:
            self.log_message("No primer output files found. Design primers first.")
            return

        # --- Selection Dialog ---
        from gui.selection_dialog import SelectionDialog
        ws = self.le_ws.text()
        dlg = SelectionDialog(ws, "Select Primers to Map", self)
        if not dlg.exec():
            return
        
        selected_genes = set()
        current_org = self.le_organism.text().replace(" ", "_")
        for sel in dlg.selections:
            if sel["organism"] == current_org:
                selected_genes.update(sel["genes"])
        
        if not selected_genes:
            self.log_message("No genes selected for current organism.")
            return

        total_pairs = 0
        modified_viewers = set()

        for pfile in primer_files:
            try:
                with open(pfile, "r", encoding="utf-8") as f:
                    pairs = json.load(f)
            except Exception as e:
                self.log_message(f"Error reading primer results ({os.path.basename(pfile)}): {e}")
                continue

            if not pairs: continue

            # Check if this file belongs to a selected gene
            # Strategy: peek first pair or filename
            file_gene = ""
            if pairs:
                file_gene = pairs[0].get("gene", "")
            if not file_gene:
                file_gene = os.path.basename(pfile).replace("_primers.json", "").replace(f"{current_org}_", "") # approximate
            
            # Simple check
            if file_gene not in selected_genes:
                # Try explicit filename check if gene inside json is missing/wrong
                # e.g. TEF1_pcr_primers.json
                # Let's trust the loop below which handles per-pair gene
                pass

            for idx, p in enumerate(pairs):
                gene = p.get("gene", "")
                if not gene:
                    gene = os.path.basename(pfile).replace("_primers.json", "")
                
                if gene not in selected_genes:
                    continue
                
                sv = self.add_viewer_tab(gene, switch_to=False)
                modified_viewers.add(sv)

                rank = p.get("global_rank", idx)
                sv.add_primer(
                    p["left_pos"], p["left_len"], False,
                    {"seq": p.get("left", ""), "pos": p.get("left_pos", 0),
                     "len": p.get("left_len", 0), "tm": p.get("left_tm", 0),
                     "mm": p.get("fwd_mm_covered", 0),
                     "cluster_id": p.get("fwd_cluster_id", "?")},
                    pair_rank=rank,
                )
                r_start = p["right_pos"] - p["right_len"] + 1
                sv.add_primer(
                    r_start, p["right_len"], True,
                    {"seq": p.get("right", ""), "pos": r_start,
                     "len": p.get("right_len", 0), "tm": p.get("right_tm", 0),
                     "mm": p.get("rev_mm_covered", 0),
                     "cluster_id": p.get("rev_cluster_id", "?")},
                    pair_rank=rank,
                )
                sv.add_amplicon_span(
                    p["left_pos"], p["right_pos"],
                    {"size": p.get("product_size", 0),
                     "rank": rank,
                     "fwd_cid": p.get("fwd_cluster_id", "?"),
                     "rev_cid": p.get("rev_cluster_id", "?"),
                     "n_species": p.get("n_species_covered", 0)},
                )
                total_pairs += 1

        for sv in modified_viewers:
            sv.finish_annotations()
            
        self.log_message(f"Mapped {total_pairs} primer pairs across {len(modified_viewers)} genes.")

    def map_all(self):
        """Map mismatches, clusters, primers, and amplicons in one go."""
        self.map_mismatches_and_clusters()
        self.map_primers_and_amplicons()

    # ── Report generation ────────────────────────────────────
    def on_generate_report(self):
        """Open report selection dialog and generate PDF/DOCX."""
        from gui.report_dialog import ReportDialog
        from core.report_generator import ReportDataCollector, generate_pdf, generate_docx

        ws = self.le_ws.text()
        dlg = ReportDialog(ws, self)
        if not dlg.exec():
            return

        selections = dlg.selections
        fmt = dlg.output_format
        include_screenshot = dlg.include_screenshot
        viewer_cols = dlg.viewer_cols

        self.log_message(f"Generating report ({fmt.upper()}) for {len(selections)} organism(s)…")

        # Collect data
        collector = ReportDataCollector(ws)
        all_data = []
        for sel in selections:
            for gene in sel["genes"]:
                data = collector.collect(sel["organism"], gene)
                all_data.append(data)

        if not all_data:
            self.log_message("No data collected.")
            return

        # Screenshot
        screenshot_path = None
        if include_screenshot and self.current_viewer:
            # Temporarily apply the requested cols_per_row, then restore.
            _prev_cols = self.current_viewer.cols_per_row
            self.current_viewer.set_cols_per_row(viewer_cols)
            img = self.current_viewer.export_to_image()
            self.current_viewer.set_cols_per_row(_prev_cols)
            if img:
                org_name = selections[0]["organism"]
                out_dir = os.path.join(ws, org_name, "Reports")
                os.makedirs(out_dir, exist_ok=True)
                screenshot_path = os.path.join(out_dir, "viewer_screenshot.png")
                img.save(screenshot_path)
                self.log_message(f"Exported viewer screenshot: {screenshot_path}")

        # Output directory
        org_name = selections[0]["organism"]
        out_dir = os.path.join(ws, org_name, "Reports")
        os.makedirs(out_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            if fmt in ("pdf", "both"):
                pdf_path = os.path.join(out_dir, f"Report_{timestamp}.pdf")
                generate_pdf(all_data, pdf_path, screenshot_path)
                self.log_message(f"PDF saved: {pdf_path}")

            if fmt in ("docx", "both"):
                docx_path = os.path.join(out_dir, f"Report_{timestamp}.docx")
                generate_docx(all_data, docx_path, screenshot_path)
                self.log_message(f"DOCX saved: {docx_path}")

            # Open output folder
            import subprocess
            subprocess.Popen(["explorer", out_dir])
            self.log_message("Report generation complete!")

        except Exception as e:
            self.log_message(f"Report generation failed: {e}")
            import traceback
            traceback.print_exc()
