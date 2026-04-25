"""
ncbi_downloader.py

Refactored NCBI downloading logic using Biopython.
Generalizes the 'download_fusarium_loci.py' script to work with any organism/locus.
"""

import os
import csv
import re
import time
import json
from typing import List, Dict, Optional, Tuple
from Bio import Entrez, SeqIO

# Global email setting is required by NCBI
# Core logic will set this dynamically based on user input

_GENE_STOP_WORDS = {
    "a", "an", "and", "complete", "partial", "sequence", "gene", "genes",
    "mrna", "rna", "rrna", "trna", "cds", "clone", "clones", "intron",
    "exon", "isolate", "strain", "voucher", "chromosome", "genome",
    "genomic", "mitochondrion", "mitochondrial", "nuclear", "internal",
    "transcribed", "spacer", "small", "large", "subunit", "ribosomal",
    "putative", "predicted", "uncharacterized", "hypothetical",
}

_AMINO_ACID_3 = {
    "alanine": "Ala", "ala": "Ala",
    "arginine": "Arg", "arg": "Arg",
    "asparagine": "Asn", "asn": "Asn",
    "aspartic": "Asp", "aspartate": "Asp", "asp": "Asp",
    "cysteine": "Cys", "cys": "Cys",
    "glutamine": "Gln", "gln": "Gln",
    "glutamic": "Glu", "glutamate": "Glu", "glu": "Glu",
    "glycine": "Gly", "gly": "Gly",
    "histidine": "His", "his": "His",
    "isoleucine": "Ile", "ile": "Ile",
    "leucine": "Leu", "leu": "Leu",
    "lysine": "Lys", "lys": "Lys",
    "methionine": "Met", "met": "Met",
    "phenylalanine": "Phe", "phe": "Phe",
    "proline": "Pro", "pro": "Pro",
    "serine": "Ser", "ser": "Ser",
    "threonine": "Thr", "thr": "Thr",
    "tryptophan": "Trp", "trp": "Trp",
    "tyrosine": "Tyr", "tyr": "Tyr",
    "valine": "Val", "val": "Val",
}


def _norm_locus_key(value: str) -> str:
    """Return a stable clustering key while preserving display names elsewhere."""
    return re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()


def _split_aliases(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        chunks = []
        for item in value:
            chunks.extend(_split_aliases(item))
        return chunks
    text = str(value)
    return [
        p.strip()
        for p in re.split(r"[,;/|]+", text)
        if p and p.strip()
    ]


def _organism_words(organism: str) -> set:
    return {
        w.lower()
        for w in re.findall(r"[A-Za-z]{3,}", organism or "")
        if w.lower() not in {"sp", "spp"}
    }


def _clean_token(token: str, organism_words: Optional[set] = None) -> Optional[str]:
    token = re.sub(r"\s+", " ", str(token or "")).strip(" .,:;()[]{}")
    if not token:
        return None
    bare = re.sub(r"[^A-Za-z0-9]+", "", token)
    low = bare.lower()
    if not bare or bare.isdigit():
        return None
    if low in _GENE_STOP_WORDS:
        return None
    if organism_words and low in organism_words:
        return None
    if len(bare) < 3 and not re.match(r"^[A-Za-z]{2}\d$", bare):
        return None
    return token


def _format_token(token: str) -> str:
    token = str(token or "").strip()
    if not token:
        return token
    known = {
        "cox1": "COX1", "coi": "COX1", "co1": "COX1",
        "cox2": "COX2", "coii": "COX2", "co2": "COX2",
        "cox3": "COX3", "coiii": "COX3", "co3": "COX3",
        "cob": "COB", "cytb": "CytB",
    }
    key = token.lower().replace("-", "").replace("_", "")
    if key in known:
        return known[key]
    if re.match(r"^[A-Za-z]{2,5}\d+[A-Za-z]?$", token):
        return token.upper()
    return token


def _product_phrase_to_gene(phrase: str) -> Tuple[Optional[str], List[str]]:
    raw = re.sub(r"\s+", " ", str(phrase or "")).strip(" .,:;")
    low = raw.lower()
    if not raw:
        return None, []

    if re.search(r"\binternal transcribed spacer\s*([0-9]+)?\b", low):
        m = re.search(r"\binternal transcribed spacer\s*([0-9]+)?\b", low)
        suffix = m.group(1) or ""
        return f"ITS{suffix}", ["internal transcribed spacer" + (f" {suffix}" if suffix else "")]

    m = re.search(r"\b(5\.8s|12s|16s|18s|28s)\s+(?:ribosomal\s+)?r?rna\b", low)
    if m:
        return f"{m.group(1).upper()} rRNA", [m.group(0)]

    if re.search(r"\bbeta[- ]tubulin\b", low):
        return "beta-tubulin", ["beta tubulin", "tubulin beta"]
    if re.search(r"\balpha[- ]tubulin\b", low):
        return "alpha-tubulin", ["alpha tubulin", "tubulin alpha"]
    if re.search(r"\bgamma[- ]tubulin\b", low):
        return "gamma-tubulin", ["gamma tubulin", "tubulin gamma"]

    if re.search(r"\bp[- ]glycoprotein\b", low):
        return "P-glycoprotein", ["pgp", "p glycoprotein"]

    if "cyathostomin immunodiagnostic antigen" in low:
        return "CID", ["cyathostomin immunodiagnostic antigen"]

    if re.search(r"\bcalmodulin\b", low):
        return "calmodulin", ["cmd", "calmodulin"]

    if re.search(r"\belongation factor\s*1[- ]?alpha\b", low):
        return "TEF1a", ["tef1", "tef-1 alpha", "elongation factor 1 alpha"]

    m = re.search(r"\bnadh dehydrogenase subunit\s*([0-9]+)\b", low)
    if m:
        return f"NAD{m.group(1)}", [f"NADH dehydrogenase subunit {m.group(1)}"]

    m = re.search(r"\bcytochrome\s+(?:c\s+)?oxidase\s+subunit\s*([ivx]+|[0-9]+)\b", low)
    if m:
        val = m.group(1).lower()
        roman = {"i": "1", "ii": "2", "iii": "3"}
        return f"COX{roman.get(val, val)}", [m.group(0), f"CO{roman.get(val, val)}"]

    if re.search(r"\bcytochrome\s+b\b", low):
        return "CytB", ["cytochrome b", "cob"]

    # Keep short explicit symbols from product phrases, but do not let
    # specimen codes or organism epithets become locus names.
    token = _clean_token(raw)
    if token and len(raw.split()) == 1:
        return _format_token(token), []
    return None, []


def _parse_gene_from_title(
    title: str,
    organism: str = "",
    gene_keyword: str = "",
    known_aliases: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str], str]:
    """
    Extract a display locus name from an NCBI nuccore title.

    The parser deliberately recognizes biological phrases before generic
    "word before gene/mRNA" fallbacks. That prevents organism epithets such as
    "coronatus" and generic words such as "RNA" from becoming cluster names.
    """
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    low = text.lower()
    org_words = _organism_words(organism)
    known_aliases = known_aliases or {}

    if gene_keyword:
        parsed, aliases = _product_phrase_to_gene(gene_keyword)
        if parsed and parsed.lower() in low:
            return parsed, aliases, "keyword"
        kw = _clean_token(gene_keyword, org_words)
        if kw and re.search(rf"\b{re.escape(kw)}\b", text, re.I):
            return _format_token(kw), [], "keyword"

    normalized_title = _norm_locus_key(text)
    for alias_key, canonical in known_aliases.items():
        if alias_key and alias_key in normalized_title:
            return canonical, [], "gene_db_alias"

    for phrase in (text, low):
        parsed, aliases = _product_phrase_to_gene(phrase)
        if parsed:
            return parsed, aliases, "product_phrase"

    m = re.search(r"\bITS[-\s]*([0-9]+)\b", text, re.I)
    if m:
        return f"ITS{m.group(1)}", ["internal transcribed spacer"], "its_token"

    m = re.search(r"\btRNA[-\s]*([A-Za-z]{2,}|[A-Z][a-z]{2})\b", text)
    if m:
        aa = _AMINO_ACID_3.get(m.group(1).lower(), m.group(1).capitalize())
        return f"tRNA-{aa}", [f"tRNA {aa}"], "trna"

    # Parenthesized gene symbols are useful, but only when they are not generic
    # title descriptors such as "(complete sequence)".
    for paren in re.findall(r"\(([^()]{1,50})\)", text):
        for part in _split_aliases(paren):
            token = _clean_token(part, org_words)
            if token:
                return _format_token(token), [], "parentheses"

    # "mRNA for P-glycoprotein" / "partial mRNA for ..."
    m = re.search(r"\bmRNA\s+for\s+([^,;]+)", text, re.I)
    if m:
        parsed, aliases = _product_phrase_to_gene(m.group(1))
        if parsed:
            return parsed, aliases, "mrna_for"

    # Conservative final fallback: a gene-like token immediately before a
    # locus descriptor. Reject organism words, RNA/CDS descriptors, and numbers.
    for m in re.finditer(r"\b([A-Za-z][A-Za-z0-9_.-]{1,24})\s+(?:gene|mRNA|CDS|transcript)\b", text, re.I):
        token = _clean_token(m.group(1), org_words)
        if token:
            return _format_token(token), [], "adjacent_token"

    return "Uncharacterized", [], "unresolved"

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

    def _safe_entrez_term(self, value: str, field: str) -> str:
        value = str(value or "").strip().replace('"', "")
        if not value:
            return ""
        return f'"{value}"[{field}]' if " " in value else f"{value}[{field}]"

    def _gene_db_alias_map(self, query: str, gene_keyword: str = "", limit: int = 100) -> Dict[str, str]:
        """Return normalized alias -> canonical symbol from NCBI Gene when available."""
        aliases: Dict[str, str] = {}
        try:
            org_term = self._safe_entrez_term(query, "Organism")
            term = org_term
            if gene_keyword:
                gq = gene_keyword.replace('"', "")
                term = f"({term}) AND ({gq}[Gene Name] OR {gq}[All Fields])"
            handle = Entrez.esearch(db="gene", term=term, retmax=limit)
            record = Entrez.read(handle)
            handle.close()
            ids = record.get("IdList", [])
            if not ids:
                return aliases

            handle = Entrez.esummary(db="gene", id=",".join(ids[:limit]))
            summaries = Entrez.read(handle)
            handle.close()
            docs = summaries.get("DocumentSummarySet", {}).get("DocumentSummary", [])
            for doc in docs:
                canonical = (
                    str(doc.get("NomenclatureSymbol") or "").strip()
                    or str(doc.get("Name") or "").strip()
                )
                canonical = _clean_token(canonical) or canonical
                if not canonical:
                    continue
                canonical = _format_token(canonical)
                values = [canonical, doc.get("Name"), doc.get("Description")]
                values.extend(_split_aliases(doc.get("OtherAliases")))
                values.extend(_split_aliases(doc.get("OtherDesignations")))
                for val in values:
                    key = _norm_locus_key(val)
                    if key:
                        aliases[key] = canonical
        except Exception as e:
            print(f"Warning: NCBI Gene lookup failed: {e}")
        return aliases

    def _deep_parse_gene_name(self, uid: str) -> Optional[str]:
        """Fetch GenBank text for one accession and prefer an explicit /gene= qualifier."""
        if not uid:
            return None
        try:
            handle = Entrez.efetch(db="nuccore", id=uid, rettype="gb", retmode="text")
            gb_text = handle.read()
            handle.close()
            for gene in re.findall(r'/gene="([^"]+)"', gb_text, flags=re.IGNORECASE):
                token = _clean_token(gene)
                if token:
                    return _format_token(token)
        except Exception as e:
            print(f"Warning: deep gene parse failed for {uid}: {e}")
        return None

    def p_search_loci_candidates(
        self,
        query: str,
        limit: int = 500,
        gene_keyword: str = "",
        deep_parse: bool = False,
    ) -> List[Dict]:
        """
        Search for potential loci/genes for a given organism query to help user select targets.
        Clusters results by gene/product name to show what's available (e.g., "TEF1a (50 found)").
        """
        # Search for mRNA or Genes, excluding whole genomes
        org_term = self._safe_entrez_term(query, "Organism")
        term = f"{org_term} AND 200:10000[SLEN] NOT whole genome shotgun[Title] NOT genome assembly[Title]"
        if gene_keyword:
            gq = gene_keyword.replace('"', "")
            term = f"({term}) AND ({gq}[Gene Name] OR {gq}[Title] OR {gq}[All Fields])"
        
        try:
            gene_aliases = self._gene_db_alias_map(query, gene_keyword, limit=100)

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
            clusters = {} # key -> {count, examples, aliases, title_sum, terms}
            
            for item in summaries:
                title = item.get("Title", "")
                display = None
                aliases = []
                reason = ""
                if deep_parse:
                    display = self._deep_parse_gene_name(item.get("Id"))
                    if display:
                        reason = "gene_qualifier"
                        time.sleep(0.11)
                if not display:
                    display, aliases, reason = _parse_gene_from_title(
                        title,
                        organism=query,
                        gene_keyword=gene_keyword,
                        known_aliases=gene_aliases,
                    )
                key = _norm_locus_key(display) or "UNCHARACTERIZED"

                if key not in clusters:
                    clusters[key] = {
                        "name": display,
                        "count": 0,
                        "examples": [],
                        "title_sum": [],
                        "aliases": set(),
                        "terms": set(),
                        "reasons": set(),
                    }
                
                clusters[key]["count"] += 1
                clusters[key]["aliases"].update(a for a in aliases if a)
                clusters[key]["terms"].add(display)
                clusters[key]["terms"].update(a for a in aliases if a)
                clusters[key]["reasons"].add(reason)
                if len(clusters[key]["examples"]) < 3:
                    clusters[key]["examples"].append(item.get("Caption", "?"))
                    clusters[key]["title_sum"].append(title)

            # 4. Format for UI
            results = []
            for key, data in clusters.items():
                if data["count"] < 2 and key == "UNCHARACTERIZED":
                    continue # Skip noise
                
                # Pick a representative title (longest one usually has most info)
                repr_title = max(data["title_sum"], key=len) if data["title_sum"] else key
                aliases = sorted(
                    {a for a in data["aliases"] if _norm_locus_key(a) != key},
                    key=str.lower,
                )
                terms = [
                    t for t in sorted(data["terms"], key=str.lower)
                    if _clean_token(t) or " " in str(t)
                ]
                if not terms:
                    terms = [data["name"]]
                
                results.append({
                    "uid": key, # Using key as distinct ID
                    "canonical": data["name"],
                    "aliases": aliases,
                    "search_terms": terms,
                    "title": f"{data['name']} ({repr_title[:60]}...)",
                    "accession": ", ".join(data["examples"]),
                    "count": data["count"],
                    "length": 0, # Not relevant for cluster
                    "parse_reasons": sorted(data["reasons"]),
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
                   keep_unverified: bool = False,
                   return_stats: bool = False) -> str:
        """
        Downloads loci for a specific taxid.
        Returns path to the created manifest file by default. When return_stats
        is true, returns manifest/summary paths plus per-locus download stats.
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
        
        download_stats = {}
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
                locus_stats = {
                    "locus": locus_key,
                    "safe_locus": self._safe_name(locus_key),
                    "requested": int(n_per_locus),
                    "found_uids": 0,
                    "valid_length": 0,
                    "downloaded": 0,
                    "skipped_qc": 0,
                    "errors": 0,
                    "fasta_paths": [],
                }
                download_stats[locus_key] = locus_stats
                
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
                    locus_stats["found_uids"] = len(uids)
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
                    locus_stats["valid_length"] = len(valid_recs)
                                
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
                                locus_stats["skipped_qc"] += 1
                                continue
                                
                            # Fetch FASTA
                            handle = Entrez.efetch(db="nuccore", id=uid, rettype="fasta", retmode="text")
                            fasta_text = handle.read()
                            handle.close()
                            
                            # Save
                            # Structure: {Workspace}/{Organism}/Genes/{locus_key}/...
                            # base_dir is Workspace root (passed from GUI)
                            safe_locus = locus_stats["safe_locus"]
                            locus_dir = os.path.join(base_dir, safe_org, "Genes", safe_locus)
                            os.makedirs(locus_dir, exist_ok=True)
                            
                            acc = rec.get("Caption") or uid
                            fn = f"{safe_locus}__{self._safe_name(acc)}.fasta"
                            file_path = os.path.join(locus_dir, fn)
                            
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(fasta_text)
                                
                            w.writerow([
                                organism_label, taxid,
                                locus_key, uid, acc, int(rec.get("Length",0)),
                                "YES" if is_verified else "NO", note, rec.get("Title",""), 
                                os.path.relpath(file_path, base_dir) # Relative to workspace root
                            ])
                            locus_stats["fasta_paths"].append(os.path.relpath(file_path, base_dir))
                            
                            downloaded_count += 1
                            locus_stats["downloaded"] = downloaded_count
                            time.sleep(0.34) # Respect NCBI rate limits (3 req/s without key, 10 with)
                            
                        except Exception as e:
                            locus_stats["errors"] += 1
                            print(f"Error processing UID {uid}: {e}")
                            
                except Exception as e:
                    locus_stats["errors"] += 1
                    print(f"Error processing locus {locus_key}: {e}")
                    
        summary_path = os.path.join(org_dir, f"{safe_org}_loci_download_summary.json")
        with open(summary_path, "w", encoding="utf-8") as sf:
            json.dump(download_stats, sf, indent=2, ensure_ascii=False)

        result = {
            "manifest": manifest_path,
            "summary": summary_path,
            "stats": download_stats,
        }
        return result if return_stats else manifest_path

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
