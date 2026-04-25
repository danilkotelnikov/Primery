# Primery v0.2.0 Feature Guidelines

This guide describes the new primer, probe, specificity, and editing workflows
added in v0.2.0. It is written for day-to-day use rather than code maintenance.

## 1. Gene Discovery And Download

Use **Search Genes** without presetting gene names. Primery now builds broader
NCBI queries from the organism taxid, canonical locus names, aliases, GenBank
feature annotations, and title parsing.

The NCBI table now shows:

| Column | Meaning |
| --- | --- |
| Canonical | Normalized locus name used for folders and downstream output. |
| Aliases | Alternative names observed in NCBI records. |
| Count | Number of candidate NCBI records grouped under that locus. |
| Per-cluster | Number of FASTA files to download for that selected locus. |
| Examples | Representative record titles/accessions used for review. |

Recommended use:

1. Search by organism name and verify the taxid.
2. Review canonical names and aliases before downloading.
3. Set **Per-cluster** higher for loci with heterogeneous records and lower for
   clean, highly redundant loci.
4. Download only selected loci. The app should then open valid downloaded FASTA
   records from that gene folder.

If a locus appears under a vague name such as `RNA` or `UNCHARACTERIZED`, inspect
the example titles. Those are usually records where NCBI does not expose a clean
`/gene=` value. Prefer the canonical locus with the strongest evidence and leave
ambiguous rows unchecked.

## 2. Mismatch Analysis Limits

Before BLAST mismatch analysis, choose the organism and gene folders explicitly.
Do not run the whole species folder unless you intentionally want every gene.

The **Limit By** behavior is:

| Mode | Use Case | What Primery Does |
| --- | --- | --- |
| Species | Species diagnostics | Discards mismatches found only inside the target species. |
| Isolate / Strain | Strain or isolate discrimination | Allows within-species mismatches and lets them drive design. |
| Genus | Genus-level context | Keeps comparisons inside the same genus where possible. |
| Clade / Species Complex | Complexes with several accepted species | Lets you type species names to omit internal-complex differences. |
| None | Exploratory work | Uses all returned BLAST hits without taxonomic suppression. |

For routine species-specific assays, start with **Species**. Use **Isolate /
Strain** only when the diagnostic target is a subgroup inside one species. Use
**Clade / Species Complex** when several species should be treated as the same
non-discriminated group.

## 3. Sequence Editing

The sequence viewer now includes editing tools for FASTA records:

- edit sequence text
- save changes
- validate nucleotide alphabet
- reverse complement
- translate coding sequence
- trim a selected interval
- search IUPAC motifs

Use editing for curation steps such as removing low-quality flanks or correcting
obvious downloaded-record issues. After editing, rerun mismatch analysis for the
affected gene so summary tables and mappings match the saved sequence.

The former ITS2 viewer crash was caused by treating a nucleotide column as a
count column. The loader now reads count fields defensively and skips malformed
rows instead of aborting the whole mapping step.

## 4. Primer Design Near 3' Mismatches

The primer designer now prefers primer pairs where at least one
species-discriminating mismatch lies close to the 3' end. By default this means
within the configured terminal window, currently three bases.

Output fields include:

| Field | Meaning |
| --- | --- |
| `fwd_3p_mm_offset` | Distance from the forward primer 3' end to the closest discriminating mismatch. |
| `rev_3p_mm_offset` | Distance from the reverse primer 3' end to the closest discriminating mismatch. |
| `fwd_mismatch_positions` | Mismatch positions covered by the forward primer. |
| `rev_mismatch_positions` | Mismatch positions covered by the reverse primer. |

Primer3 only accepts `A`, `C`, `G`, `T`, and `N` in templates. When the reference
contains IUPAC ambiguity codes, Primery now converts invalid characters to `N`
and excludes those ambiguous spans from primer placement. This avoids false
Primer3 crashes while preventing primers from being chosen directly over
uncertain bases.

## 5. Probe Design

Use probes when primers alone cannot separate the target from close relatives,
or when the best discriminatory mismatch lies inside the amplicon rather than at
a primer terminus.

Available probe families:

| Chemistry | Typical Use | Design Notes |
| --- | --- | --- |
| TaqMan/qPCR | Hydrolysis probe qPCR | Fluorophore at 5', quencher at 3', mismatch preferably central. |
| MGB-style probe | Short high-specificity qPCR probes | Shorter probe, higher Tm support, use carefully with close mismatches. |
| Molecular beacon | Hairpin probe | Stem-loop design; mismatch should destabilize target binding. |
| RPA/exo | RPA probe assays | Includes exo-compatible internal site formatting when available. |

Probe files are written under:

```text
{Workspace}/{Organism}/BLAST/{Gene}/Probes/{Chemistry}/
```

Each probe export includes a conventionally formatted sequence such as:

```text
[FAM]ACGTA[C+]GTAC[G+]TACGT[BHQ-1]
```

In this notation:

- `[FAM]` is the 5' dye.
- `[BHQ-1]` is the 3' quencher.
- `[C+]` or `[G+]` marks an LNA-modified base.
- Internal chemistry markers are kept inside brackets where needed.

## 6. LNA And Modification Rules

The LNA placement logic is deliberately conservative:

- no more than three LNAs are placed by default
- LNAs are internal rather than terminal when possible
- adjacent LNAs are avoided
- the most informative mismatch positions are preferred
- probes without useful mismatch positions are left unmodified unless the
  selected chemistry requires another modification

Too many LNAs can over-stabilize duplexes and reduce mismatch discrimination.
Treat LNA as a specificity-tuning tool, not as a default decoration. If a probe
already has strong central mismatches, use fewer modifications. If mismatches
are weak or near the probe edge, use the formatted output as a starting point
and review the assay manually before ordering.

## 7. Primer Plus Probe Specificity

The assay-level specificity workflow is:

1. Run Primer-BLAST for the selected primer pairs.
2. Collect predicted target and off-target amplicons.
3. Align the probe core sequence to each amplicon.
4. Score whether the probe binds the target amplicon.
5. Check whether probe mismatches separate previously indistinguishable
   non-target amplicons.

Important statuses:

| Status | Meaning |
| --- | --- |
| Primer-specific | Primers alone appear specific. Probe is confirmatory. |
| Assay-specific | Primer hits exist, but the probe supports target discrimination. |
| Probe-rescued candidate | Primers are not enough; probe mismatch evidence may rescue the assay. |
| Probe-not-discriminating | Probe binds off-target amplicons too similarly. |
| Probe target binding not confirmed | Probe did not confidently bind the target amplicon. |
| Probe not assessed | Missing amplicon sequence or insufficient data. |
| Unresolved | Evidence is incomplete or contradictory. |

Do not treat **Probe-rescued candidate** as final validation. It means the design
is worth follow-up, not that it is production-ready. Confirm with local BLAST,
alignment review, and wet-lab validation.

## 8. Mapping Primer And Probe Features

Primer and probe maps now use nucleotide-resolution gradient arrows. Red blocks
mark mismatches. Tooltips and labels report which mismatch positions are covered
by each primer or probe, including LNA-supported positions for probes.

Use **Map All** after primer and probe design. If no features appear, check that:

- the selected FASTA belongs to the same gene folder used for design
- primer/probe JSON files are in the gene-specific BLAST output folder
- mismatch analysis has been rerun after sequence edits

## 9. Viewing Tables And Reports In The App

Primer XLSX/JSON files can be opened in the in-app primer table viewer. The
viewer supports sheet selection, filtering, and CSV export.

Specificity reports open in a two-pane viewer with status coloring. Use this
viewer to inspect primer-level and assay-level specificity before generating the
final report.

Reports now include:

- a summary table with every primer and probe oligo
- primer characteristics
- probe chemistry, dye, quencher, modifications, and rationale
- specificity summaries
- sequence maps when enabled

## 10. Practical Recommended Workflow

1. Search NCBI genes for the organism and inspect canonical names plus aliases.
2. Download selected loci with an explicit per-cluster FASTA count.
3. Open and curate FASTA sequences only if needed.
4. Run BLAST mismatch analysis for selected gene folders.
5. Use **Species** limit for species diagnostics or **Isolate / Strain** for
   intraspecies assays.
6. Open the mismatch viewer and confirm clusters map to the expected gene.
7. Design primers with 3' mismatch enforcement enabled.
8. If primer results are weak or ambiguous, design probes for the same gene.
9. Run specificity analysis and inspect primer plus probe status.
10. Map primers/probes on the sequence and generate the final report.
