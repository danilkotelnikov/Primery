# Changelog

## v0.2.0 - 2026-04-25

This subrelease turns Primery from a primer-only workflow into a gene-selected,
mismatch-aware primer and probe design workstation. It also fixes the main
runtime blockers reported during ITS2 analysis and Primer3 design.

### Added

- Broader NCBI locus discovery with canonical gene names, aliases, examples,
  per-cluster FASTA limits, and download statistics.
- Explicit gene/folder selection for BLAST mismatch analysis, primer design,
  probe design, specificity checks, and mapping.
- FASTA-aware sequence editing in the viewer: save, validate, reverse
  complement, translate, trim, and IUPAC motif search.
- Mismatch scoping modes for BLAST analysis:
  - species-level exclusion of within-target-species mismatches
  - isolate/strain-level analysis for intraspecies discrimination
  - clade/species-complex exclusion with user-provided species names
- Primer3 template sanitization for IUPAC ambiguity codes with excluded
  ambiguous regions, preventing invalid-template Primer3 crashes.
- Primer placement enforcement for species-discriminating mismatches near the
  primer 3' end, with persisted mismatch offsets and mismatch-position metadata.
- Probe catalog with fluorophores, quenchers, and probe modifications commonly
  available through regional suppliers.
- Probe design workflows for qPCR/TaqMan, MGB-style probes, molecular beacons,
  and RPA/exo probes.
- LNA-aware probe formatting with capped, internal, non-adjacent LNA placement
  at the most informative mismatch positions.
- Assay-level primer plus probe specificity evaluation:
  - Primer-BLAST amplicons are evaluated first.
  - Probe binding is checked on the candidate amplicon.
  - Probe mismatch evidence can rescue primer-indistinguishable hits when
    biologically justified.
- Probe output folders under `BLAST/{gene}/Probes/{chemistry}/` with JSON,
  FASTA, CSV, and XLSX order tables.
- Primer and probe mapping in the sequence viewer with per-nucleotide gradient
  arrows and mismatch coverage annotations.
- In-app primer table and specificity report viewers with filtering and export.
- Preferences dialog for editor, application, analysis, and keyboard settings.
- Report summary table covering primers and probes, plus probe sections and
  assay-specificity summaries.
- Updated start screen button styling with Google Sans Flex preference and
  graceful font fallback.

### Fixed

- Fixed ITS2 mismatch viewer loading crash caused by reading nucleotide letters
  as integer counts (`invalid literal for int() with base 10: 'A'`).
- Fixed BLAST analyzer cache scoping crash:
  `cannot access local variable 'json' where it is not associated with a value`.
- Fixed per-gene primer and specificity report naming so one gene no longer
  claims output files from every selected gene.
- Fixed report method detection so similarly named loci such as `TEF1` and
  `TEF1a` are not merged by a greedy regex.
- Fixed Primer3 failures on templates containing IUPAC ambiguity characters by
  sanitizing template input and excluding ambiguous regions from primer picks.
- Fixed mismatch viewer folder handling so selected summary files and likely
  BLAST folders are offered directly.
- Fixed probe discovery duplication from nested and legacy output layouts.
- Fixed messy XLSX viewing by adding sheet-aware table loading and filtering.
- Fixed downloaded FASTA visibility by auto-opening valid downloaded records
  from the selected locus folder.

### Changed

- Probe outputs are now gene- and chemistry-scoped instead of being written as
  loose workspace-level files.
- Specificity results now preserve amplicon coordinates and sequences when
  NCBI returns enough data for probe-on-amplicon assessment.
- BLAST mismatch cache keys include the selected limit mode and excluded species
  so old species-level runs are not silently reused for isolate or clade runs.
- Primer/probe maps now render at nucleotide resolution rather than as coarse
  solid regions.

### Known Limits

- Live NCBI, BLAST, and Primer-BLAST workflows still depend on network access,
  NCBI availability, and rate limits.
- Probe specificity is strongest when Primer-BLAST returns amplicon sequence or
  fetchable accession coordinates. If amplicon sequence retrieval fails, the
  assay is reported as not fully assessed rather than overcalled.
- DOCX report parity should be rechecked after PDF-focused probe-section work.
- This release does not bundle binary installers or generated BLAST workspaces.
