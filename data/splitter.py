import json
import numpy as np
from pathlib import Path
from sklearn.model_selection import StratifiedShuffleSplit

from config import Config


class DataSplitter:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _path(self, name: str) -> Path:
        return self.cfg.dataset_dir / f"split_{name}.json"

    def split_and_save(self, samples: list) -> None:
        if self.cfg.split_meta.exists():
            print("[skip] split_meta.json exists — delete to re-split")
            return

        labels = np.array([s["label"] for s in samples])
        idx    = np.arange(len(samples))

        sss = StratifiedShuffleSplit(1, test_size=self.cfg.test_ratio, random_state=self.cfg.seed)
        trainval_idx, test_idx = next(sss.split(idx, labels))

        val_frac = self.cfg.val_ratio / (1 - self.cfg.test_ratio)
        sss2 = StratifiedShuffleSplit(1, test_size=val_frac, random_state=self.cfg.seed)
        tr_rel, vl_rel = next(sss2.split(trainval_idx, labels[trainval_idx]))
        train_idx = trainval_idx[tr_rel]
        val_idx   = trainval_idx[vl_rel]

        for name, idxs in [("train", train_idx), ("val", val_idx), ("test", test_idx)]:
            subset = [samples[i] for i in idxs]
            with open(self._path(name), "w", encoding="utf-8") as f:
                json.dump(subset, f, ensure_ascii=True)
            n1 = sum(1 for s in subset if s["label"] == 1)
            n0 = len(subset) - n1
            print(f"  [{name:5s}] {len(subset):5d} | webshell={n1} | benign={n0}")

        with open(self.cfg.split_meta, "w") as f:
            json.dump({
                "seed": self.cfg.seed,
                "total": int(len(samples)),
                "train": int(len(train_idx)),
                "val":   int(len(val_idx)),
                "test":  int(len(test_idx)),
            }, f, indent=2)
        print(f"[saved] seed={self.cfg.seed} locked — do not re-run after training")

    def load(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        with open(self._path(name), encoding="utf-8") as f:
            data = json.load(f)
        texts  = np.array([s["text"]  for s in data])
        labels = np.array([s["label"] for s in data])
        return texts, labels

    def run(self) -> None:
        with open(self.cfg.dataset_processed, encoding="utf-8") as f:
            samples = json.load(f)
        self.split_and_save(samples)
