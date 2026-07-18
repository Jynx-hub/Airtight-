"""
scripts/fetch_real.py
=====================
Fetch ~350 100% REAL patents (including full-text claims and abstracts)
by streaming the Harvard USPTO dataset directly from HuggingFace, without
downloading the 60GB bulk dataset.

Target breakdown:
  G06F: 120
  H04L: 120
  H01L: 70
  G06N: 40
Total:  350 real patents
"""

import tarfile
import urllib.request
import json
import os
import sys
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

TARGETS = {
    "G06F": 120,
    "H04L": 120,
    "H01L": 70,
    "G06N": 40,
}

PATENTS_DIR = config.DATA_DIR / "corpus" / "patents"
MANIFEST_PATH = config.DATA_DIR / "corpus" / "manifest.json"

def fetch_real_patents():
    print("🧹 Cleaning out old synthetic corpus...")
    if PATENTS_DIR.exists():
        import shutil
        shutil.rmtree(PATENTS_DIR)
    PATENTS_DIR.mkdir(parents=True)
    
    # We use the 2016 tar.gz which has rich recent software/AI patents
    url = "https://huggingface.co/datasets/HUPD/hupd/resolve/main/data/2016.tar.gz"
    print(f"🌐 Streaming from HUPD (2016 data): {url}")
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    counts = {k: 0 for k in TARGETS.keys()}
    total_target = sum(TARGETS.values())
    total_fetched = 0
    all_ids = []
    
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            with tarfile.open(fileobj=r, mode='r|gz') as tar:
                for member in tar:
                    if not member.isfile() or not member.name.endswith('.json'):
                        continue
                        
                    f = tar.extractfile(member)
                    if not f:
                        continue
                        
                    raw = json.loads(f.read().decode('utf-8'))
                    
                    # Check CPC classes
                    cpc_labels = raw.get("cpc_labels", []) or []
                    matched_cpc = None
                    for target_cpc in TARGETS:
                        if counts[target_cpc] < TARGETS[target_cpc]:
                            # cpc_labels is a list of strings like ['G06F173053', ...]
                            if any(label.startswith(target_cpc) for label in cpc_labels):
                                matched_cpc = target_cpc
                                break
                            
                    if not matched_cpc:
                        continue
                        
                    # Parse claims (HUPD stores claims as a big string, we'll split crudely by number)
                    claims_text = raw.get("claims", "")
                    parsed_claims = []
                    if claims_text:
                        # Very crude split for demo purposes
                        parts = re.split(r'\n(\d+)\.\s', "\n" + claims_text)
                        for i in range(1, len(parts), 2):
                            num = int(parts[i])
                            text = parts[i+1].strip()
                            parsed_claims.append({
                                "number": num,
                                "text": text,
                                "independent": (num == 1 or "claim 1" not in text.lower())
                            })
                            
                    if not parsed_claims:
                        parsed_claims = [{"number": 1, "text": claims_text, "independent": True}]
                    
                    pnum = raw.get("patent_number") or raw.get("application_number")
                    if not pnum:
                        continue
                        
                    patent = {
                        "app_number": raw.get("application_number", ""),
                        "patent_number": pnum,
                        "cpc_class": matched_cpc,
                        "title": raw.get("title", ""),
                        "filing_date": raw.get("filing_date", "")[:10] if raw.get("filing_date") else "",
                        "grant_date": raw.get("patent_issue_date", "")[:10] if raw.get("patent_issue_date") else "",
                        "abstract": raw.get("abstract", ""),
                        "claims": parsed_claims,
                        "source": "hupd_real_stream"
                    }
                    
                    out_path = PATENTS_DIR / f"{pnum}.json"
                    out_path.write_text(json.dumps(patent, ensure_ascii=False, indent=2))
                    
                    counts[matched_cpc] += 1
                    total_fetched += 1
                    all_ids.append(pnum)
                    
                    print(f"[{total_fetched}/{total_target}] Saved {pnum} ({matched_cpc}) - {patent['title'][:40]}...")
                    
                    if total_fetched >= total_target:
                        break
                        
    except Exception as e:
        print(f"Error during stream: {e}")
        
    # Write manifest
    manifest = {
        "generated_at": "2026-07-18T00:00:00Z",
        "cpc_classes": list(TARGETS.keys()),
        "total_patents": len(all_ids),
        "warming_set_count": min(50, len(all_ids)),
        "extended_set_count": max(0, len(all_ids) - 50),
        "warming_set_ids": all_ids[:50],
        "extended_set_ids": all_ids[50:],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"✅ Finished writing {total_fetched} real patents to {PATENTS_DIR}")

if __name__ == "__main__":
    fetch_real_patents()
