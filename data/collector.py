import hashlib
import json
import re
import subprocess
from pathlib import Path

from config import Config

_OBFUSCATION_PATTERNS = [
    r'\\x[0-9a-f]{2}',
    r'chr\s*\(\s*\d+',
    r'str_rot13\s*\(',
    r'gzinflate\s*\(',
    r'gzuncompress\s*\(',
    r'gzdecode\s*\(',
    r'\$[a-z_]\w*\s*\(\s*\$[a-z_]\w*',
    r'preg_replace\s*\(.*\/e',
    r'base64_decode\s*\(\s*str_rot13',
    r'assert\s*\(\s*base64',
    r'create_function\s*\(',
    r'["\'][0-9a-f]{20,}["\']',
    r'pack\s*\(\s*["\']H',
]

_MALICIOUS_PATTERNS = [
    r'\beval\s*\(',       r'\bbase64_decode\s*\(',
    r'\bsystem\s*\(',     r'\bexec\s*\(',
    r'\bpassthru\s*\(',   r'\bshell_exec\s*\(',
    r'\bassert\s*\(',     r'\$_(POST|GET|REQUEST|COOKIE)',
    r'\bcreate_function\s*\(',
    r'gzinflate|gzuncompress|gzdecode',
    r'str_rot13',         r'preg_replace\s*\(.*\/e',
]

_OBFUSCATED_REPOS = [
    ("https://github.com/bartblaze/PHP-backdoors.git",        "obf_bartblaze"),
    ("https://github.com/nikicat/web-malware-collection.git", "obf_nikicat"),
]


class DataCollector:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _clone(self, url: str, name: str) -> Path | None:
        target = self.cfg.raw_dir / name
        if target.exists():
            print(f"  [skip] {name}")
            return target
        print(f"  [clone] {name}")
        r = subprocess.run(
            ["git", "clone", "--depth=1", url, str(target)],
            capture_output=True,
        )
        if r.returncode != 0:
            print(f"  [error] {name}: {r.stderr.decode()[:100]}")
            return None
        return target

    @staticmethod
    def _md5(text: str) -> str:
        return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def dedup(samples: list) -> list:
        seen, unique = set(), []
        for s in samples:
            key = DataCollector._md5(s["code"])
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique

    def _collect_php(self, directory: Path, label: int,
                     max_files: int | None = None) -> list:
        samples = []
        for path in directory.rglob("*.php"):
            try:
                code = path.read_text(encoding="utf-8", errors="ignore").strip()
                if not (self.cfg.min_len <= len(code) <= self.cfg.max_len):
                    continue
                samples.append({"code": code, "label": label, "source": str(path)})
                if max_files and len(samples) >= max_files:
                    break
            except Exception:
                continue
        return samples

    def collect_webshell(self) -> list:
        raw = []
        for url, name in self.cfg.webshell_repos:
            repo = self._clone(url, name)
            if repo:
                s = self._collect_php(repo, label=1)
                print(f"    → {len(s)} files")
                raw.extend(s)
        result = self.dedup(raw)
        print(f"[webshell] {len(result)} unique")
        return result

    def collect_benign(self, n_webshell: int) -> list:
        target   = min(int(n_webshell * self.cfg.benign_ratio), self.cfg.max_benign)
        per_repo = max(target // len(self.cfg.benign_repos), 80)
        raw = []
        for url, name in self.cfg.benign_repos:
            repo = self._clone(url, name)
            if repo:
                s = self._collect_php(repo, label=0, max_files=per_repo)
                print(f"    → {len(s)} files")
                raw.extend(s)
        result = self.dedup(raw)[:target]
        print(f"[benign] {len(result)} unique  (target={target})")
        return result

    @staticmethod
    def _obfuscation_score(code: str) -> int:
        return sum(1 for p in _OBFUSCATION_PATTERNS if re.search(p, code, re.IGNORECASE))

    @staticmethod
    def _is_malicious(code: str) -> bool:
        return any(re.search(p, code, re.IGNORECASE) for p in _MALICIOUS_PATTERNS)

    def collect_obfuscated(self) -> list:
        """
        Collects heavily obfuscated webshells (label=1) from dedicated repos.
        Saved separately to dataset_obfuscated.json for stress testing.
        """
        samples = []
        for url, name in _OBFUSCATED_REPOS:
            repo = self._clone(url, name)
            if not repo:
                continue
            for path in repo.rglob("*.php"):
                try:
                    code = path.read_text(encoding="utf-8", errors="ignore").strip()
                    if len(code) < self.cfg.min_len or len(code) > self.cfg.max_len:
                        continue
                    if not ("<?php" in code or "<?" in code):
                        continue
                    score = self._obfuscation_score(code)
                    if score >= 1 and self._is_malicious(code):
                        samples.append({
                            "code": code,
                            "label": 1,
                            "obfuscation_score": score,
                            "source": str(path),
                        })
                except Exception:
                    continue
            print(f"  [{name}] running total {len(samples)}")

        samples = self.dedup(samples)
        samples.sort(key=lambda x: -x["obfuscation_score"])

        with open(self.cfg.dataset_obfuscated, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=True, indent=2)

        scores = [s["obfuscation_score"] for s in samples]
        print(f"[obfuscated] {len(samples)} samples"
              + (f" | avg_score={sum(scores)/len(scores):.1f}"
                 f" | max={max(scores)}" if scores else ""))
        print(f"[saved] → {self.cfg.dataset_obfuscated}")
        return samples

    @staticmethod
    def _http_json(url: str) -> dict:
        import json as _json
        import urllib.request
        with urllib.request.urlopen(url, timeout=30) as r:
            return _json.loads(r.read())

    @staticmethod
    def _http_bytes(url: str, timeout: int = 300) -> bytes:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read()

    def collect_cyc1e183(self) -> list:
        """
        Downloads PHP-Webshell.zip from Cyc1e183/PHP-Webshell-Dataset (2917 webshells).
        The repo stores data as a single zip (possibly LFS-tracked); we download directly.
        """
        import io
        import zipfile

        dest_dir = self.cfg.raw_dir / "cyc1e183_extracted"
        if dest_dir.exists() and any(dest_dir.rglob("*.php")):
            samples = self._collect_php(dest_dir, label=1)
            print(f"  [skip] cyc1e183 (already extracted) → {len(samples)} files")
            return samples

        dest_dir.mkdir(parents=True, exist_ok=True)
        print("  [cyc1e183] downloading PHP-Webshell.zip …")
        try:
            data = self._http_bytes(self.cfg.cyc1e183_zip_url)
        except Exception as e:
            print(f"  [error] cyc1e183 download: {e}")
            return []

        if len(data) < 500 and b"oid sha256" in data:
            print("  [skip] cyc1e183: zip is LFS-tracked — install git-lfs and re-clone manually")
            return []

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                z.extractall(dest_dir)
        except Exception as e:
            print(f"  [error] cyc1e183 extract: {e}")
            return []

        samples = self._collect_php(dest_dir, label=1)
        print(f"  [cyc1e183] → {len(samples)} files")
        return samples

    def collect_fwoid(self) -> list:
        """
        Downloads the FWOID dataset from Zenodo (record 14938302).
        source_code(pass123).zip contains both webshell and benign PHP files.
        Label is determined per-file from the path *inside* the zip, not the zip name.
        """
        import io
        import zipfile

        extract_dir = self.cfg.raw_dir / "fwoid"
        extract_dir.mkdir(parents=True, exist_ok=True)

        api_url = f"https://zenodo.org/api/records/{self.cfg.fwoid_zenodo_record}"
        try:
            meta = self._http_json(api_url)
        except Exception as e:
            print(f"[skip] collect_fwoid: Zenodo API error — {e}")
            return []

        file_entries = meta.get("files", [])
        if not file_entries:
            print("[warn] collect_fwoid: unexpected Zenodo response shape")
            return []

        samples = []
        for entry in file_entries:
            name   = entry.get("key", entry.get("filename", ""))
            dl_url = entry.get("links", {}).get("self", entry.get("links", {}).get("download", ""))
            if not name.endswith(".zip") or not dl_url:
                continue

            zip_dest = extract_dir / name
            if not zip_dest.exists():
                print(f"  [fwoid] downloading {name} …")
                try:
                    zip_dest.write_bytes(self._http_bytes(dl_url))
                except Exception as e:
                    print(f"  [error] {name}: {e}")
                    continue

            try:
                with zipfile.ZipFile(zip_dest) as z:
                    for info in z.infolist():
                        if not info.filename.lower().endswith(".php"):
                            continue
                        path_lower = info.filename.lower()
                        if any(k in path_lower for k in
                               ("webshell", "malware", "backdoor", "/shell")):
                            label = 1
                        elif any(k in path_lower for k in
                                 ("source_", "benign", "normal", "phpmailer",
                                  "wordpress", "phpcms")):
                            label = 0
                        else:
                            continue
                        try:
                            code = z.read(info, pwd=self.cfg.fwoid_zip_password
                                          ).decode("utf-8", errors="ignore").strip()
                            if self.cfg.min_len <= len(code) <= self.cfg.max_len:
                                samples.append({
                                    "code": code, "label": label,
                                    "source": f"{name}::{info.filename}",
                                })
                        except Exception:
                            continue
            except Exception as e:
                print(f"  [error] open {name}: {e}")
                continue

        samples = self.dedup(samples)
        n1 = sum(1 for s in samples if s["label"] == 1)
        print(f"[fwoid] {len(samples)} samples | webshell={n1} | benign={len(samples)-n1}")
        return samples

    def collect_weevely(self) -> list:
        """
        Generates obfuscated PHP backdoors using weevely3 (v4+, package-based).
        Installs via `pip install -e .`, then calls the `weevely generate` command.
        """
        import random
        import shutil
        import string

        weevely_dir = self.cfg.raw_dir / "weevely3"

        # Detect broken clone (no pyproject.toml) and re-clone
        if weevely_dir.exists() and not (weevely_dir / "pyproject.toml").exists():
            print("  [weevely3] broken clone detected — re-cloning")
            shutil.rmtree(weevely_dir)

        if not weevely_dir.exists():
            if not self._clone("https://github.com/epinna/weevely3.git", "weevely3"):
                return []

        # Install as package (idempotent)
        subprocess.run(
            ["pip", "install", "-e", ".", "-q", "--break-system-packages"],
            cwd=str(weevely_dir), capture_output=True,
        )

        weevely_bin = shutil.which("weevely")
        if not weevely_bin:
            print("[skip] collect_weevely: weevely command not found after install")
            return []

        out_dir = self.cfg.raw_dir / "weevely_generated"
        out_dir.mkdir(parents=True, exist_ok=True)

        rng = random.Random(self.cfg.seed)
        samples = []
        for i in range(self.cfg.weevely_n_shells):
            out_php = out_dir / f"weevely_{i:04d}.php"
            if not out_php.exists():
                pwd = "".join(rng.choices(string.ascii_letters + string.digits, k=12))
                r = subprocess.run(
                    [weevely_bin, "generate", pwd, str(out_php)],
                    capture_output=True,
                )
                if r.returncode != 0:
                    continue
            try:
                code = out_php.read_text(encoding="utf-8", errors="ignore").strip()
                if self.cfg.min_len <= len(code) <= self.cfg.max_len:
                    score = self._obfuscation_score(code)
                    samples.append({
                        "code": code, "label": 1,
                        "obfuscation_score": score,
                        "source": str(out_php),
                    })
            except Exception:
                continue

        print(f"[weevely] {len(samples)} shells generated")
        return samples

    def collect_mwf(self) -> list:
        """
        Loads the MWF dataset (Computers & Security 2023, DOI:10.1016/j.cose.2023.103140).
        Requires institutional Elsevier access — download manually and set cfg.mwf_dir.
        Expected layout:  mwf_dir/webshell/*.php  and  mwf_dir/benign/*.php
        """
        mwf_dir = Path(self.cfg.mwf_dir)
        if not mwf_dir.exists():
            print("[skip] collect_mwf: cfg.mwf_dir not set or does not exist")
            print("       DOI: https://doi.org/10.1016/j.cose.2023.103140")
            return []

        samples = []
        for label, subdir in [(1, "webshell"), (0, "benign")]:
            d = mwf_dir / subdir
            if not d.exists():
                print(f"[warn] collect_mwf: {d} not found — skipping")
                continue
            found = self._collect_php(d, label)
            print(f"  [mwf/{subdir}] {len(found)} files")
            samples.extend(found)

        samples = self.dedup(samples)
        n1 = sum(1 for s in samples if s["label"] == 1)
        print(f"[mwf] {len(samples)} samples | webshell={n1} | benign={len(samples)-n1}")
        return samples

    def run(self) -> None:
        self.cfg.raw_dir.mkdir(parents=True, exist_ok=True)

        webshell = self.collect_webshell()
        webshell.extend(self.collect_cyc1e183())
        benign   = self.collect_benign(len(webshell))

        if self.cfg.enable_fwoid:
            fwoid = self.collect_fwoid()
            webshell.extend(s for s in fwoid if s["label"] == 1)
            benign.extend(s for s in fwoid if s["label"] == 0)

        if self.cfg.enable_mwf:
            mwf = self.collect_mwf()
            webshell.extend(s for s in mwf if s["label"] == 1)
            benign.extend(s for s in mwf if s["label"] == 0)

        samples = self.dedup(webshell + benign)

        with open(self.cfg.dataset_raw, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)

        n1 = sum(1 for s in samples if s["label"] == 1)
        n0 = len(samples) - n1
        print(f"\n[main dataset] {len(samples)} total"
              f" | webshell={n1} | benign={n0}"
              f" | ratio 1:{n0/max(n1,1):.1f}")
        print(f"[saved] → {self.cfg.dataset_raw}")

        print("\n[collecting obfuscated samples for stress test]")
        obf = self.collect_obfuscated()

        if self.cfg.enable_weevely:
            weevely = self.collect_weevely()
            if weevely:
                obf_all = self.dedup(obf + weevely)
                obf_all.sort(key=lambda x: -x.get("obfuscation_score", 0))
                with open(self.cfg.dataset_obfuscated, "w", encoding="utf-8") as f:
                    json.dump(obf_all, f, ensure_ascii=True, indent=2)
                scores = [s.get("obfuscation_score", 0) for s in obf_all]
                print(f"[obfuscated+weevely] {len(obf_all)} total"
                      + (f" | avg_score={sum(scores)/len(scores):.1f}"
                         f" | max={max(scores)}" if scores else ""))
                print(f"[saved] → {self.cfg.dataset_obfuscated}")
