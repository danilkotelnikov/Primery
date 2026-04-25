"""
Probe chemistry catalog for hydrolysis probes, molecular beacons, and RPA exo.

The catalog is deliberately data-only: GUI code can use it for combo boxes,
validation, and report rationale without duplicating chemistry rules.
"""

DYES = {
    "FAM": {"ex": 494, "em": 520, "channel": "FAM", "suppliers": ["Syntol", "DNK-Sintez", "Evrogen", "Lumiprobe"]},
    "HEX": {"ex": 535, "em": 555, "channel": "HEX", "suppliers": ["Syntol", "DNK-Sintez", "Evrogen"]},
    "JOE": {"ex": 520, "em": 548, "channel": "HEX", "suppliers": ["DNK-Sintez", "Lumiprobe"]},
    "R6G": {"ex": 525, "em": 555, "channel": "HEX", "suppliers": ["Syntol"]},
    "ROX": {"ex": 575, "em": 602, "channel": "ROX", "suppliers": ["Syntol", "DNK-Sintez", "Evrogen"]},
    "TAMRA": {"ex": 555, "em": 580, "channel": "ROX", "suppliers": ["Syntol", "DNK-Sintez"]},
    "Cy3": {"ex": 550, "em": 570, "channel": "Cy3", "suppliers": ["Lumiprobe", "DNK-Sintez"]},
    "Cy5": {"ex": 648, "em": 668, "channel": "Cy5", "suppliers": ["Syntol", "DNK-Sintez", "Lumiprobe"]},
    "Cy5.5": {"ex": 675, "em": 695, "channel": "Cy5.5", "suppliers": ["Lumiprobe"]},
    "Texas Red": {"ex": 596, "em": 615, "channel": "ROX", "suppliers": ["Lumiprobe"]},
    "Yakima Yellow": {"ex": 530, "em": 549, "channel": "HEX", "suppliers": ["DNK-Sintez"]},
    "Quasar 670": {"ex": 644, "em": 670, "channel": "Cy5", "suppliers": ["Lumiprobe"]},
    "VIC": {"ex": 538, "em": 554, "channel": "HEX", "suppliers": ["DNK-Sintez"]},
    "TET": {"ex": 521, "em": 536, "channel": "FAM/HEX", "suppliers": ["DNK-Sintez"]},
    "Atto 550": {"ex": 554, "em": 576, "channel": "HEX/ROX", "suppliers": ["Lumiprobe"]},
    "Atto 647N": {"ex": 646, "em": 664, "channel": "Cy5", "suppliers": ["Lumiprobe"]},
    "Alexa Fluor 488": {"ex": 495, "em": 519, "channel": "FAM", "suppliers": ["Lumiprobe"]},
    "Alexa Fluor 647": {"ex": 650, "em": 668, "channel": "Cy5", "suppliers": ["Lumiprobe"]},
}

QUENCHERS = {
    "BHQ1": {"abs": (480, 580), "pair_with": ["FAM", "HEX", "JOE", "R6G", "TET", "VIC", "Yakima Yellow"]},
    "BHQ2": {"abs": (560, 670), "pair_with": ["ROX", "TAMRA", "Cy3", "Texas Red", "Atto 550"]},
    "BHQ3": {"abs": (620, 730), "pair_with": ["Cy5", "Cy5.5", "Quasar 670", "Atto 647N", "Alexa Fluor 647"]},
    "TAMRA": {"abs": (520, 590), "pair_with": ["FAM"], "note": "Legacy quencher; prefer dark quenchers for multiplex qPCR."},
    "Dabcyl": {"abs": (450, 560), "pair_with": ["FAM", "TET", "HEX"], "note": "Common for molecular beacons."},
    "Eclipse": {"abs": (390, 625), "pair_with": ["FAM", "HEX", "ROX", "TAMRA"]},
    "Iowa Black FQ": {"abs": (420, 620), "pair_with": ["FAM", "HEX", "JOE", "TET", "VIC"]},
    "Iowa Black RQ": {"abs": (560, 720), "pair_with": ["ROX", "Cy5", "Cy5.5"]},
    "MGB-NFQ": {"abs": (400, 620), "pair_with": ["FAM", "VIC"], "note": "Use for short TaqMan-MGB probes."},
    "RTQ1": {"abs": (500, 580), "pair_with": ["FAM", "HEX"], "supplier": "Syntol"},
    "RTQ2": {"abs": (560, 650), "pair_with": ["ROX", "Cy3"], "supplier": "Syntol"},
}

MODIFICATIONS = {
    "LNA": "Locked nucleic acid; raises Tm and can sharpen mismatch discrimination.",
    "MGB": "Minor-groove binder; supports shorter hydrolysis probes with higher Tm.",
    "3p_C3_spacer": "3' blocker commonly used for RPA exo probes.",
    "3p_phosphate": "Alternative 3' blocker for non-extending probes.",
    "3p_ddC": "Dideoxy-C 3' blocker.",
    "5p_amino": "5' amino linker for conjugation workflows.",
    "iSpacer18": "Internal spacer used in selected beacon/linker designs.",
    "dSpacer_THF": "THF abasic site required for RPA exo cleavage.",
    "internal_quencher": "Internal quencher placement, required for RPA exo probe architecture.",
    "MGB_NFQ": "Combined MGB non-fluorescent quencher label.",
}

CHEMISTRY_DEFAULTS = {
    "taqman": {"dye": "FAM", "quencher": "BHQ1", "mods": []},
    "taqman_mgb": {"dye": "FAM", "quencher": "MGB-NFQ", "mods": ["MGB"]},
    "molecular_beacon": {"dye": "FAM", "quencher": "Dabcyl", "mods": []},
    "rpa_exo": {"dye": "FAM", "quencher": "BHQ1", "mods": ["dSpacer_THF", "internal_quencher", "3p_C3_spacer"]},
}


def recommend_quencher(dye: str) -> str:
    for quencher, info in QUENCHERS.items():
        if dye in info.get("pair_with", []):
            return quencher
    return "BHQ1"


def validate_combo(dye: str, quencher: str):
    if dye not in DYES:
        return False, f"Unknown dye: {dye}"
    if quencher not in QUENCHERS:
        return False, f"Unknown quencher: {quencher}"
    if dye in QUENCHERS[quencher].get("pair_with", []):
        return True, f"{dye} + {quencher} is compatible."
    rec = recommend_quencher(dye)
    return False, f"{quencher} is not recommended for {dye}; use {rec}."


def chemistry_note(chemistry: str) -> str:
    notes = {
        "taqman": "Hydrolysis probe for qPCR; probe Tm should generally exceed primer Tm.",
        "taqman_mgb": "Short MGB hydrolysis probe for compact/high-specificity qPCR assays.",
        "molecular_beacon": "Stem-loop probe; useful when mismatch discrimination is more important than hydrolysis.",
        "rpa_exo": "RPA exo probe; requires THF, internal quencher, fluorophore, and 3' blocker.",
    }
    return notes.get(chemistry, "")
