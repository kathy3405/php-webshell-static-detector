"""
python diagnose.py

Reads dataset_clean.json and reports:
  1. Source breakdown by label
  2. Suspicious samples: webshell_no_pattern / benign_has_pattern
  3. Label collision check between sources
  4. Random sample preview for manual inspection
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from config import Config

from data.cleaner import _DANGEROUS, _MALICIOUS, _LIBRARY_SIGNALS

_LIBRARY_RE = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in _LIBRARY_SIGNALS]


def _has_pattern(code: str) -> bool:
    return any(re.search(p, code, re.IGNORECASE) for p in _MALICIOUS)


def _has_dangerous(code: str) -> bool:
    return any(re.search(p, code, re.IGNORECASE) for p in _DANGEROUS)


def _looks_like_library(code: str) -> bool:
    return any(r.search(code) for r in _LIBRARY_RE)


def _source_tag(path: str) -> str:
    """Collapse raw source path to a short tag."""
    p = path.lower()
    for tag in ("fwoid", "webshell_tennc", "webshell_xl7", "webshell_blackarch",
                "webshell_wwwolf", "webshell_b374k", "webshell_fuzzdb",
                "cyc1e183", "obf_bartblaze", "obf_nikicat",
                "benign_guzzle", "benign_phpmailer", "benign_monolog",
                "benign_phpparser", "benign_codeigniter", "benign_dotenv",
                "benign_laravel", "benign_symfony_demo"):
        if tag in p:
            return tag
    return "unknown"


def main() -> None:
    cfg = Config()
    with open(cfg.dataset_clean, encoding="utf-8") as f:
        samples = json.load(f)

    print(f"\n[dataset_clean] {len(samples)} total")

    src_label: dict = defaultdict(lambda: Counter())
    for s in samples:
        src_label[_source_tag(s["source"])][s["label"]] += 1

    print("\nSource breakdown")
    print(f"  {'source':<28} {'webshell':>9} {'benign':>8} {'total':>7}")
    print("  " + "-" * 57)
    for src, cnt in sorted(src_label.items(), key=lambda x: -sum(x[1].values())):
        ws, bn = cnt[1], cnt[0]
        print(f"  {src:<28} {ws:>9} {bn:>8} {ws+bn:>7}")

    ws_no_pattern   = [s for s in samples if s["label"] == 1 and not _has_pattern(s["code"])]
    bn_has_pattern  = [s for s in samples if s["label"] == 0 and _has_dangerous(s["code"])]
    ws_mislabeled   = [s for s in samples if s["label"] == 1
                       and not _has_dangerous(s["code"]) and _looks_like_library(s["code"])]

    print("\nwebshell_no_pattern (label=1, no known call)")
    print(f"  total: {len(ws_no_pattern)} / {sum(1 for s in samples if s['label']==1)}"
          f"  ({len(ws_no_pattern)/max(1, sum(1 for s in samples if s['label']==1))*100:.1f}%)")
    src_ws_no = Counter(_source_tag(s["source"]) for s in ws_no_pattern)
    for src, n in src_ws_no.most_common():
        print(f"    {src:<28} {n}")

    print("\nwebshell_likely_mislabeled (no dangerous call + library signals)")
    print(f"  total: {len(ws_mislabeled)} — these will be DROPPED by cleaner")
    src_ws_mis = Counter(_source_tag(s["source"]) for s in ws_mislabeled)
    for src, n in src_ws_mis.most_common():
        print(f"    {src:<28} {n}")

    print("\nbenign_has_pattern (label=0, has DANGEROUS call, not just $_POST)")
    print(f"  total: {len(bn_has_pattern)} / {sum(1 for s in samples if s['label']==0)}"
          f"  ({len(bn_has_pattern)/max(1, sum(1 for s in samples if s['label']==0))*100:.1f}%)")
    src_bn_pat = Counter(_source_tag(s["source"]) for s in bn_has_pattern)
    for src, n in src_bn_pat.most_common():
        print(f"    {src:<28} {n}")

    import hashlib
    seen: dict = {}
    collisions = 0
    for s in samples:
        h = hashlib.md5(s["code"].encode("utf-8", errors="replace")).hexdigest()
        if h in seen and seen[h] != s["label"]:
            collisions += 1
        else:
            seen[h] = s["label"]
    print("\nLabel collision (same code, different label)")
    print(f"  {collisions} collisions found")
    if collisions > 0:
        print("  [warn] these samples have contradictory labels — will add noise to training")

    import random
    rng = random.Random(42)

    def _preview(title: str, pool: list, n: int = 5) -> None:
        print(f"\n{title} (random {min(n, len(pool))} of {len(pool)})")
        for s in rng.sample(pool, min(n, len(pool))):
            src = _source_tag(s["source"])
            snippet = s["code"].replace("\n", " ")[:120]
            print(f"  [{src}] {snippet}")

    _preview("webshell_no_pattern examples",     ws_no_pattern)
    _preview("webshell_likely_mislabeled examples", ws_mislabeled)
    _preview("benign_has_pattern examples",      bn_has_pattern)

    print("\nPattern hit rate for webshells by source")
    ws_by_src: dict = defaultdict(list)
    for s in samples:
        if s["label"] == 1:
            ws_by_src[_source_tag(s["source"])].append(_has_pattern(s["code"]))
    for src, hits in sorted(ws_by_src.items()):
        rate = sum(hits) / len(hits) * 100
        print(f"  {src:<28}  {sum(hits):>4}/{len(hits):<5}  ({rate:.1f}% have pattern)")


if __name__ == "__main__":
    main()
