"""
ncbi_downloader.py

Refactored NCBI downloading logic using Biopython.
Generalizes the 'download_fusarium_loci.py' script to work with any organism/locus.
"""

import os
import csv
import re
import time
from typing import List, Dict, Optional, Tuple
from Bio import Entrez, SeqIO

# Global email setting is required by NCBI
# Core logic will set this dynamically based on user input

class NCBIDownloader:
    def __init__(self, email: str, api_key: Optional[str] = None):
        self.email = email
        self.api_key = api_key
        Entrez.email = email
        if api_key:
            Entrez.api_key = api_key
        self.tool = "Primery_NCBI_Downloader"

    def _safe_name(self, s: str) -> str:
        s = s.strip().replace(" ", "_")
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", s)

    def p_search_loci_candidates(self, query: str, limit: int = 500) -> List[Dict]:
        """
        Search for potential loci/genes for a given organism query to help user select targets.
        Clusters results by gene/product name to show what's available (e.g., "TEF1a (50 found)").
        """
        # Search for mRNA or Genes, excluding whole genomes
        term = f"{query}[Organism] AND 200:10000[SLEN] NOT whole genome shotgun[Title] NOT genome assembly[Title]"
        
        try:
            # 1. Search for UIDs
            handle = Entrez.esearch(db="nuccore", term=term, retmax=limit, idtype="acc")
            record = Entrez.read(handle)
            handle.close()
            
            uids = record["IdList"]
            if not uids:
                return []
            
            # 2. Fetch Summaries to get titles/lengths
            # We process in batches to avoid URL length issues
            batch_size = 200
            summaries = []
            for i in range(0, len(uids), batch_size):
                batch = uids[i:i+batch_size]
                try:
                    handle = Entrez.esummary(db="nuccore", id=",".join(batch))
                    batch_sums = Entrez.read(handle)
                    handle.close()
                    summaries.extend(batch_sums)
                except Exception as batch_err:
                    print(f"Error fetching batch summary: {batch_err}")
            
            # 3. Cluster by Name
            clusters = {} # key -> {count, examples, total_len}
            
            for item in summaries:
                title = item.get("Title", "")
                
                # Heuristic to extract "Gene" name or "Product"
                # Pattern: "Organism gene_name, partial cds" or "Organism product (gene) mRNA"
                # This is rough, but effective for a high-level view
                
                # Try to find gene name in parentheses (common in Titles)
                gene_match = re.search(r"\(([\w\d\-\.]+)\)", title)
                
                # Try to clean up organism name from title to find the "product"
                # Assuming query matches organism name roughly
                clean_title = title
                
                key = "Uncharacterized"
                if gene_match:
                    key = gene_match.group(1).strip()
                    # Filter out common non-gene words in parens
                    if key.lower() in ["partial", "complete", "cds", "mrna", "sequence", "clone", "intron", "exon"]:
                        key = "Uncharacterized"
                
                if key == "Uncharacterized":
                    # Fallback: Try word before "mRNA", "CDS", "gene"
                    # e.g. "Fusarium culmorum TEF1 gene..."
                    m = re.search(r"\s+([A-Za-z0-9\-\.]+)\s+(gene|mRNA|CDS|partial|complete)", title, re.I)
                    if m:
                        key = m.group(1)
                
                # Normalize key
                key = key.upper().replace("-", "").replace("_", "")
                if len(key) < 3 or key.isdigit(): 
                    # If too short/numeric, maybe use first few words of title (excluding organism)
                    # For now just lump
                    pass

                if key not in clusters:
                    clusters[key] = {"count": 0, "examples": [], "title_sum": []}
                
                clusters[key]["count"] += 1
                if len(clusters[key]["examples"]) < 3:
                    clusters[key]["examples"].append(item.get("Caption", "?"))
                    clusters[key]["title_sum"].append(title)

            # 4. Format for UI
            results = []
            for key, data in clusters.items():
                if data["count"] < 2 and key == "Uncharacterized": continue # Skip noise
                
                # Pick a representative title (longest one usually has most info)
                repr_title = max(data["title_sum"], key=len) if data["title_sum"] else key
                
                results.append({
                    "uid": key, # Using key as distinct ID
                    "title": f"{key} ({repr_title[:60]}...)",
                    "accession": ", ".join(data["examples"]),
                    "count": data["count"],
                    "length": 0 # Not relevant for cluster
                })
            
            # Sort by count desc
            results.sort(key=lambda x: x["count"], reverse=True)
            return results

        except Exception as e:
            print(f"Error searching loci: {e}")
            return []

    def fetch_loci(self, 
                   taxid: int, 
                   organism_label: str, 
                   loci_config: Dict[str, Dict], # { 'locus_key': {'terms': [...], 'verify': [...]} }
                   outdir: str, 
                   n_per_locus: int = 10,
                   strict_qc: bool = True,
                   keep_unverified: bool = False) -> str:
        """
        Downloads loci for a specific taxid.
        Returns path to the created manifest file.
        """
        
        # Prepare workspace structure
        # {organism}_{taxid}/analysis/... 
        # But this function just downloads to outdir (which should be the organism folder ideally)
        # We will follow the new structure: outdir should be passed as "workspace/{organism}_{taxid}"
        
        safe_org = self._safe_name(organism_label)
        base_dir = outdir 
        # Structure: {Workspace}/{Organism}/...
        org_dir = os.path.join(base_dir, safe_org)
        os.makedirs(org_dir, exist_ok=True)
        
        manifest_path = os.path.join(org_dir, f"{safe_org}_loci.tsv")
        
        file_exists = os.path.exists(manifest_path)
        mode = 'a' if file_exists else 'w'
        
        with open(manifest_path, mode, encoding="utf-8", newline="") as mf:
            w = csv.writer(mf, delimiter="\t")
            if not file_exists:
                w.writerow([
                    "species_label", "taxid",
                    "locus", "uid", "accession", "length",
                    "verified", "qc_note", "title", "fasta_path"
                ])
            
            for locus_key, cfg in loci_config.items():
                search_terms = cfg.get("search_terms", [locus_key])
                verify_terms = cfg.get("verify_terms", [])
                
                # Build Query
                locus_query = " OR ".join([f'"{t}"[All Fields]' for t in search_terms])
                term = (
                    f"txid{taxid}[Organism:exp] AND ({locus_query}) "
                    f'NOT ("whole genome shotgun"[Title] OR "genome assembly"[Title] OR "chromosome"[Title])'
                )
                
                try:
                    # ESearch
                    handle = Entrez.esearch(db="nuccore", term=term, retmax=500, retmode="xml") # fetch more candidates
                    record = Entrez.read(handle)
                    handle.close()
                    
                    uids = record["IdList"]
                    if not uids:
                        continue
                        
                    # ESummary (to filter by length before fetching full)
                    # Batching? Biopython handles some, but let's be safe
                    batch_size = 200
                    valid_recs = []
                    
                    for i in range(0, len(uids), batch_size):
                        batch = uids[i:i+batch_size]
                        handle = Entrez.esummary(db="nuccore", id=",".join(batch))
                        sums = Entrez.read(handle)
                        handle.close()
                        
                        for s in sums:
                            slen = int(s.get("Length", 0))
                            if 200 <= slen <= 10000: # Reasonable limits
                                valid_recs.append(s)
                                
                    # Fetch and Verify
                    downloaded_count = 0
                    for rec in valid_recs:
                        if downloaded_count >= n_per_locus:
                            break
                            
                        uid = rec.get("Id")
                        try:
                            # Fetch GenBank for QC
                            handle = Entrez.efetch(db="nuccore", id=uid, rettype="gb", retmode="text")
                            gb_text = handle.read()
                            handle.close()
                            
                            is_verified, note = self._verify_qc(gb_text, verify_terms, strict=strict_qc)
                            
                            if (not is_verified) and (not keep_unverified):
                                continue
                                
                            # Fetch FASTA
                            handle = Entrez.efetch(db="nuccore", id=uid, rettype="fasta", retmode="text")
                            fasta_text = handle.read()
                            handle.close()
                            
                            # Save
                            # Structure: {Workspace}/{Organism}/Genes/{locus_key}/...
                            # base_dir is Workspace root (passed from GUI)
                            locus_dir = os.path.join(base_dir, safe_org, "Genes", self._safe_name(locus_key))
                            os.makedirs(locus_dir, exist_ok=True)
                            
                            acc = rec.get("Caption") or uid
                            fn = f"{self._safe_name(locus_key)}__{self._safe_name(acc)}.fasta"
                            file_path = os.path.join(locus_dir, fn)
                            
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(fasta_text)
                                
                            w.writerow([
                                organism_label, taxid,
                                locus_key, uid, acc, int(rec.get("Length",0)),
                                "YES" if is_verified else "NO", note, rec.get("Title",""), 
                                os.path.relpath(file_path, base_dir) # Relative to workspace root
                            ])
                            
                            downloaded_count += 1
                            time.sleep(0.34) # Respect NCBI rate limits (3 req/s without key, 10 with)
                            
                        except Exception as e:
                            print(f"Error processing UID {uid}: {e}")
                            
                except Exception as e:
                    print(f"Error processing locus {locus_key}: {e}")
                    
        return manifest_path

    def _verify_qc(self, gb_text: str, verify_terms: List[str], strict: bool) -> Tuple[bool, str]:
        if not verify_terms:
            return True, "no_verify_terms_provided"
            
        # Biopython GenBank parser could be used, but regex is faster for text scanning 
        # (and consistent with previous logic).
        # However, since we use biopython, let's try to be smart if we want.
        # But for "text-based" verification (searching keywords in fields), regex is fine and robust against format quirks.
        
        genes = re.findall(r'/gene="([^"]+)"', gb_text, flags=re.IGNORECASE)
        products = re.findall(r'/product="([^"]+)"', gb_text, flags=re.IGNORECASE)
        
        m = re.search(r"^DEFINITION\s+(.+?)\nACCESSION", gb_text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        definition = m.group(1) if m else ""
        keywords = re.findall(r"^KEYWORDS\s+(.+?)\.$", gb_text, flags=re.IGNORECASE | re.MULTILINE)
        
        def normalize(l): return " | ".join(l).lower()
        
        haystacks = [normalize(genes), normalize(products), definition.lower()]
        if not strict:
            haystacks.append(gb_text.lower())
            
        verify_terms = [t.lower() for t in verify_terms]
        
        for term in verify_terms:
            if any(term in h for h in haystacks):
                return True, f"matched:{term}"
                
        return False, "failed_qc"
