"""
dialogs.py

Dialogs for the Primery application.
Includes mismatch viewer and user-friendly advanced primer settings.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QComboBox,
    QFormLayout, QLineEdit, QFileDialog, QMessageBox, QHeaderView,
    QInputDialog, QGroupBox, QSpinBox, QDoubleSpinBox, QGridLayout,
    QTabWidget, QWidget, QCheckBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import json, os


# ═══════════════════════ Mismatch Dialog ════════════════════

class MismatchDialog(QDialog):
    def __init__(self, parent=None, start_dir="", initial_path=""):
        super().__init__(parent)
        self.setWindowTitle("Mismatch Analysis Viewer")
        self.resize(800, 600)
        self.start_dir = start_dir
        self.initial_path = initial_path

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.btn_load_general = QPushButton("Load General Summary")
        self.btn_load_file = QPushButton("Load Specific File")
        top.addWidget(self.btn_load_general)
        top.addWidget(self.btn_load_file)
        top.addStretch()
        layout.addLayout(top)

        self.table = QTableWidget()
        layout.addWidget(self.table)

        self.btn_load_general.clicked.connect(self.load_general)
        self.btn_load_file.clicked.connect(self.load_specific)
        if self.initial_path and os.path.exists(self.initial_path):
            self._load_data(self.initial_path)

    def load_general(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open General Summary", self.start_dir,
            "Excel Files (*.xlsx);;JSON (*.json)")
        if path:
            self._load_data(path)

    def load_specific(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Mismatch Summary", self.start_dir,
            "Excel Files (*.xlsx);;JSON (*.json)")
        if path:
            self._load_data(path)

    def _load_data(self, path):
        try:
            data = None
            if path.endswith(".xlsx"):
                from openpyxl import load_workbook
                wb = load_workbook(path, read_only=True, data_only=True)
                ws = wb.active
                rows_iter = ws.iter_rows(values_only=True)
                headers = [str(h or "") for h in next(rows_iter)]
                data = []
                for row in rows_iter:
                    record = {}
                    for i, h in enumerate(headers):
                        val = row[i] if i < len(row) else ""
                        record[h] = "" if val is None else val
                    data.append(record)
                wb.close()
            else:
                with open(path, 'r') as f:
                    data = json.load(f)

            if not data:
                return

            headers = list(data[0].keys())
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)
            self.table.setRowCount(0)

            for row in data:
                r = self.table.rowCount()
                self.table.insertRow(r)
                for c, h in enumerate(headers):
                    val = str(row.get(h, ""))
                    self.table.setItem(r, c, QTableWidgetItem(val))

            self.table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load: {e}")


# ═══════════════════════ Primer Settings ════════════════════

class PrimerSettingsDialog(QDialog):
    """
    User-friendly advanced primer settings.
    Groups parameters by category with clear labels.
    Supports loading preset values an updating live.
    """

    def __init__(self, current_settings=None, preset_params=None,
                 current_probe_settings=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Primer Design Settings")
        self.setMinimumSize(520, 520)

        self.settings = current_settings or {}
        self.probe_settings = current_probe_settings or {}

        main_layout = QVBoxLayout(self)

        # ── Tabs ──
        tabs = QTabWidget()
        self.tabs = tabs
        main_layout.addWidget(tabs)

        # --- Primer Size & Tm tab ---
        tab_primer = QWidget()
        l1 = QVBoxLayout(tab_primer)

        grp_size = QGroupBox("Primer Length (bp)")
        g1 = QGridLayout(grp_size)
        g1.addWidget(QLabel("Min:"), 0, 0)
        self.sp_min_size = QSpinBox()
        self.sp_min_size.setRange(10, 45)
        g1.addWidget(self.sp_min_size, 0, 1)
        g1.addWidget(QLabel("Optimal:"), 0, 2)
        self.sp_opt_size = QSpinBox()
        self.sp_opt_size.setRange(10, 45)
        g1.addWidget(self.sp_opt_size, 0, 3)
        g1.addWidget(QLabel("Max:"), 0, 4)
        self.sp_max_size = QSpinBox()
        self.sp_max_size.setRange(10, 45)
        g1.addWidget(self.sp_max_size, 0, 5)
        l1.addWidget(grp_size)

        grp_tm = QGroupBox("Melting Temperature (°C)")
        g2 = QGridLayout(grp_tm)
        g2.addWidget(QLabel("Min:"), 0, 0)
        self.sp_min_tm = QDoubleSpinBox()
        self.sp_min_tm.setRange(30, 85)
        self.sp_min_tm.setSingleStep(0.5)
        g2.addWidget(self.sp_min_tm, 0, 1)
        g2.addWidget(QLabel("Optimal:"), 0, 2)
        self.sp_opt_tm = QDoubleSpinBox()
        self.sp_opt_tm.setRange(30, 85)
        self.sp_opt_tm.setSingleStep(0.5)
        g2.addWidget(self.sp_opt_tm, 0, 3)
        g2.addWidget(QLabel("Max:"), 0, 4)
        self.sp_max_tm = QDoubleSpinBox()
        self.sp_max_tm.setRange(30, 85)
        self.sp_max_tm.setSingleStep(0.5)
        g2.addWidget(self.sp_max_tm, 0, 5)
        l1.addWidget(grp_tm)

        grp_gc = QGroupBox("GC Content (%)")
        g3 = QGridLayout(grp_gc)
        g3.addWidget(QLabel("Min:"), 0, 0)
        self.sp_min_gc = QDoubleSpinBox()
        self.sp_min_gc.setRange(0, 100)
        g3.addWidget(self.sp_min_gc, 0, 1)
        g3.addWidget(QLabel("Max:"), 0, 2)
        self.sp_max_gc = QDoubleSpinBox()
        self.sp_max_gc.setRange(0, 100)
        g3.addWidget(self.sp_max_gc, 0, 3)
        l1.addWidget(grp_gc)

        l1.addStretch()
        tabs.addTab(tab_primer, "Primer Size && Tm")

        # --- Product tab ---
        tab_product = QWidget()
        l2 = QVBoxLayout(tab_product)

        grp_prod = QGroupBox("Amplicon Product Size (bp)")
        gp = QGridLayout(grp_prod)
        gp.addWidget(QLabel("Min:"), 0, 0)
        self.sp_prod_min = QSpinBox()
        self.sp_prod_min.setRange(30, 5000)
        gp.addWidget(self.sp_prod_min, 0, 1)
        gp.addWidget(QLabel("Max:"), 0, 2)
        self.sp_prod_max = QSpinBox()
        self.sp_prod_max.setRange(30, 5000)
        gp.addWidget(self.sp_prod_max, 0, 3)
        l2.addWidget(grp_prod)

        grp_output = QGroupBox("Output")
        go = QGridLayout(grp_output)
        go.addWidget(QLabel("Max primer pairs:"), 0, 0)
        self.sp_max_pairs = QSpinBox()
        self.sp_max_pairs.setRange(1, 100)
        self.sp_max_pairs.setValue(10)
        go.addWidget(self.sp_max_pairs, 0, 1)
        go.addWidget(QLabel("Cluster pairs to evaluate:"), 1, 0)
        self.sp_cluster_pairs = QSpinBox()
        self.sp_cluster_pairs.setRange(1, 200)
        self.sp_cluster_pairs.setValue(20)
        go.addWidget(self.sp_cluster_pairs, 1, 1)
        l2.addWidget(grp_output)

        l2.addStretch()
        tabs.addTab(tab_product, "Product && Output")

        # --- Thermodynamics tab ---
        tab_thermo = QWidget()
        l3 = QVBoxLayout(tab_thermo)

        grp_thermo = QGroupBox("Thermodynamic Constraints")
        gt = QFormLayout(grp_thermo)
        self.sp_max_hairpin = QDoubleSpinBox()
        self.sp_max_hairpin.setRange(0, 80)
        self.sp_max_hairpin.setValue(47.0)
        gt.addRow("Max hairpin Tm (°C):", self.sp_max_hairpin)
        self.sp_max_dimer = QDoubleSpinBox()
        self.sp_max_dimer.setRange(0, 80)
        self.sp_max_dimer.setValue(47.0)
        gt.addRow("Max self-dimer Tm (°C):", self.sp_max_dimer)
        self.sp_max_compl = QDoubleSpinBox()
        self.sp_max_compl.setRange(0, 80)
        self.sp_max_compl.setValue(47.0)
        gt.addRow("Max pair complementarity Tm (°C):", self.sp_max_compl)
        l3.addWidget(grp_thermo)

        grp_salt = QGroupBox("Salt & Concentration")
        gs = QFormLayout(grp_salt)
        self.sp_na = QDoubleSpinBox()
        self.sp_na.setRange(0, 1000)
        self.sp_na.setValue(50.0)
        self.sp_na.setSuffix(" mM")
        gs.addRow("Na+ concentration:", self.sp_na)
        self.sp_mg = QDoubleSpinBox()
        self.sp_mg.setRange(0, 100)
        self.sp_mg.setValue(1.5)
        self.sp_mg.setSuffix(" mM")
        gs.addRow("Mg²+ concentration:", self.sp_mg)
        self.sp_dntp = QDoubleSpinBox()
        self.sp_dntp.setRange(0, 10)
        self.sp_dntp.setValue(0.6)
        self.sp_dntp.setSuffix(" mM")
        gs.addRow("dNTP concentration:", self.sp_dntp)
        l3.addWidget(grp_salt)

        l3.addStretch()
        tabs.addTab(tab_thermo, "Thermodynamics")

        # --- Specificity tab ---
        tab_spec = QWidget()
        l4 = QVBoxLayout(tab_spec)

        grp_blast = QGroupBox("Primer-BLAST Parameters")
        gb = QFormLayout(grp_blast)
        self.combo_spec_db = QComboBox()
        self.combo_spec_db.addItems([
            "nt (Nucleotide Collection)",
            "refseq_rna (RefSeq RNA)",
            "refseq_representative_genomes",
            "prokaryotic_refseq_genomes"
        ])
        gb.addRow("Database:", self.combo_spec_db)

        self.le_entrez_spec = QLineEdit()
        self.le_entrez_spec.setPlaceholderText("e.g. fungi[organism]")
        gb.addRow("Entrez Query:", self.le_entrez_spec)

        self.le_target_org = QLineEdit()
        self.le_target_org.setPlaceholderText("e.g. Fusarium nanum")
        gb.addRow("Target Organism:", self.le_target_org)

        l4.addWidget(grp_blast)

        grp_3p = QGroupBox("3' mismatch placement")
        g3p = QFormLayout(grp_3p)
        self.chk_require_3p = QCheckBox("Require mismatch near each primer 3' end")
        self.chk_require_3p.setChecked(True)
        g3p.addRow(self.chk_require_3p)
        self.sp_3p_window = QSpinBox()
        self.sp_3p_window.setRange(0, 5)
        self.sp_3p_window.setValue(3)
        g3p.addRow("Max offset from 3' end:", self.sp_3p_window)
        l4.addWidget(grp_3p)

        l4.addStretch()
        tabs.addTab(tab_spec, "Specificity")

        # --- Probe design tab ---
        tab_probe = QWidget()
        l5 = QVBoxLayout(tab_probe)
        grp_probe = QGroupBox("Probe Design")
        gp5 = QFormLayout(grp_probe)
        self.combo_probe_mode = QComboBox()
        self.combo_probe_mode.addItems(["Off", "Fallback", "Always"])
        self.combo_probe_mode.setCurrentText("Fallback")
        gp5.addRow("Mode:", self.combo_probe_mode)

        self.combo_probe_chemistry = QComboBox()
        self.combo_probe_chemistry.addItems(["taqman", "taqman_mgb", "molecular_beacon", "rpa_exo"])
        gp5.addRow("Chemistry:", self.combo_probe_chemistry)

        try:
            from core.probe_catalog import DYES, QUENCHERS, CHEMISTRY_DEFAULTS, validate_combo
            dye_names = list(DYES.keys())
            quencher_names = list(QUENCHERS.keys())
            self._probe_defaults = CHEMISTRY_DEFAULTS
            self._validate_probe_combo = validate_combo
        except Exception:
            dye_names = ["FAM", "HEX", "ROX", "Cy5"]
            quencher_names = ["BHQ1", "BHQ2", "BHQ3"]
            self._probe_defaults = {}
            self._validate_probe_combo = None

        self.combo_dye = QComboBox()
        self.combo_dye.addItems(dye_names)
        gp5.addRow("Dye:", self.combo_dye)
        self.combo_quencher = QComboBox()
        self.combo_quencher.addItems(quencher_names)
        gp5.addRow("Quencher:", self.combo_quencher)
        self.lbl_probe_combo = QLabel("")
        gp5.addRow("Compatibility:", self.lbl_probe_combo)

        self.chk_mod_lna = QCheckBox("LNA")
        self.chk_mod_mgb = QCheckBox("MGB")
        self.chk_mod_thf = QCheckBox("dSpacer_THF")
        self.chk_mod_3p = QCheckBox("3p_C3_spacer")
        mods_row = QWidget()
        mods_layout = QHBoxLayout(mods_row)
        mods_layout.setContentsMargins(0, 0, 0, 0)
        for chk in (self.chk_mod_lna, self.chk_mod_mgb, self.chk_mod_thf, self.chk_mod_3p):
            mods_layout.addWidget(chk)
        gp5.addRow("Modifications:", mods_row)

        self.combo_probe_chemistry.currentTextChanged.connect(self._apply_probe_defaults)
        self.combo_dye.currentTextChanged.connect(self._update_probe_combo_label)
        self.combo_quencher.currentTextChanged.connect(self._update_probe_combo_label)
        self._apply_probe_defaults(self.combo_probe_chemistry.currentText())

        l5.addWidget(grp_probe)
        l5.addStretch()
        tabs.addTab(tab_probe, "Probe Design")

        # ── Buttons ──
        btns = QHBoxLayout()
        self.btn_ok = QPushButton("Apply Settings")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok.setDefault(True)
        btns.addStretch()
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_cancel)
        main_layout.addLayout(btns)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        # Load preset params if given
        if preset_params:
            self.load_preset(preset_params)
        self._load_probe_settings(self.probe_settings)

    def _apply_probe_defaults(self, chemistry):
        defaults = self._probe_defaults.get(chemistry, {})
        dye = defaults.get("dye")
        quencher = defaults.get("quencher")
        if dye:
            idx = self.combo_dye.findText(dye)
            if idx >= 0:
                self.combo_dye.setCurrentIndex(idx)
        if quencher:
            idx = self.combo_quencher.findText(quencher)
            if idx >= 0:
                self.combo_quencher.setCurrentIndex(idx)
        mods = set(defaults.get("mods", []))
        self.chk_mod_lna.setChecked("LNA" in mods)
        self.chk_mod_mgb.setChecked("MGB" in mods)
        self.chk_mod_thf.setChecked("dSpacer_THF" in mods)
        self.chk_mod_3p.setChecked("3p_C3_spacer" in mods)
        self._update_probe_combo_label()

    def _update_probe_combo_label(self):
        if not self._validate_probe_combo:
            self.lbl_probe_combo.setText("Not validated")
            return
        ok, msg = self._validate_probe_combo(
            self.combo_dye.currentText(),
            self.combo_quencher.currentText(),
        )
        self.lbl_probe_combo.setText(("OK: " if ok else "Warning: ") + msg)

    def _load_probe_settings(self, settings):
        if not settings:
            return

        mode = settings.get("mode")
        if mode:
            idx = self.combo_probe_mode.findText(str(mode).title())
            if idx >= 0:
                self.combo_probe_mode.setCurrentIndex(idx)

        chemistry = settings.get("chemistry")
        if chemistry:
            idx = self.combo_probe_chemistry.findText(str(chemistry))
            if idx >= 0:
                self.combo_probe_chemistry.setCurrentIndex(idx)

        dye = settings.get("dye")
        if dye:
            idx = self.combo_dye.findText(str(dye))
            if idx >= 0:
                self.combo_dye.setCurrentIndex(idx)

        quencher = settings.get("quencher")
        if quencher:
            idx = self.combo_quencher.findText(str(quencher))
            if idx >= 0:
                self.combo_quencher.setCurrentIndex(idx)

        mods = set(settings.get("modifications", []))
        self.chk_mod_lna.setChecked("LNA" in mods)
        self.chk_mod_mgb.setChecked("MGB" in mods)
        self.chk_mod_thf.setChecked("dSpacer_THF" in mods)
        self.chk_mod_3p.setChecked("3p_C3_spacer" in mods)
        self._update_probe_combo_label()

    def load_preset(self, params):
        """Populate spinbox values from a METHOD_PARAMS dict."""
        self.sp_min_size.setValue(params.get("min_size", 18))
        self.sp_opt_size.setValue(params.get("opt_size", 22))
        self.sp_max_size.setValue(params.get("max_size", 25))
        self.sp_min_tm.setValue(params.get("min_tm", 55.0))
        self.sp_opt_tm.setValue(params.get("opt_tm", 60.0))
        self.sp_max_tm.setValue(params.get("max_tm", 65.0))
        prod = params.get("product", [100, 500])
        if isinstance(prod, (list, tuple)) and len(prod) == 2:
            self.sp_prod_min.setValue(prod[0])
            self.sp_prod_max.setValue(prod[1])
        self.sp_min_gc.setValue(params.get("min_gc", 30.0))
        self.sp_max_gc.setValue(params.get("max_gc", 70.0))

    def get_settings(self):
        """Return Primer3 settings dict from current UI values."""
        return {
            "PRIMER_MIN_SIZE": self.sp_min_size.value(),
            "PRIMER_OPT_SIZE": self.sp_opt_size.value(),
            "PRIMER_MAX_SIZE": self.sp_max_size.value(),
            "PRIMER_MIN_TM": self.sp_min_tm.value(),
            "PRIMER_OPT_TM": self.sp_opt_tm.value(),
            "PRIMER_MAX_TM": self.sp_max_tm.value(),
            "PRIMER_MIN_GC": self.sp_min_gc.value(),
            "PRIMER_MAX_GC": self.sp_max_gc.value(),
            "PRIMER_PRODUCT_SIZE_RANGE": [
                [self.sp_prod_min.value(), self.sp_prod_max.value()]
            ],
            "PRIMER_MAX_HAIRPIN_TH": self.sp_max_hairpin.value(),
            "PRIMER_MAX_SELF_ANY_TH": self.sp_max_dimer.value(),
            "PRIMER_PAIR_MAX_COMPL_ANY_TH": self.sp_max_compl.value(),
            "PRIMER_SALT_MONOVALENT": self.sp_na.value(),
            "PRIMER_SALT_DIVALENT": self.sp_mg.value(),
            "PRIMER_DNTP_CONC": self.sp_dntp.value(),
            "PRIMERY_REQUIRE_3PRIME_MM": self.chk_require_3p.isChecked(),
            "PRIMERY_THREE_PRIME_WINDOW": self.sp_3p_window.value(),
        }

    def get_max_pairs(self):
        return self.sp_max_pairs.value()

    def get_cluster_pairs_limit(self):
        return self.sp_cluster_pairs.value()

    def get_specificity_settings(self):
        """Return specificity settings from the Specificity tab."""
        db_text = self.combo_spec_db.currentText()
        db_name = db_text.split(" ")[0]  # Extract short name
        return {
            "database": db_name,
            "entrez_query": self.le_entrez_spec.text().strip(),
            "target_organism": self.le_target_org.text().strip(),
        }

    def get_probe_settings(self):
        mods = []
        if self.chk_mod_lna.isChecked():
            mods.append("LNA")
        if self.chk_mod_mgb.isChecked():
            mods.append("MGB")
        if self.chk_mod_thf.isChecked():
            mods.append("dSpacer_THF")
        if self.chk_mod_3p.isChecked():
            mods.append("3p_C3_spacer")
        return {
            "mode": self.combo_probe_mode.currentText().lower(),
            "chemistry": self.combo_probe_chemistry.currentText(),
            "dye": self.combo_dye.currentText(),
            "quencher": self.combo_quencher.currentText(),
            "modifications": mods,
        }
