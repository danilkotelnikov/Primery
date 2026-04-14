# Scientific Background

> Theory and rationale behind Primery's species-specific primer design approach

---

## Species-Specific Primer Design

Species-specific primers exploit genetic variation between organisms to achieve selective amplification. The key insight: if a primer's 3' end lands on a position where the target species differs from all non-target species, the polymerase will fail to extend efficiently on non-target templates, even if the rest of the primer matches.

Primery automates the discovery of these discriminatory positions and designs primers that overlap them, maximizing specificity for molecular diagnostics applications such as pathogen identification, food safety testing, and environmental monitoring.

---

## Mismatch Analysis Rationale

### Why BLAST Against core_nt?

NCBI's `core_nt` database is a curated subset of the full nucleotide database (`nt`). It contains representative sequences for most organisms while being significantly smaller, resulting in faster searches. For species discrimination, `core_nt` captures the relevant phylogenetic diversity without redundancy.

### How Mismatches Are Identified

1. **Query submission:** The target species' reference sequence (e.g., TEF1 gene from *Fusarium culmorum*) is submitted to BLASTN on `core_nt`.
2. **Hit filtering:** Hits matching the target species (by taxid or scientific name) are excluded. Only non-target species are retained.
3. **Query-anchored alignment:** Each hit's HSP is projected onto the query coordinate system. Positions outside the HSP are marked `N` (uncovered). Deletions in the hit are marked `-`.
4. **Mismatch tallying:** At each query position, substitutions (SNPs) and deletions are counted across all non-target hits. The number of distinct species with mismatches at each position is recorded.

### Why 3' End Mismatches Matter

DNA polymerases extend from the 3' end of a primer. A mismatch at the ultimate 3' position dramatically reduces extension efficiency. Mismatches at the 3'-1 and 3'-2 positions also impair amplification, though less severely. Primery's scoring formula reflects this:

| Position | Score Bonus |
|----------|-------------|
| 3' end (position 0 from 3') | +15 |
| 3'-1 (position 1 from 3') | +5 |
| 3'-2 (position 2 from 3') | +5 |

---

## Cluster-Based Primer Placement

### Position Clustering

Individual mismatch positions are grouped into "clusters" — sets of positions that can be spanned by a single primer. Two positions belong to the same cluster if they are within `primer_len` bp of each other (default 25 bp for PCR, 35 bp for RPA).

This clustering converts scattered point mutations into actionable "landing zones" for primer placement.

### Cluster Scoring

Each cluster is scored by its species discrimination power:

```
score = n_species × mean_accession_fraction
```

Where:
- `n_species` is the number of distinct non-target species that have mismatches within this cluster
- `mean_accession_fraction` is the average fraction of reference accessions where these positions appear

Higher scores indicate clusters that discriminate against more non-target species more consistently.

### Pair Enumeration

Valid primer pairs require:
- Forward primer on an upstream cluster, reverse primer on a downstream cluster
- Distance between the outer edges of the two clusters must fall within the product size range for the selected method
- Forward cluster must be upstream (lower position) of the reverse cluster

Pairs are sorted by species union size (total species discriminated by both primers combined), then by total mismatch count.

---

## Primer Scoring Formula

Each candidate primer pair receives a composite score:

```
score = (n_species_covered × 10)
      + (total_mismatches_covered × 5)
      + (3'_end_bonus)
      - (thermal_penalty × 0.5)
```

### Components

| Component | Weight | Description |
|-----------|--------|-------------|
| Species coverage | × 10 | Number of non-target species discriminated by covered mismatches |
| Mismatch coverage | × 5 | Total mismatch positions overlapping with both primers |
| 3' end bonus | +15 / +5 | Bonus for mismatches at critical 3' positions (see above) |
| Thermal penalty | × -0.5 | `max(hairpin_Tm) + max(self_dimer_Tm) + pair_complementarity_Tm` |

---

## Amplification Methods

### PCR (Polymerase Chain Reaction)

Standard thermocycling amplification. The most versatile method.

| Parameter | Range |
|-----------|-------|
| Primer length | 18–25 nt |
| Optimal primer Tm | 60 °C |
| Tm range | 55–65 °C |
| GC content | 40–60% |
| Product size | 100–500 bp |

### qPCR (Quantitative Real-Time PCR)

Real-time detection during amplification. Requires tighter Tm uniformity for consistent Ct values.

| Parameter | Range |
|-----------|-------|
| Primer length | 18–25 nt |
| Optimal primer Tm | 60 °C |
| Tm range | 58–62 °C |
| Product size | 70–180 bp |

Short amplicons (< 150 bp) are preferred for efficient amplification. For SYBR Green detection, primer-dimer avoidance is critical.

### RPA (Recombinase Polymerase Amplification)

Isothermal amplification at 37–42 °C. Uses recombinase, single-strand binding protein, and strand-displacing polymerase. Ideal for point-of-care and field-deployable diagnostics.

| Parameter | Range |
|-----------|-------|
| Primer length | 30–36 nt |
| Optimal primer Tm | 54 °C |
| Tm range | 50–58 °C |
| Product size | 100–300 bp |

Longer primers (30–35 nt) are required for efficient recombinase binding. Product sizes of 100–200 bp give optimal performance.

### LAMP (Loop-Mediated Isothermal Amplification)

Uses 4–6 primers (FIP, BIP, F3, B3, and optional LF, LB) for highly specific isothermal amplification at 60–65 °C. Primery designs **outer primers only** (F3/B3), which are shorter.

| Parameter | Range |
|-----------|-------|
| Outer primer length | 18–25 nt |
| Optimal primer Tm | 62 °C |
| Tm range | 58–68 °C |
| Product size | 150–350 bp |

Inner primers (FIP/BIP) are typically 45–49 nt and must be designed separately using tools like PrimerExplorer.

### NASBA (Nucleic Acid Sequence-Based Amplification)

RNA amplification at 40–55 °C using reverse transcriptase, RNase H, and T7 RNA polymerase. One primer carries a T7 promoter sequence.

| Parameter | Range |
|-----------|-------|
| Primer length | 20–30 nt |
| Optimal primer Tm | 60 °C |
| Tm range | 55–65 °C |
| Product size | 100–250 bp |

Amplicons should be < 150 nt for optimal performance in NASBA.

---

## Thermodynamic Calculations

### Melting Temperature (Tm)

Primery uses the **SantaLucia nearest-neighbor method** (Primer3 `PRIMER_TM_FORMULA=1`), which considers stacking interactions between adjacent base pairs. This is more accurate than simpler %GC-based methods, especially for primers shorter than 20 nt.

### Salt Corrections

The **SantaLucia 1998 salt correction** is applied (`PRIMER_SALT_CORRECTIONS=1`), accounting for monovalent cation concentration effects on Tm.

### Secondary Structures

Primer3 calculates several thermodynamic parameters for secondary structures:

| Parameter | Description | Concern Level |
|-----------|-------------|---------------|
| **Hairpin Tm** | Temperature at which the primer forms an intramolecular hairpin | Critical if ≥ annealing temperature |
| **Self-dimer Tm** | Temperature for self-complementary duplex formation | Can deplete available primer |
| **Heterodimer Tm** | Temperature for forward-reverse primer duplex | Can cause primer-dimer artifacts |
| **Pair complementarity Tm** | Overall complementarity between the pair | Affects PCR efficiency |

Primery penalizes high secondary structure Tm values through the thermal penalty term in the scoring formula.

---

## BLAST Configuration

### NCBI Common URL API

Primery uses the [NCBI BLAST Common URL API](https://blast.ncbi.nlm.nih.gov/doc/blast-help/urlapi.html) for submitting and retrieving BLAST jobs:

- **Submission:** `POST` to `Blast.cgi` with `CMD=Put`
- **Retrieval:** `GET` from `Blast.cgi` with `CMD=Get` and `FORMAT_TYPE=JSON2`
- **Result format:** JSON2 delivered as a ZIP archive

### Default Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Program | `blastn` | Nucleotide-nucleotide alignment |
| Database | `core_nt` | Curated, faster than full `nt` |
| Megablast | Enabled | High-identity searches (> 95% identity) |
| HITLIST_SIZE | 200 | Sufficient diversity for species discrimination |
| EXPECT | 10.0 | Permissive threshold captures distant homologs |
| Min coverage | 0.5 | Exclude partial alignments |

### Specificity Check Parameters

The `SpecificityAnalyzer` uses different BLAST parameters optimized for short primer sequences:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Program | `blastn` (via `NCBIWWW.qblast`) | Uses Biopython interface |
| Database | `nt` | Full database for comprehensive specificity check |
| Expect | 1000 | Very permissive for short sequences |
| Word size | 7 | Optimized for primer-length queries (`blastn-short` default) |
| HITLIST_SIZE | 100 | Sufficient for specificity assessment |
| Amplicon distance | 50–3000 bp | Range for plausible PCR products |

---

## References

### Primer Design

- **SantaLucia, J. (1998).** A unified view of polymer, dumbbell, and oligonucleotide DNA nearest-neighbor thermodynamics. *PNAS*, 95(4), 1460-1465.
- **Untergasser, A. et al. (2012).** Primer3 — new capabilities and interfaces. *Nucleic Acids Research*, 40(15), e115.

### Amplification Methods

- **NEB.** PCR Protocol & Guidelines. [neb.com](https://www.neb.com/)
- **IDT.** qPCR Application Guide. [idtdna.com](https://www.idtdna.com/)
- **TwistDx.** RPA Guidelines and Resources. [twistdx.co.uk](https://www.twistdx.co.uk/)
- **Eiken Chemical.** PrimerExplorer — LAMP Primer Design Manual. [primerexplorer.jp](https://primerexplorer.jp/)
- **Compton, J. (1991).** Nucleic acid sequence-based amplification. *Nature*, 350, 91-92.

### BLAST

- **NCBI.** BLAST Common URL API Documentation. [blast.ncbi.nlm.nih.gov](https://blast.ncbi.nlm.nih.gov/doc/blast-help/urlapi.html)
- **NCBI.** core_nt Database Description. [blast.ncbi.nlm.nih.gov](https://blast.ncbi.nlm.nih.gov/doc/blast-help/blastdatabases.html)

### Species-Specific Diagnostics

- **Ye, J. et al. (2012).** Primer-BLAST: A tool to design target-specific primers for polymerase chain reaction. *BMC Bioinformatics*, 13, 134.
- **Mulè, G. et al. (2004).** Species-specific PCR assays for Fusarium section Liseola. *Mycological Research*, 108, 1291-1300.
