import json
import re
from collections import defaultdict

from config import Config

_DANGEROUS = [
    r'\beval\s*\(',          r'\bbase64_decode\s*\(',  r'\bsystem\s*\(',
    r'\bexec\s*\(',          r'\bpassthru\s*\(',        r'\bshell_exec\s*\(',
    r'\bproc_open\s*\(',     r'\bpopen\s*\(',           r'\bassert\s*\(',
    r'preg_replace\s*\(.*\/e',
    r'\bcreate_function\s*\(',
]

_SUPERGLOBALS = [
    r'\$_(POST|GET|REQUEST|COOKIE)',
]

_MALICIOUS = _DANGEROUS + _SUPERGLOBALS

_LIBRARY_SIGNALS = [
    r'@package\s+\w',
    r'@subpackage\s+\w',
    r'^\s*namespace\s+[A-Za-z][A-Za-z0-9_\\]*\s*;',
    r'^\s*abstract\s+class\s+\w',
    r'^\s*interface\s+\w',
    r'^\s*trait\s+\w',
]

_BENIGN_EXCEPTIONS = [
    r'@package\s+phpMyAdmin', r'@package\s+Drupal',
    r'namespace\s+Drupal',    r'\* phpMyAdmin',
]


def _match(code: str, patterns: list) -> list:
    return [p for p in patterns if re.search(p, code, re.IGNORECASE | re.MULTILINE)]


def _has_php_tag(code: str) -> bool:
    return '<?php' in code or '<?' in code


def _looks_like_library(code: str) -> bool:
    return bool(_match(code, _LIBRARY_SIGNALS))


class DataCleaner:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _drop_reason(self, s: dict) -> str | None:
        code, label = s["code"], s["label"]
        has_mal = bool(_match(code, _MALICIOUS))
        has_dangerous = bool(_match(code, _DANGEROUS))

        if not _has_php_tag(code) and not has_mal:
            return "no_tag_no_pattern"
        if len(code.strip()) < 50 and label == 1 and not has_mal:
            return "short_webshell_no_pattern"
        if len(code.strip()) < 50 and label == 0:
            return "short_benign"

        if label == 1 and not has_dangerous and _looks_like_library(code):
            return "webshell_likely_mislabeled"

        return None

    def audit(self, samples: list) -> dict:
        issues: dict = defaultdict(list)
        for i, s in enumerate(samples):
            flags = []
            if not _has_php_tag(s["code"]):
                flags.append("no_php_tag")
            if len(s["code"].strip()) < 50:
                flags.append("too_short")

            matched_dangerous = _match(s["code"], _DANGEROUS)
            matched_all       = _match(s["code"], _MALICIOUS)

            if s["label"] == 1 and not matched_all:
                flags.append("webshell_no_pattern")
            if s["label"] == 1 and not matched_dangerous and _looks_like_library(s["code"]):
                flags.append("webshell_likely_mislabeled")

            if s["label"] == 0 and matched_dangerous and not _match(s["code"], _BENIGN_EXCEPTIONS):
                flags.append("benign_has_pattern")

            if flags:
                issues["|".join(flags)].append({
                    "index": i, "label": s["label"],
                    "flags": flags, "preview": s["code"][:200],
                })
        return dict(issues)

    def clean(self, samples: list) -> list:
        reasons: dict = defaultdict(int)
        kept = []
        for s in samples:
            reason = self._drop_reason(s)
            if reason:
                reasons[reason] += 1
            else:
                kept.append(s)

        dropped = len(samples) - len(kept)
        n1 = sum(1 for s in kept if s["label"] == 1)
        n0 = len(kept) - n1
        print(f"[clean] {len(samples)} → {len(kept)} kept  (dropped {dropped})")
        if reasons:
            for reason, n in sorted(reasons.items(), key=lambda x: -x[1]):
                print(f"  dropped [{reason}]: {n}")
        print(f"        webshell={n1} | benign={n0}")
        return kept

    def run(self) -> None:
        with open(self.cfg.dataset_raw, encoding="utf-8") as f:
            samples = json.load(f)

        issues = self.audit(samples)
        if issues:
            print("[audit] flags found:")
            for flag, items in sorted(issues.items(), key=lambda x: -len(x[1])):
                print(f"  {flag}: {len(items)}")

        cleaned = self.clean(samples)
        with open(self.cfg.dataset_clean, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        print(f"[saved] -> {self.cfg.dataset_clean}")
