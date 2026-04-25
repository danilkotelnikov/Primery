"""
primer_specificity.py

Implements Primer-BLAST-like specificity checking using remote NCBI BLAST.
"""

import time
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import List, Dict
from Bio.Blast import NCBIWWW, NCBIXML
from Bio import Entrez

# Access email is required for NCBI
Entrez.email = "example@example.com"  # Should be user configurable or generic

class SpecificityAnalyzer:
    def __init__(self):
        pass

    _COMP = str.maketrans("ACGTRYMKBDHVNacgtrymkbdhvn", "TGCAYRKMVHDBNtgcayrkmvhdbn")

    def _revcomp(self, seq: str) -> str:
        return str(seq or "").translate(self._COMP)[::-1]

    def _safe_token(self, value: str) -> str:
        value = str(value or "").strip() or "unknown"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"

    def _primer_group_key(self, primer: Dict) -> tuple:
        gene = primer.get("gene") or "unknown"
        method = primer.get("method") or primer.get("assay") or "primers"
        return str(gene), str(method)

    def _read_fasta_sequence(self, text: str) -> str:
        return "".join(
            line.strip() for line in str(text or "").splitlines()
            if line.strip() and not line.startswith(">")
        ).upper()

    def _fetch_amplicon_sequence(self, acc: str, start: int, end: int, orientation: int, cache: Dict) -> tuple:
        lo, hi = sorted((max(1, int(start)), max(1, int(end))))
        key = (acc, lo, hi, orientation)
        if key in cache:
            return cache[key]
        try:
            handle = Entrez.efetch(
                db="nuccore",
                id=acc,
                rettype="fasta",
                retmode="text",
                seq_start=lo,
                seq_stop=hi,
            )
            fasta = handle.read()
            handle.close()
            seq = self._read_fasta_sequence(fasta)
            if orientation == -1:
                seq = self._revcomp(seq)
            cache[key] = (seq, "")
        except Exception as e:
            cache[key] = ("", str(e))
        return cache[key]

    def run_primer_blast(self, 
                        primers: List[Dict], 
                        database: str = "nt", 
                        organism_filter: str = "",
                        target_organism: str = "",
                        output_dir: str = None,
                        report_name_prefix: str = None) -> List[Dict]:
        """
        Check specificity for a list of primers.
        
        Args:
            primers: List of dicts with 'name', 'fwd', 'rev'.
            database: NCBI database (nt, refseq_rna, etc).
            organism_filter: Entrez query to limit search (e.g. 'fungi[organism]').
            target_organism: Name of the target species (e.g. "Fusarium nanum").
            
        Returns:
            List of primers with added 'specificity' fields.
        """
        results = []

        if output_dir and report_name_prefix is None:
            groups = defaultdict(list)
            for p in primers:
                groups[self._primer_group_key(p)].append(p)
            if len(groups) > 1:
                grouped_results = []
                for (gene, method), group in groups.items():
                    prefix = (
                        f"PrimerBLAST_{self._safe_token(gene)}_"
                        f"{self._safe_token(method)}"
                    )
                    grouped_results.extend(self.run_primer_blast(
                        group,
                        database=database,
                        organism_filter=organism_filter,
                        target_organism=target_organism,
                        output_dir=output_dir,
                        report_name_prefix=prefix,
                    ))
                return grouped_results
        
        # Parse target genus for classification
        target_genus = target_organism.split()[0] if target_organism else ""
        sequence_cache = {}
        
        # Prepare Report File
        report_file = None
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if report_name_prefix is None:
                if primers:
                    gene, method = self._primer_group_key(primers[0])
                    report_name_prefix = (
                        f"PrimerBLAST_{self._safe_token(gene)}_"
                        f"{self._safe_token(method)}"
                    )
                else:
                    report_name_prefix = "PrimerBLAST"
            report_path = os.path.join(
                output_dir,
                f"{self._safe_token(report_name_prefix)}_{timestamp}.txt",
            )
            try:
                report_file = open(report_path, "w", encoding="utf-8")
                report_file.write(f"Primer-BLAST Specificity Report\n")
                report_file.write(f"Date: {datetime.now()}\n")
                report_file.write(f"Target: {target_organism}\n")
                report_file.write(f"Database: {database}\n")
                report_file.write("="*60 + "\n\n")
            except Exception as e:
                print(f"Error creating report file: {e}")
        
        for p in primers:
            amplicons = [] # Reset for each pair
            # We process one pair at a time because Remote BLAST is slow and we want
            # to track progress per pair (in GUI).
            # Construct query: Fwd + Rev
            # Actually, Primer-BLAST usually takes one pair. 
            # We can use blastn-short with both sequences.
            
            fwd_seq = p.get('fwd', '') or p.get('left', '')
            rev_seq = p.get('rev', '') or p.get('right', '')
            
            if not fwd_seq or not rev_seq:
                p['specificity_status'] = "Error: Missing Seq"
                results.append(p)
                continue
                
            query_fasta = f">Fwd\n{fwd_seq}\n>Rev\n{rev_seq}\n"
            
            # Entrez Query Construction
            # If user provided filter, use it. 
            # Note: BLAST 'entrez_query' param filters the DATABASE.
            
            try:
                # 1. Run Remote BLAST
                # blastn-short is optimized for primers/short seqs
                print(f"Blasting {p.get('name', 'pair')} against {database}...")
                
                # NCBIWWW.qblast params:
                # program="blastn"
                # database=database
                # sequence=query_fasta
                # entrez_query=organism_filter
                # expect=1000 (high e-value for short seqs)
                # word_size=7 (default for blastn-short is 7)
                # nucl_reward=1, nucl_penalty=-3 (blastn-short defaults)
                
                handle = NCBIWWW.qblast(
                    "blastn", 
                    database, 
                    query_fasta, 
                    entrez_query=organism_filter,
                    expect=1000,
                    word_size=7,
                    hitlist_size=100  # distinct accessions
                )
                
                # 2. Parse XML
                blast_records = list(NCBIXML.parse(handle))
                handle.close()
                
                # 3. Analyze Hits to find Amplicons
                # We need hits for Fwd and hits for Rev on the SAME accession
                # Check orientation and distance
                
                fwd_hits = {} # accession -> list of HSPs
                rev_hits = {} # accession -> list of HSPs
                
                # record[0] is Fwd, record[1] is Rev (order in query_fasta)
                for record in blast_records:
                    query_def = record.query.split()[0] # "Fwd" or "Rev"
                    is_fwd = "Fwd" in query_def
                    
                    for alignment in record.alignments:
                        acc = alignment.accession
                        # Get organism from title (e.g. "gi|123|... Fusarium nanum ...")
                        title = alignment.title
                        # Extract organism name - naive heuristic or use hit_def
                        # We will store the whole alignment object or relevant fields
                        
                        for hsp in alignment.hsps:
                            # Filter weak hits? Primer-BLAST is sensitive.
                            # Identity > 80%? 3' end match?
                            # For simplicity, keep all reported hits but prioritize perfect ones.
                            
                            hit_data = {
                                'acc': acc,
                                'title': title,
                                'start': hsp.sbjct_start,
                                'end': hsp.sbjct_end,
                                'strand': hsp.frame[1], # 1 or -1
                                'ident': hsp.identities,
                                'len': hsp.align_length,
                                'mismatches': hsp.align_length - hsp.identities,
                                'q_len': record.query_length
                            }
                            
                            # 3' End Check:
                            # Fwd (Plus): q_end should be near q_len
                            # Rev (Plus): q_end should be near q_len (BLAST orients query)
                            # Actually need to check if lack of match is at 3' end.
                            # hsp.query_end == record.query_length means 3' matched.
                            hit_data['3_prime_match'] = (hsp.query_end == record.query_length)
                            
                            if is_fwd:
                                if acc not in fwd_hits: fwd_hits[acc] = []
                                fwd_hits[acc].append(hit_data)
                            else:
                                if acc not in rev_hits: rev_hits[acc] = []
                                rev_hits[acc].append(hit_data)

                # 4. Find Amplicons
                amplicons = []
                common_accs = set(fwd_hits.keys()) & set(rev_hits.keys())
                
                for acc in common_accs:
                    for f in fwd_hits[acc]:
                        for r in rev_hits[acc]:
                            # Check orientation: One Plus, One Minus
                            # And distance
                            # Fwd start < Rev start (if Fwd is Plus)
                            
                            # Case 1: Fwd Plus, Rev Minus
                            if f['strand'] == 1 and r['strand'] == -1:
                                dist = r['start'] - f['start']
                                if 50 < dist < 3000: # Plausible amplicon
                                    subject_start = min(f['start'], f['end'], r['start'], r['end'])
                                    subject_end = max(f['start'], f['end'], r['start'], r['end'])
                                    amp_seq, amp_seq_error = self._fetch_amplicon_sequence(
                                        acc, subject_start, subject_end, 1, sequence_cache
                                    )
                                    amplicons.append({
                                        'acc': acc,
                                        'title': f['title'],
                                        'product_size': dist,
                                        'f_mm': f['mismatches'],
                                        'r_mm': r['mismatches'],
                                        'f_3p': f['3_prime_match'],
                                        'r_3p': r['3_prime_match'],
                                        'subject_start': subject_start,
                                        'subject_end': subject_end,
                                        'orientation': 1,
                                        'sequence': amp_seq,
                                        'sequence_error': amp_seq_error,
                                    })
                                    
                            # Case 2: Fwd Minus, Rev Plus
                            elif f['strand'] == -1 and r['strand'] == 1:
                                dist = f['start'] - r['start']
                                if 50 < dist < 3000:
                                    subject_start = min(f['start'], f['end'], r['start'], r['end'])
                                    subject_end = max(f['start'], f['end'], r['start'], r['end'])
                                    amp_seq, amp_seq_error = self._fetch_amplicon_sequence(
                                        acc, subject_start, subject_end, -1, sequence_cache
                                    )
                                    amplicons.append({
                                        'acc': acc,
                                        'title': f['title'],
                                        'product_size': dist,
                                        'f_mm': f['mismatches'],
                                        'r_mm': r['mismatches'],
                                        'f_3p': f['3_prime_match'],
                                        'r_3p': r['3_prime_match'],
                                        'subject_start': subject_start,
                                        'subject_end': subject_end,
                                        'orientation': -1,
                                        'sequence': amp_seq,
                                        'sequence_error': amp_seq_error,
                                    })

                # 5. Classify Amplicons
                status = "No Hits"
                target_hits = 0
                off_target_hits = 0
                
                if amplicons:
                    has_target_amplicon = False
                    has_other_genus_amplicon = False
                    
                    for amp in amplicons:
                        # Parse Organism from title
                        # Title format: "gi|...| ref|...| Organism name sequence..."
                        # or "Description"
                        # We try to find target_organism in title
                        title_lower = amp['title'].lower()
                        org_lower = target_organism.lower()
                        genus_lower = target_genus.lower()
                        
                        is_target_species = org_lower in title_lower
                        is_target_genus = genus_lower in title_lower
                        amp['is_target_species'] = is_target_species
                        amp['is_target_genus'] = is_target_genus
                        
                        # A valid PCR product usually requires good 3' matches
                        # If 3' doesn't match, amplification is inefficient.
                        # We treat it as a hit if BOTH 3' ends match closely (or perfect match).
                        # Let's say if total mismatches < 3.
                        
                        relevant = (amp['f_mm'] + amp['r_mm'] < 5) # relaxed filter
                        
                        if relevant:
                            if is_target_species:
                                target_hits += 1
                                has_target_amplicon = True
                            elif is_target_genus:
                                # Same genus, different species => Genus Specific (potentially)
                                pass 
                            else:
                                # Different Genus
                                off_target_hits += 1
                                has_other_genus_amplicon = True
                                # Try to extract genus name for reporting?
                                # (skip for now)
                    
                    if has_target_amplicon and not has_other_genus_amplicon:
                        # Check intra-genus specificity
                        # If we have hits in same genus but NOT target species
                        # We need to know if those are considered "off-target" for Species-Specific.
                        # YES.
                        
                        # Re-scan for non-target-species hits
                        has_same_genus_off_target = False
                        for amp in amplicons:
                            title_lower = amp['title'].lower()
                            if genus_lower in title_lower and org_lower not in title_lower:
                                if amp['f_mm'] + amp['r_mm'] < 3: # Strong hit
                                    has_same_genus_off_target = True
                        
                        if has_same_genus_off_target:
                            status = "Genus-Specific"
                        else:
                            status = "Species-Specific"
                            
                    elif has_other_genus_amplicon:
                        status = "Non-Specific"
                    elif has_target_amplicon:
                        status = "Species-Specific" # Fallback
                    else:
                        status = "No Target Hits"
                
                p['specificity_status'] = status
                p['target_hits'] = target_hits
                p['off_target_hits'] = off_target_hits
                p['amplicons'] = amplicons
                
            except Exception as e:
                p['specificity_status'] = f"Error: {str(e)}"
            
            # Write to report
            if report_file:
                 report_file.write(f"Pair: {p.get('name', 'Unknown')}\n")
                 report_file.write(f"  Status: {p.get('specificity_status', 'Unknown')}\n")
                 report_file.write(f"  Target Hits: {p.get('target_hits', 0)}\n")
                 report_file.write(f"  Off-Target Hits: {p.get('off_target_hits', 0)}\n")
                 report_file.write("  Alignments:\n")
                 if amplicons:
                     for amp in amplicons:
                         report_file.write(f"    Subject: {amp['title']}\n")
                         report_file.write(f"    Product Size: {amp['product_size']} bp\n")
                         report_file.write(f"    Mismatches: Fwd={amp['f_mm']}, Rev={amp['r_mm']}\n")
                         report_file.write("-" * 40 + "\n")
                 else:
                     report_file.write("    No amplicons found.\n")
                 report_file.write("="*60 + "\n\n")


            # Rate limit for NCBI (3 requests/sec is limit, but safe to go slower)
            time.sleep(2.0)
            results.append(p)
            
        if report_file:
            report_file.close()

        return results
