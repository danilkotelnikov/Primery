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
import re
from functools import partial
from datetime import datetime

from PySide6.QtWidgets import (QMainWindow, QDockWidget, QWidget, QVBoxLayout,
                               QFileSystemModel, QTreeView, QPlainTextEdit,
                               QToolBar, QLabel, QLineEdit, QPushButton, QComboBox,
                               QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                               QGroupBox, QFormLayout, QInputDialog, QMenu, QToolButton,
                               QFileDialog, QTabWidget, QTabBar, QSpinBox)
from PySide6.QtCore import Qt, QSize, QObject, Signal, QSettings
from PySide6.QtGui import QIcon, QAction

from gui.sequence_viewer import SequenceViewer
from gui.i18n import tr
from gui.gui_context import context
# Import core logical components
from core.ncbi_downloader import NCBIDownloader
from core.blast_analyzer import BlastAnalyzer
# We will use threading (QThread) for long running tasks, similar to old gui_app.py but cleaner

APP_VERSION = "0.2.0"

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
        self.setWindowTitle(f"Primery {APP_VERSION}")
        
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
        sv.sequenceEdited.connect(lambda seq, viewer=sv: self._on_viewer_sequence_edited(viewer, seq))
        if hasattr(self, 'combo_font'):
            sv.set_font(self.combo_font.currentText())
        if hasattr(self, 'combo_scheme'):
            sv.set_color_scheme(self.combo_scheme.currentText())
        
        idx = self.tabs.addTab(sv, gene_name)
        if switch_to:
            self.tabs.setCurrentIndex(idx)
        return sv

    def _on_viewer_sequence_edited(self, viewer, seq):
        self.current_seq = seq
        name = self.tabs.tabText(self.tabs.indexOf(viewer)) if self.tabs.indexOf(viewer) >= 0 else "sequence"
        self.log_message(f"Sequence edited in viewer: {name} ({len(seq)} bp). Rerun BLAST analysis to refresh mismatch clusters.")

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

            if not is_dir:
                ac_edit = QAction("Edit", self)
                ac_edit.triggered.connect(lambda: self._open_editor(path))
                menu.addAction(ac_edit)
                menu.addSeparator()

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

        self.le_gene_query = QLineEdit()
        self.le_gene_query.setPlaceholderText("optional: ITS2, COX1, beta-tubulin")
        form.addRow("Gene/keyword:", self.le_gene_query)

        self.sp_per_cluster = QSpinBox()
        self.sp_per_cluster.setRange(1, 500)
        self.sp_per_cluster.setValue(10)
        form.addRow("FASTAs per cluster:", self.sp_per_cluster)
        
        layout.addLayout(form)
        
        # Buttons
        self.btn_search = QPushButton("Search Genes")
        self.btn_search.clicked.connect(self.on_search_loci)
        layout.addWidget(self.btn_search)
        
        # Results Table
        self.table_loci = QTableWidget(0, 5)
        self.table_loci.setHorizontalHeaderLabels([
            "Canonical", "Aliases", "Count", "Per-cluster", "Examples"
        ])
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
        self.combo_limit.addItems([
            "None", "Genus", "Species", "Isolate / Strain", "Clade / Species Complex"
        ])
        l_mm.addRow("Limit By:", self.combo_limit)

        self.le_complex_species = QLineEdit()
        self.le_complex_species.setPlaceholderText("Species to exclude for clade/complex mode; separate with ;")
        l_mm.addRow("Exclude Species:", self.le_complex_species)

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

        self.btn_adv_settings = QPushButton("Advanced Primer Settings")
        self.btn_adv_settings.clicked.connect(self.open_primer_settings)
        l_p3.addRow(self.btn_adv_settings)

        self.btn_probe_settings = QPushButton("Probe Settings")
        self.btn_probe_settings.clicked.connect(self.open_probe_settings)
        l_p3.addRow(self.btn_probe_settings)

        self.btn_design = QPushButton("Design Primers")
        self.btn_design.clicked.connect(self.on_design_primers)
        l_p3.addRow(self.btn_design)

        self.btn_design_probes = QPushButton("Design Probes")
        self.btn_design_probes.clicked.connect(self.on_design_probes)
        l_p3.addRow(self.btn_design_probes)
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
        self.custom_probe_settings = {
            "mode": "fallback",
            "chemistry": "taqman",
            "dye": "FAM",
            "quencher": "BHQ1",
            "modifications": [],
        }
        self.max_primer_pairs = 10
        self.n_cluster_pairs = 20
        self.specificity_settings = {
            "database": "nt",
            "entrez_query": "",
            "target_organism": "",
        }

    def open_mismatch_viewer(self):
        from gui.dialogs import MismatchDialog
        org_root = self._get_org_root()
        blast_dir = os.path.join(org_root, "BLAST")
        gene = self._current_gene_hint()
        start_dir = os.path.join(blast_dir, gene) if gene else blast_dir
        initial_path = os.path.join(start_dir, f"{gene}_general_summary.xlsx") if gene else ""
        dlg = MismatchDialog(
            self,
            start_dir=start_dir if os.path.isdir(start_dir) else blast_dir,
            initial_path=initial_path if os.path.isfile(initial_path) else "",
        )
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

    def open_primer_settings(self, focus_tab=None):
        if isinstance(focus_tab, bool):
            focus_tab = None
        from gui.dialogs import PrimerSettingsDialog
        preset_params = self._get_selected_preset_params()
        dlg = PrimerSettingsDialog(
            current_settings=getattr(self, 'custom_primer_settings', None),
            preset_params=preset_params,
            current_probe_settings=getattr(self, 'custom_probe_settings', None),
            parent=self,
        )
        if focus_tab and hasattr(dlg, "tabs"):
            needle = str(focus_tab).lower()
            for i in range(dlg.tabs.count()):
                if needle in dlg.tabs.tabText(i).lower():
                    dlg.tabs.setCurrentIndex(i)
                    break
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
            self.custom_probe_settings = dlg.get_probe_settings()
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
                f"Cluster pairs: {self.n_cluster_pairs}, "
                f"Probe mode: {self.custom_probe_settings.get('mode', 'off')}")

    def open_probe_settings(self, checked=False):
        self.open_primer_settings("probe")
            
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

        selected_genes = self._select_current_org_genes(
            "Select Gene Folders for BLAST Mismatch Analysis",
            default_all=False,
        )
        if not selected_genes:
            return

        fasta_files = []
        for gene in selected_genes:
            gene_root = os.path.join(genes_root, gene)
            if os.path.exists(gene_root):
                for root, dirs, files in os.walk(gene_root):
                    for f in files:
                        if f.endswith(".fasta"):
                            fasta_files.append(os.path.join(root, f))
        
        if not fasta_files:
            self.log_message(f"No FASTA files found in {genes_root}")
            return

        # Params
        db = self.combo_db.currentText()
        limit_mode = self.combo_limit.currentText()
        excluded_species = [
            s.strip()
            for s in re.split(r"[;\n,]+", self.le_complex_species.text())
            if s.strip()
        ]
        
        self.log_message(f"Starting BLAST analysis ({db}) for {len(fasta_files)} files in {len(selected_genes)} selected gene folder(s)...")
        self.btn_run_blast.setEnabled(False)
        
        analyzer = BlastAnalyzer(context.email or "user@example.com", context.api_key)
        
        def run_analysis():
            if limit_mode == "Clade / Species Complex" and excluded_species:
                from Bio import Entrez
                Entrez.email = context.email or "user@example.com"
                missing = []
                for name in excluded_species:
                    handle = Entrez.esearch(db="taxonomy", term=f'"{name}"[Scientific Name]')
                    rec = Entrez.read(handle)
                    handle.close()
                    if not rec.get("IdList"):
                        missing.append(name)
                if missing:
                    raise ValueError(
                        "Could not verify species in NCBI Taxonomy: "
                        + "; ".join(missing)
                    )
            return analyzer.run_analysis(
                fasta_files, target_org, 0, ws,
                max_hits=200, megablast=True, db=db, force=False,
                limit=limit_mode, excluded_species=excluded_species,
            )
            
        def on_blast_done(results):
            self.log_message(f"Analysis complete. Processed {len(results)} files.")
            self.btn_run_blast.setEnabled(True)
            self.log_message(f"Results saved in {ws}/{safe_org}/BLAST/")
            # Auto-map: load reference and top-10 clusters
            self.map_mismatches_and_clusters(genes=selected_genes, prompt=False)

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

        tools_menu = menubar.addMenu("Tools")
        ac_prefs = QAction("Preferences", self)
        ac_prefs.triggered.connect(self.open_settings)
        tools_menu.addAction(ac_prefs)
        ac_probe_settings = QAction("Probe Design Settings", self)
        ac_probe_settings.triggered.connect(self.open_probe_settings)
        tools_menu.addAction(ac_probe_settings)
        ac_design_probes = QAction("Design Probes", self)
        ac_design_probes.triggered.connect(self.on_design_probes)
        tools_menu.addAction(ac_design_probes)
        ac_primer_view = QAction("Open Primer Table Viewer", self)
        ac_primer_view.triggered.connect(self.open_primer_table_viewer)
        tools_menu.addAction(ac_primer_view)
        ac_spec_view = QAction("Open Specificity Report Viewer", self)
        ac_spec_view.triggered.connect(self.open_specificity_report_viewer)
        tools_menu.addAction(ac_spec_view)

        # Map menu
        map_menu = menubar.addMenu("Map")
        ac_map_mm = QAction("Map Mismatches && Clusters", self)
        ac_map_mm.triggered.connect(self.map_mismatches_and_clusters)
        map_menu.addAction(ac_map_mm)

        ac_map_pr = QAction("Map Primers && Amplicons", self)
        ac_map_pr.triggered.connect(self.map_primers_and_amplicons)
        map_menu.addAction(ac_map_pr)
        ac_map_probe = QAction("Map Probes", self)
        ac_map_probe.triggered.connect(self.map_probes)
        map_menu.addAction(ac_map_probe)

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

    def open_settings(self):
        try:
            from gui.settings_dialog import SettingsDialog
            dlg = SettingsDialog(self)
            if dlg.exec():
                self.sp_per_cluster.setValue(dlg.sp_fastas.value())
                self.log_message("Preferences saved.")
        except Exception as e:
            self.log_message(f"Could not open preferences: {e}")

    def open_primer_table_viewer(self):
        try:
            from gui.report_viewers import PrimerTableViewer
            viewer = PrimerTableViewer(self._get_org_root(), self)
            viewer.show()
            self._last_primer_viewer = viewer
        except Exception as e:
            self.log_message(f"Could not open primer viewer: {e}")

    def open_specificity_report_viewer(self):
        try:
            from gui.report_viewers import SpecificityReportViewer
            viewer = SpecificityReportViewer(os.path.join(self._get_org_root(), "Primer-BLAST"), self)
            viewer.show()
            self._last_specificity_viewer = viewer
        except Exception as e:
            self.log_message(f"Could not open specificity viewer: {e}")

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
        map_menu.addAction("Probes", self.map_probes)
        map_menu.addSeparator()
        map_menu.addAction("Map All", self.map_all)
        btn_map.setMenu(map_menu)
        btn_map.setPopupMode(QToolButton.InstantPopup)
        tb.addWidget(btn_map)

        tb.addSeparator()

        btn_seq = QToolButton()
        btn_seq.setText("Sequence ▾")
        seq_menu = QMenu(btn_seq)
        seq_menu.addAction("Edit", lambda: self.current_viewer.edit_sequence() if self.current_viewer else None)
        seq_menu.addAction("Save FASTA", lambda: self.current_viewer.save_fasta() if self.current_viewer else None)
        seq_menu.addAction("Validate", lambda: self.current_viewer.validate_sequence(True) if self.current_viewer else None)
        seq_menu.addSeparator()
        seq_menu.addAction("Reverse Complement", lambda: self.current_viewer.reverse_complement() if self.current_viewer else None)
        seq_menu.addAction("Translate Selection", lambda: self.current_viewer.translate_selection() if self.current_viewer else None)
        seq_menu.addAction("Trim to Selection", lambda: self.current_viewer.trim_to_selection() if self.current_viewer else None)
        seq_menu.addAction("Find IUPAC Motif", lambda: self.current_viewer.find_iupac_motif() if self.current_viewer else None)
        btn_seq.setMenu(seq_menu)
        btn_seq.setPopupMode(QToolButton.InstantPopup)
        tb.addWidget(btn_seq)

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
        elif os.path.isfile(path):
            self._open_editor(path)

    def _open_editor(self, path):
        try:
            from gui.editor_widget import FileEditorTab
            tab_name = os.path.basename(path)
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == tab_name:
                    self.tabs.setCurrentIndex(i)
                    return
            tab = FileEditorTab(path, self)
            idx = self.tabs.addTab(tab, tab_name)
            self.tabs.setCurrentIndex(idx)
        except Exception as e:
            self.log_message(f"Could not open editor: {e}")
            
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
                sv.load_sequence(seq, source_path=path)
                
                self.current_seq = seq
                self.log_message(f"Loaded: {os.path.basename(path)}")
            else:
                self.log_message(f"Invalid FASTA: {path}")
        except Exception as e:
            self.log_message(f"Error loading file: {e}")

    def _load_fastas_for_genes(self, genes, max_tabs=100):
        org_root = self._get_org_root()
        genes_root = os.path.join(org_root, "Genes")
        opened = 0
        total = 0
        for gene in genes:
            gene_dir = os.path.join(genes_root, gene)
            if not os.path.isdir(gene_dir):
                safe_gene = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(gene)).strip("_")
                gene_dir = os.path.join(genes_root, safe_gene)
            if not os.path.isdir(gene_dir):
                continue
            paths = sorted(glob.glob(os.path.join(gene_dir, "*.fa*")))
            total += len(paths)
            for path in paths:
                if opened >= max_tabs:
                    continue
                self.load_sequence(path)
                opened += 1
        if total:
            self.log_message(f"Loaded {opened} of {total} downloaded FASTA file(s) into sequence tabs.")
            if opened < total:
                self.log_message(f"Remaining FASTAs are visible in the Files dock under {genes_root}.")

    def on_search_loci(self):
        query = self.le_organism.text()
        if not query: return
        gene_query = self.le_gene_query.text().strip() if hasattr(self, "le_gene_query") else ""
        deep_parse = QSettings("Primery", "Primery").value("analysis/deepParse", "false") == "true"
        
        suffix = f" / {gene_query}" if gene_query else ""
        self.log_message(f"Searching loci for {query}{suffix}...")
        self.btn_search.setEnabled(False)
        
        def on_done(res):
            self.populate_loci_table(res)
            self.log_message(f"Found {len(res)} clusters.")
            self.btn_search.setEnabled(True)
            
        self.run_worker(
            self.downloader.p_search_loci_candidates,
            on_done,
            query,
            limit=100,
            gene_keyword=gene_query,
            deep_parse=deep_parse,
        )
            
    def populate_loci_table(self, data):
        self.table_loci.setRowCount(0)
        self.table_loci.setSortingEnabled(False)
        for row in data:
            r = self.table_loci.rowCount()
            self.table_loci.insertRow(r)
            
            canonical = row.get("canonical") or row.get("title", "").split(" (")[0]
            aliases = row.get("aliases") or []
            if isinstance(aliases, str):
                alias_text = aliases
            else:
                alias_text = ", ".join(aliases)
            per_cluster = self.sp_per_cluster.value() if hasattr(self, "sp_per_cluster") else 10

            # Canonical item with checkbox and row metadata.
            item_title = QTableWidgetItem(canonical)
            item_title.setFlags(item_title.flags() | Qt.ItemIsUserCheckable)
            item_title.setCheckState(Qt.Unchecked)
            item_title.setToolTip(row.get("title", canonical))
            item_title.setData(Qt.UserRole, row)
            
            self.table_loci.setItem(r, 0, item_title)
            self.table_loci.setItem(r, 1, QTableWidgetItem(alias_text))
            self.table_loci.setItem(r, 2, QTableWidgetItem(str(row.get('count', 0))))
            self.table_loci.setItem(r, 3, QTableWidgetItem(str(per_cluster)))
            self.table_loci.setItem(r, 4, QTableWidgetItem(row.get('accession', '')))
        self.table_loci.setSortingEnabled(True)

    def _locus_config_from_row(self, row_index):
        item = self.table_loci.item(row_index, 0)
        if not item:
            return None
        row_data = item.data(Qt.UserRole) or {}
        canonical = row_data.get("canonical") or item.text().split(" (")[0]
        terms = row_data.get("search_terms") or [canonical]
        if isinstance(terms, str):
            terms = [terms]
        terms = [str(t).strip() for t in terms if str(t).strip()]
        if canonical not in terms:
            terms.insert(0, canonical)

        per_cluster_item = self.table_loci.item(row_index, 3)
        try:
            per_cluster = int(per_cluster_item.text()) if per_cluster_item else self.sp_per_cluster.value()
        except (TypeError, ValueError):
            per_cluster = self.sp_per_cluster.value()
        per_cluster = max(1, min(500, per_cluster))
        return {
            "canonical": canonical,
            "terms": terms,
            "per_cluster": per_cluster,
        }

    def on_download_loci(self):
        # Determine selection by Checkboxes
        selected_items = []
        for r in range(self.table_loci.rowCount()):
            item = self.table_loci.item(r, 0)
            if item and item.checkState() == Qt.Checked:
                cfg = self._locus_config_from_row(r)
                if cfg:
                    selected_items.append(cfg)
        
        # Fallback to selected rows if no checkboxes are checked (UX convenience)
        if not selected_items:
            rows = self.table_loci.selectionModel().selectedRows()
            for r in rows:
                cfg = self._locus_config_from_row(r.row())
                if cfg:
                    selected_items.append(cfg)

        if not selected_items:
            self.log_message("No loci selected (use checkboxes).")
            return
            
        self.log_message(f"Downloading {[x['canonical'] for x in selected_items]}...")
        
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
            # Workspace
            ws = self.le_ws.text()
            
            # Run
            download_results = []
            for item in selected_items:
                loci_config = {
                    item["canonical"]: {
                        'search_terms': item["terms"],
                        'verify_terms': item["terms"],
                    }
                }
                result = self.downloader.fetch_loci(
                    taxid,
                    self.le_organism.text(),
                    loci_config,
                    ws,
                    n_per_locus=item["per_cluster"],
                    return_stats=True,
                )
                download_results.append(result)
            return {
                "genes": [item["canonical"] for item in selected_items],
                "results": download_results,
            }

        def on_download_done(res):
            if isinstance(res, str):
                self.log_message(res)
                return
            if not isinstance(res, dict):
                self.log_message(f"Download complete: {res}")
                return

            for result in res.get("results", []):
                if not isinstance(result, dict):
                    self.log_message(f"Download complete: {result}")
                    continue
                self.log_message(f"Download manifest: {result.get('manifest', '')}")
                self.log_message(f"Download summary: {result.get('summary', '')}")
                for locus, stats in result.get("stats", {}).items():
                    self.log_message(
                        f"{locus}: requested {stats.get('requested', 0)}, "
                        f"found {stats.get('found_uids', 0)}, "
                        f"valid length {stats.get('valid_length', 0)}, "
                        f"downloaded {stats.get('downloaded', 0)}, "
                        f"skipped QC {stats.get('skipped_qc', 0)}, "
                        f"errors {stats.get('errors', 0)}"
                    )
            safe_genes = []
            for result in res.get("results", []):
                if isinstance(result, dict):
                    for stats in result.get("stats", {}).values():
                        safe_genes.append(stats.get("safe_locus") or stats.get("locus", ""))
            self.fs_model.setRootPath(self.le_ws.text())
            self.tree.setRootIndex(self.fs_model.index(self.le_ws.text()))
            self._load_fastas_for_genes(safe_genes or res.get("genes", []))

        self.run_worker(resolve_and_download, on_download_done)

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

    def _current_org_key(self):
        org = self.le_organism.text().strip().replace(" ", "_")
        if org:
            return org

        ws = self.le_ws.text().strip()
        candidate_paths = []
        try:
            idx = self.tree.currentIndex()
            if idx.isValid():
                candidate_paths.append(self.fs_model.filePath(idx))
        except Exception:
            pass
        try:
            widget = self.tabs.currentWidget()
            source_path = getattr(widget, "source_path", "")
            if source_path:
                candidate_paths.append(source_path)
        except Exception:
            pass

        if ws:
            for path in candidate_paths:
                try:
                    rel = os.path.relpath(path, ws)
                except ValueError:
                    continue
                if rel.startswith(".."):
                    continue
                first = rel.split(os.sep, 1)[0]
                if first and first not in {".", ".."}:
                    org_root = os.path.join(ws, first)
                    if os.path.isdir(os.path.join(org_root, "Genes")) or os.path.isdir(os.path.join(org_root, "BLAST")):
                        self.le_organism.setText(first)
                        return first

            if os.path.isdir(ws):
                candidates = []
                with os.scandir(ws) as it:
                    for entry in it:
                        if not entry.is_dir() or entry.name.startswith("."):
                            continue
                        if (os.path.isdir(os.path.join(entry.path, "Genes")) or
                                os.path.isdir(os.path.join(entry.path, "BLAST"))):
                            candidates.append(entry.name)
                if candidates:
                    best = sorted(candidates)[0]
                    self.le_organism.setText(best)
                    return best

        return ""

    def _current_gene_hint(self):
        tab_name = self.tabs.tabText(self.tabs.currentIndex()) if self.tabs.count() else ""
        org_root = self._get_org_root()
        blast_dir = os.path.join(org_root, "BLAST")
        genes_dir = os.path.join(org_root, "Genes")
        candidates = []
        for root in (blast_dir, genes_dir):
            if os.path.isdir(root):
                candidates.extend(
                    d for d in os.listdir(root)
                    if os.path.isdir(os.path.join(root, d))
                )
        if tab_name in candidates:
            return tab_name
        for gene in candidates:
            if tab_name.startswith(gene + "__") or tab_name.startswith(gene + "_"):
                return gene
        return ""

    def _select_current_org_genes(
        self,
        title,
        require_cluster_meta=False,
        require_primers=False,
        require_probes=False,
        default_all=False,
    ):
        ws = self.le_ws.text().strip()
        org = self._current_org_key()
        if not ws or not org:
            self.log_message("Set workspace and organism first.")
            return []

        checked = []
        hint = self._current_gene_hint()
        if hint:
            checked.append(hint)

        from gui.selection_dialog import SelectionDialog
        dlg = SelectionDialog(
            ws,
            title,
            self,
            organism_filter=org,
            checked_genes=checked,
            default_checked=default_all,
        )
        if not dlg.exec():
            return []

        selected = []
        for sel in dlg.selections:
            if sel.get("organism") == org:
                selected.extend(sel.get("genes", []))

        selected = sorted(set(selected))
        if not selected:
            self.log_message("No genes selected for current organism.")
            return []

        blast_dir = os.path.join(ws, org, "BLAST")
        filtered = []
        for gene in selected:
            gene_dir = os.path.join(blast_dir, gene)
            ok = True
            if require_cluster_meta:
                ok = ok and os.path.isfile(os.path.join(gene_dir, f"{gene}_cluster_meta.json"))
            if require_primers:
                ok = ok and bool(glob.glob(os.path.join(gene_dir, "*_primers.json")))
            if require_probes:
                ok = ok and bool(glob.glob(os.path.join(gene_dir, "Probes", "**", "*_probes.json"), recursive=True))
            if ok:
                filtered.append(gene)
            else:
                self.log_message(f"Skipping {gene}: required analysis files are missing.")
        return filtered

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


        selected_genes = self._select_current_org_genes(
            "Select Genes for Primer Design",
            require_cluster_meta=True,
            default_all=False,
        )
        if not selected_genes:
            return

        meta_files = [
            os.path.join(blast_root, gene, f"{gene}_cluster_meta.json")
            for gene in selected_genes
        ]
        meta_files = [path for path in meta_files if os.path.isfile(path)]
        if not meta_files:
            self.log_message("No cluster metadata found. Run BLAST analysis first.")
            return

        from core.primer_designer import PrimerDesigner
        designer = PrimerDesigner()
        mode = self.combo_preset.currentText().split(" ")[0]

        self.log_message(f"Designing {mode} primers for {len(meta_files)} selected gene(s)...")
        self.btn_design.setEnabled(False)

        def run_design():
            all_results = []
            contexts = {}
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
                require_3p = True if custom is None else bool(custom.get("PRIMERY_REQUIRE_3PRIME_MM", True))
                three_prime_window = 3 if custom is None else int(custom.get("PRIMERY_THREE_PRIME_WINDOW", 3))
                contexts[gene] = {
                    "seq": seq,
                    "clusters": clusters,
                    "fasta_path": fasta_path,
                    "mode": mode.lower(),
                }
                pairs = designer.design_primers_from_clusters(
                    seq, mode=mode, clusters=clusters,
                    n_per_pair=50, n_top=n_top,
                    n_cluster_pairs=n_cpairs,
                    custom_settings=custom,
                    require_3prime_mm=require_3p,
                    three_prime_window=three_prime_window,
                )
                for p in pairs:
                    p["gene"] = gene
                    p["method"] = mode.lower()
                    p["ref_fasta"] = os.path.basename(fasta_path)
                    p["ref_len"] = len(seq)

                all_results.extend(pairs)
            return {"pairs": all_results, "contexts": contexts}

        def on_design_done(payload):
            if isinstance(payload, dict):
                pairs = payload.get("pairs", [])
                contexts = payload.get("contexts", {})
            else:
                pairs = payload
                contexts = {}
            self.log_message(f"Designed {len(pairs)} primer pairs total.")
            self.btn_design.setEnabled(True)

            if pairs:
                self._show_primer_results(pairs)
                self._save_primers_xlsx(pairs)
            else:
                self.log_message("No primers found. Check BLAST clusters.")

            probe_mode = getattr(self, "custom_probe_settings", {}).get("mode", "fallback")
            if probe_mode == "always" or (probe_mode == "fallback" and not pairs):
                probes = self._design_and_save_probes(contexts, pairs, reason="primer_design")
                if probes:
                    self._show_probe_results(probes)
                    self.map_probes(genes=contexts.keys(), prompt=False)

            # Map results to viewers (supports multi-tab)
            if pairs:
                self.map_primers_and_amplicons(genes=contexts.keys(), prompt=False)

        self.run_worker(run_design, on_design_done)

    def on_design_probes(self, checked=False):
        ws = self.le_ws.text().strip()
        target_org = self.le_organism.text().strip()
        if not ws or not target_org:
            self.log_message("Set workspace and organism first.")
            return

        safe_org = target_org.replace(" ", "_")
        blast_root = os.path.join(ws, safe_org, "BLAST")
        if not os.path.isdir(blast_root):
            self.log_message(f"No BLAST results found at {blast_root}. Run mismatch analysis first.")
            return

        selected_genes = self._select_current_org_genes(
            "Select Genes for Probe Design",
            require_cluster_meta=True,
            default_all=False,
        )
        if not selected_genes:
            return

        contexts = self._contexts_from_genes(selected_genes)
        if not contexts:
            self.log_message("No probe-ready gene contexts found. Run BLAST analysis and clustering first.")
            return

        probe_settings = getattr(self, "custom_probe_settings", {})
        chemistry = probe_settings.get("chemistry", "taqman")
        self.log_message(
            f"Designing {chemistry} probes for {len(contexts)} selected gene(s)..."
        )

        if hasattr(self, "btn_design_probes"):
            self.btn_design_probes.setEnabled(False)
        try:
            probes = self._design_and_save_probes(
                contexts,
                pairs=[],
                reason="manual_probe_design",
                force=True,
            )
        finally:
            if hasattr(self, "btn_design_probes"):
                self.btn_design_probes.setEnabled(True)

        if probes:
            self._show_probe_results(probes)
            self.log_message(f"Designed {len(probes)} probes total.")
            self.map_probes(genes=selected_genes, prompt=False)
        else:
            self.log_message("No probes found. Check mismatch clusters and probe settings.")

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
            "Fwd MM", "Rev MM", "Fwd 3p", "Rev 3p", "Forward", "Reverse",
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
                str(p.get("fwd_3p_mm_offset", "")),
                str(p.get("rev_3p_mm_offset", "")),
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
        """Save primer pairs to {Organism}/Primers/ as per-gene XLSX/JSON files."""
        if not pairs:
            return
        try:
            from collections import defaultdict
            from openpyxl import Workbook
            from openpyxl.styles import Font as XlFont, PatternFill

            ws_path = self.le_ws.text()
            org = self.le_organism.text().replace(" ", "_")
            primer_dir = os.path.join(ws_path, org, "Primers")
            os.makedirs(primer_dir, exist_ok=True)
            mode = self.combo_preset.currentText().split(" ")[0].lower()

            pairs_by_gene = defaultdict(list)
            for p in pairs:
                gene = str(p.get("gene") or "unknown")
                p.setdefault("method", mode)
                pairs_by_gene[gene].append(p)

            headers = [
                "Rank", "Gene", "Fwd Cluster", "Rev Cluster",
                "Score", "Species", "Fwd Mismatches", "Rev Mismatches",
                "Fwd 3p Mismatch Offset", "Rev 3p Mismatch Offset",
                "Forward Seq", "Reverse Seq",
                "Fwd Tm (°C)", "Rev Tm (°C)", "Product (bp)",
                "Fwd Pos", "Fwd Len", "Rev Pos", "Rev Len",
                "Hairpin (F/R)", "Dimer (F/R)", "Thermal Penalty",
            ]
            hdr_font = XlFont(bold=True, color="FFFFFF")
            hdr_fill = PatternFill("solid", fgColor="2C3E50")

            for gene, gene_pairs in pairs_by_gene.items():
                out_path = os.path.join(primer_dir, f"{gene}_{mode}_primers.xlsx")
                wb = Workbook()
                ws = wb.active
                ws.title = "Primer Pairs"

                for c, h in enumerate(headers, 1):
                    cell = ws.cell(row=1, column=c, value=h)
                    cell.font = hdr_font
                    cell.fill = hdr_fill

                for i, p in enumerate(gene_pairs):
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
                        p.get("fwd_3p_mm_offset", ""),
                        p.get("rev_3p_mm_offset", ""),
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

                # Also save JSON for map_primers_and_amplicons/report generation.
                json_path = os.path.join(
                    ws_path, org, "BLAST", gene, f"{gene}_{mode}_primers.json"
                )
                os.makedirs(os.path.dirname(json_path), exist_ok=True)
                import json as _jjson
                with open(json_path, "w", encoding="utf-8") as jf:
                    _jjson.dump(gene_pairs, jf, indent=2, default=str)

        except Exception as e:
            self.log_message(f"Error saving primers XLSX: {e}")

    def _contexts_from_genes(self, genes):
        org_root = self._get_org_root()
        blast_dir = os.path.join(org_root, "BLAST")
        genes_dir = os.path.join(org_root, "Genes")
        contexts = {}
        for gene in sorted(set(g for g in genes if g)):
            meta_path = os.path.join(blast_dir, gene, f"{gene}_cluster_meta.json")
            if not os.path.isfile(meta_path):
                continue
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                fasta_path = meta.get("longest_fasta", {}).get("path", "")
                if not fasta_path or not os.path.exists(fasta_path):
                    fasta_path, _ = self._find_longest_fasta(os.path.join(genes_dir, gene))
                if not fasta_path:
                    continue
                with open(fasta_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                seq = "".join(l.strip() for l in lines if not l.startswith(">"))
                contexts[gene] = {
                    "seq": seq,
                    "clusters": meta.get("clusters", []),
                    "fasta_path": fasta_path,
                    "mode": self.combo_preset.currentText().split(" ")[0].lower(),
                }
            except Exception as e:
                self.log_message(f"Could not prepare probe context for {gene}: {e}")
        return contexts

    def _design_and_save_probes(self, contexts, pairs=None, reason="manual", force=False):
        probe_settings = getattr(self, "custom_probe_settings", {})
        if not force and probe_settings.get("mode", "off") == "off":
            return []
        try:
            from core.probe_designer import design_probes
        except Exception as e:
            self.log_message(f"Probe designer unavailable: {e}")
            return []

        pairs = pairs or []
        pairs_by_gene = {}
        for p in pairs:
            pairs_by_gene.setdefault(p.get("gene", ""), []).append(p)

        all_probes = []
        org = self.le_organism.text().replace(" ", "_")
        ws_path = self.le_ws.text()
        chemistry = probe_settings.get("chemistry", "taqman")
        for gene, ctx in contexts.items():
            gene_pairs = pairs_by_gene.get(gene) or [None]
            gene_probes = []
            for pair in gene_pairs[:3]:
                probes = design_probes(
                    ctx.get("seq", ""),
                    ctx.get("clusters", []),
                    chemistry=chemistry,
                    fwd_primer=pair,
                    rev_primer=pair,
                    dye=probe_settings.get("dye", "FAM"),
                    quencher=probe_settings.get("quencher", "BHQ1"),
                    modifications=probe_settings.get("modifications", []),
                    n_top=5,
                )
                for pr in probes:
                    pr["gene"] = gene
                    pr["method"] = ctx.get("mode", self.combo_preset.currentText().split(" ")[0].lower())
                    pr["source_reason"] = reason
                    if pair:
                        pr["primer_rank"] = pair.get("global_rank")
                gene_probes.extend(probes)

            # Deduplicate by start/end/chemistry and keep best ranked probes.
            by_key = {}
            for pr in gene_probes:
                key = (pr.get("chemistry"), pr.get("start"), pr.get("end"))
                if key not in by_key or pr.get("score", 0) > by_key[key].get("score", 0):
                    by_key[key] = pr
            gene_probes = sorted(by_key.values(), key=lambda x: (-x.get("score", 0), x.get("start", 0)))[:10]
            for i, pr in enumerate(gene_probes, 1):
                pr["rank"] = i
            if not gene_probes:
                continue

            out_dir = os.path.join(ws_path, org, "BLAST", gene, "Probes", chemistry)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{gene}_{chemistry}_probes.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(gene_probes, f, indent=2, ensure_ascii=False, default=str)
            self._save_probe_order_files(gene, chemistry, gene_probes, out_dir)
            self.log_message(f"Probes saved to {out_path}")
            all_probes.extend(gene_probes)
        return all_probes

    def _save_probe_order_files(self, gene, chemistry, probes, out_dir):
        headers = [
            "rank", "gene", "chemistry", "dye", "quencher", "modifications",
            "formatted_sequence", "core_sequence", "sequence", "start", "end",
            "length", "tm", "gc", "mm_covered", "mismatch_positions",
            "lna_count", "lna_positions", "lna_design_note",
            "n_species", "species", "score", "rationale",
        ]
        rows = []
        for pr in probes:
            row = {}
            for h in headers:
                value = pr.get(h, "")
                if isinstance(value, list):
                    value = "; ".join(str(x) for x in value)
                row[h] = value
            row["gene"] = gene
            rows.append(row)

        import csv
        csv_path = os.path.join(out_dir, f"{gene}_{chemistry}_probes.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "probes"
        ws.append(headers)
        for row in rows:
            ws.append([row[h] for h in headers])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            letter = col[0].column_letter
            width = min(max(len(str(c.value or "")) for c in col) + 2, 70)
            ws.column_dimensions[letter].width = width
        wb.save(os.path.join(out_dir, f"{gene}_{chemistry}_probes.xlsx"))

        fasta_path = os.path.join(out_dir, f"{gene}_{chemistry}_probes.fasta")
        with open(fasta_path, "w", encoding="utf-8") as f:
            for pr in probes:
                name = f"{gene}_{chemistry}_probe_{pr.get('rank', '?')}"
                f.write(f">{name} {pr.get('formatted_sequence', '')}\n")
                seq = pr.get("formatted_sequence") or pr.get("core_sequence") or pr.get("sequence", "")
                for i in range(0, len(seq), 80):
                    f.write(seq[i:i + 80] + "\n")

    def _probe_files_for_gene(self, gene):
        org_root = self._get_org_root()
        gene_blast = os.path.join(org_root, "BLAST", gene)
        nested = glob.glob(os.path.join(gene_blast, "Probes", "**", f"{gene}_*_probes.json"), recursive=True)
        flat = glob.glob(os.path.join(gene_blast, f"{gene}_*_probes.json"))
        chosen = {}
        for path in sorted(flat):
            chosen[os.path.basename(path)] = path
        for path in sorted(nested):
            chosen[os.path.basename(path)] = path
        return list(chosen.values())

    def _load_probes_by_gene(self, genes):
        probes_by_gene = {}
        for gene in sorted(set(g for g in genes if g)):
            items = []
            for path in self._probe_files_for_gene(gene):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, list):
                        items.extend(loaded)
                except Exception as e:
                    self.log_message(f"Could not load probes for {gene}: {e}")
            probes_by_gene[gene] = sorted(items, key=lambda p: (p.get("rank", 999), -p.get("score", 0)))
        return probes_by_gene

    def _show_probe_results(self, probes):
        if not hasattr(self, "dock_probes"):
            self.dock_probes = QDockWidget("Probe Results", self)
            self.dock_probes.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
            self.probe_table = QTableWidget()
            self.dock_probes.setWidget(self.probe_table)
            self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_probes)

        headers = ["Rank", "Gene", "Chemistry", "Dye", "Quencher", "Mods",
                   "Formatted", "Sequence", "Tm", "GC", "Pos", "MM", "Species", "Score"]
        t = self.probe_table
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setRowCount(0)
        for pr in probes:
            r = t.rowCount()
            t.insertRow(r)
            vals = [
                pr.get("rank", ""),
                pr.get("gene", ""),
                pr.get("chemistry", ""),
                pr.get("dye", ""),
                pr.get("quencher", ""),
                ", ".join(pr.get("modifications", [])),
                pr.get("formatted_sequence", ""),
                pr.get("sequence", ""),
                pr.get("tm", ""),
                pr.get("gc", ""),
                f"{pr.get('start', 0) + 1}-{pr.get('end', 0) + 1}",
                pr.get("mm_covered", ""),
                pr.get("n_species", ""),
                pr.get("score", ""),
            ]
            for c, v in enumerate(vals):
                t.setItem(r, c, QTableWidgetItem(str(v)))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.dock_probes.show()

    def load_primers_for_specificity(self):
        """Load designed primers from workspace for specificity check."""
        ws = self.le_ws.text()
        
        # --- Selection Dialog ---
        from gui.selection_dialog import SelectionDialog
        dlg = SelectionDialog(
            ws,
            "Select Primers for Specificity",
            self,
            organism_filter=self._current_org_key(),
            checked_genes=[self._current_gene_hint()] if self._current_gene_hint() else [],
            default_checked=False,
        )
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
                        method = ""
                        m = re.match(
                            rf"^{re.escape(gene)}_(.+?)_primers\.json$",
                            os.path.basename(pf),
                        )
                        if m:
                            method = m.group(1)
                        # Add to list
                        for p in pairs:
                            p.setdefault("gene", gene)
                            if method:
                                p.setdefault("method", method)
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
            self.load_primers_for_specificity()
            primers = getattr(self, "loaded_specificity_primers", [])
            if not primers:
                self.log_message("No primers selected for specificity check.")
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
            try:
                from core.probe_specificity import classify_primer_probe_specificity
                genes = [r.get("gene", "") for r in results]
                probes_by_gene = self._load_probes_by_gene(genes)
                results = classify_primer_probe_specificity(
                    results, probes_by_gene, target_organism=target_org
                )
                combined_path = os.path.join(
                    output_dir,
                    f"PrimerProbeSpecificity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                )
                with open(combined_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
                self.log_message(f"Combined primer+probe specificity saved: {combined_path}")
            except Exception as e:
                self.log_message(f"Could not classify primer+probe specificity: {e}")
            self._show_specificity_results(results)
            probe_mode = getattr(self, "custom_probe_settings", {}).get("mode", "off")
            if probe_mode == "fallback" and not any(
                r.get("specificity_status") == "Species-Specific" for r in results
            ):
                genes = [r.get("gene", "") for r in results]
                contexts = self._contexts_from_genes(genes)
                probes = self._design_and_save_probes(contexts, results, reason="specificity_fallback")
                if probes:
                    self._show_probe_results(probes)
                    self.map_probes(genes=contexts.keys(), prompt=False)
                    self.log_message("Fallback probes designed because no Species-Specific primer pair was found.")
            try:
                from gui.report_viewers import SpecificityReportViewer
                output_dir = os.path.join(self._get_org_root(), "Primer-BLAST")
                viewer = SpecificityReportViewer(output_dir, self)
                viewer.show()
                self._last_specificity_viewer = viewer
            except Exception as e:
                self.log_message(f"Could not open specificity report viewer: {e}")
            
        self.run_worker(run_spec, on_done)

    def _show_specificity_results(self, results):
        if not hasattr(self, "dock_spec_res"):
            self.dock_spec_res = QDockWidget("Specificity Results", self)
            self.dock_spec_res.setAllowedAreas(Qt.BottomDockWidgetArea)
            self.spec_table = QTableWidget()
            self.dock_spec_res.setWidget(self.spec_table)
            self.addDockWidget(Qt.BottomDockWidgetArea, self.dock_spec_res)
            
        t = self.spec_table
        headers = [
            "Pair", "Forward", "Reverse", "Primer Status",
            "Assay Status", "Probe", "Probe Target", "Probe Blocked",
            "Probe Unblocked", "Unassessed", "Target Hits", "Off-Target Hits"
        ]
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
            t.setItem(r, 4, make_item(p.get('assay_specificity_status') or p.get('primer_probe_status', '')))
            t.setItem(r, 5, make_item(p.get('probe_sequence', '')))
            t.setItem(r, 6, make_item(p.get('probe_target_amplicon_hits', '')))
            t.setItem(r, 7, make_item(p.get('probe_offtarget_blocked', '')))
            t.setItem(r, 8, make_item(p.get('probe_offtarget_unblocked', '')))
            t.setItem(r, 9, make_item(p.get('probe_unassessed_amplicons', '')))
            t.setItem(r, 10, make_item(p.get('target_hits', 0)))
            t.setItem(r, 11, make_item(p.get('off_target_hits', 0)))
            
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

    def map_mismatches_and_clusters(self, genes=None, prompt=True):
        """Load reference FASTA and overlay mismatch heatmap + top-10 clusters."""
        if isinstance(genes, bool):
            genes = None
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

        if genes is None and prompt:
            selected_genes = set(self._select_current_org_genes(
                "Select Genes to Map",
                require_cluster_meta=True,
                default_all=False,
            ))
        else:
            selected_genes = set(genes or [])

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
                            if not row or row[0] is None:
                                continue
                            try:
                                pos = int(row[0])
                                count = int(row[3]) if len(row) > 3 and row[3] else 1
                            except (TypeError, ValueError):
                                continue
                            mm_data.append({
                                "pos": pos,
                                "count": max(count, 1),
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

    def map_primers_and_amplicons(self, genes=None, prompt=True):
        """Load primer results and map primers + amplicons onto the viewer."""
        if isinstance(genes, bool):
            genes = None
        current_org = self._current_org_key()
        org_root = self._get_org_root()
        blast_dir = os.path.join(org_root, "BLAST")

        # Find primer output JSON
        primer_files = glob.glob(os.path.join(blast_dir, "**", "*_primers.json"), recursive=True)
        if not primer_files:
            self.log_message("No primer output files found. Design primers first.")
            return

        if genes is None and prompt:
            selected_genes = set(self._select_current_org_genes(
                "Select Primers to Map",
                require_primers=True,
                default_all=False,
            ))
        else:
            selected_genes = set(genes or [])

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
                     "mismatch_positions": p.get("fwd_mismatch_positions", []),
                     "cluster_id": p.get("fwd_cluster_id", "?")},
                    pair_rank=rank,
                )
                r_start = p["right_pos"] - p["right_len"] + 1
                sv.add_primer(
                    r_start, p["right_len"], True,
                    {"seq": p.get("right", ""), "pos": r_start,
                     "len": p.get("right_len", 0), "tm": p.get("right_tm", 0),
                     "mm": p.get("rev_mm_covered", 0),
                     "mismatch_positions": p.get("rev_mismatch_positions", []),
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

    def map_probes(self, genes=None, prompt=True):
        if isinstance(genes, bool):
            genes = None

        if genes is None and prompt:
            selected_genes = set(self._select_current_org_genes(
                "Select Probes to Map",
                require_probes=True,
                default_all=False,
            ))
        else:
            selected_genes = set(genes or [])
        if not selected_genes:
            self.log_message("No genes selected for current organism.")
            return
        probe_files = []
        for gene in selected_genes:
            probe_files.extend(self._probe_files_for_gene(gene))
        if not probe_files:
            self.log_message("No probe output files found. Design probes first.")
            return

        total = 0
        modified_viewers = set()
        cleared_viewers = set()
        for pfile in probe_files:
            try:
                with open(pfile, "r", encoding="utf-8") as f:
                    probes = json.load(f)
            except Exception as e:
                self.log_message(f"Error reading probe results ({os.path.basename(pfile)}): {e}")
                continue
            file_gene = ""
            base = os.path.basename(pfile)
            for candidate in sorted(selected_genes, key=len, reverse=True):
                if base.startswith(f"{candidate}_"):
                    file_gene = candidate
                    break
            for pr in probes:
                gene = pr.get("gene") or file_gene
                if gene not in selected_genes:
                    continue
                sv = self.add_viewer_tab(gene, switch_to=False)
                if not sv.sequence:
                    ctx = self._contexts_from_genes([gene]).get(gene, {})
                    if ctx.get("seq"):
                        sv.load_sequence(ctx["seq"], source_path=ctx.get("fasta_path"))
                if sv not in cleared_viewers:
                    sv.clear_probes()
                    cleared_viewers.add(sv)
                sv.add_probe(
                    int(pr.get("start", 0)),
                    int(pr.get("length") or (int(pr.get("end", 0)) - int(pr.get("start", 0)) + 1)),
                    pr,
                )
                modified_viewers.add(sv)
                total += 1

        for sv in modified_viewers:
            sv.finish_annotations()
        self.log_message(f"Mapped {total} probes across {len(modified_viewers)} genes.")

    def map_all(self):
        """Map mismatches, clusters, primers, and amplicons in one go."""
        genes = self._select_current_org_genes(
            "Select Genes to Map",
            default_all=False,
        )
        if not genes:
            return
        self.map_mismatches_and_clusters(genes=genes, prompt=False)
        self.map_primers_and_amplicons(genes=genes, prompt=False)
        self.map_probes(genes=genes, prompt=False)

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
        gene_tag = "_".join(sel_gene for sel in selections for sel_gene in sel.get("genes", []))
        gene_tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", gene_tag)[:80] or "selected"

        try:
            if fmt in ("pdf", "both"):
                pdf_path = os.path.join(out_dir, f"Report_{gene_tag}_{timestamp}.pdf")
                generate_pdf(all_data, pdf_path, screenshot_path)
                self.log_message(f"PDF saved: {pdf_path}")

            if fmt in ("docx", "both"):
                docx_path = os.path.join(out_dir, f"Report_{gene_tag}_{timestamp}.docx")
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
