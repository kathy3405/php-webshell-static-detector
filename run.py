"""
Usage:
    python run.py all
    python run.py <step>

Steps: collect | clean | preprocess | split | train | evaluate
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from config import Config
from data.collector import DataCollector
from data.cleaner import DataCleaner
from data.splitter import DataSplitter
from detector.evaluator import Evaluator
from detector.trainer import Trainer
from features.extractor import FeatureExtractor


class _Tee:
    """Mirror every print() to both console and log file."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file   = open(path, "a", encoding="utf-8")
        self._stdout = sys.stdout

    def write(self, data: str):
        self._stdout.write(data)
        self._file.write(data)
        self._file.flush()

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def __enter__(self):
        sys.stdout = self
        return self

    def __exit__(self, *_):
        sys.stdout = self._stdout
        self._file.close()


def _collect(cfg):
    DataCollector(cfg).run()

def _clean(cfg):
    DataCleaner(cfg).run()

def _preprocess(cfg):
    with open(cfg.dataset_clean, encoding="utf-8") as f:
        samples = json.load(f)
    processed = FeatureExtractor(cfg.max_tokens).preprocess_dataset(samples)
    with open(cfg.dataset_processed, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=True, indent=2)
    print(f"[saved] → {cfg.dataset_processed}")

def _split(cfg):
    DataSplitter(cfg).run()

def _train(cfg):
    Trainer(cfg).run(DataSplitter(cfg))

def _evaluate(cfg):
    Evaluator(cfg).run()


STEPS = {
    "collect":    _collect,
    "clean":      _clean,
    "preprocess": _preprocess,
    "split":      _split,
    "train":      _train,
    "evaluate":   _evaluate,
}
_ORDER = list(STEPS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Webshell detector pipeline")
    parser.add_argument("step", choices=[*_ORDER, "all"])
    args = parser.parse_args()

    cfg = Config()

    cfg.dataset_dir.mkdir(parents=True, exist_ok=True)
    cfg.raw_dir.mkdir(parents=True, exist_ok=True)

    print(f"[paths]")
    print(f"  dataset : {cfg.dataset_dir.resolve()}")
    print(f"  log     : {cfg.log_file.resolve()}")

    steps = _ORDER if args.step == "all" else [args.step]

    with _Tee(cfg.log_file):
        print(f"\n{'='*52}")
        print(f"  step  : {' → '.join(steps)}")
        print(f"  time  : {datetime.now():%Y-%m-%d %H:%M:%S}")
        print(f"  data  : {cfg.dataset_dir.resolve()}")
        print(f"  log   : {cfg.log_file.resolve()}")
        print(f"{'='*52}")

        for step in steps:
            print(f"\n{'-'*44}\n  {step.upper()}\n{'-'*44}")
            STEPS[step](cfg)

        print(f"\n[done] {datetime.now():%H:%M:%S}")


if __name__ == "__main__":
    main()
