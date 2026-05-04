import json
import pickle
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix
import torch

from config import Config
from detector.model import MLP
from features.extractor import FeatureExtractor


class Evaluator:
    """
    Loads saved model + tfidf and runs two evaluations:
      1. Held-out clean test split (split_test.json)
      2. Obfuscated webshell stress test (dataset_obfuscated.json)

    tfidf was fitted on train split only — no leakage.
    """

    def __init__(self, cfg: Config):
        self.cfg       = cfg
        self.model     = None
        self.tfidf     = None
        self.extractor = FeatureExtractor(cfg.max_tokens)

    def load(self) -> None:
        with open(self.cfg.tfidf_file, "rb") as f:
            self.tfidf = pickle.load(f)
        dim = len(self.tfidf.get_feature_names_out())
        self.model = MLP(dim)
        self.model.load_state_dict(torch.load(self.cfg.model_file, map_location="cpu"))
        self.model.eval()
        print(f"[loaded] MLP ({dim}-dim) + tfidf")

    def predict(self, texts: list) -> tuple[np.ndarray, np.ndarray]:
        X = self.tfidf.transform(texts).toarray().astype("float32")
        with torch.no_grad():
            probs = torch.sigmoid(self.model(torch.tensor(X))).numpy()
        return (probs >= 0.5).astype(int), probs

    def _report(self, title: str, y_true, y_pred) -> None:
        print(f"\n{'='*54}\n  {title}\n{'='*54}")
        print(classification_report(y_true, y_pred, target_names=["benign", "webshell"]))
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        print(f"FNR={fn/(fn+tp)*100:.1f}%  FPR={fp/(fp+tn)*100:.1f}%")

    def _eval_clean(self) -> None:
        with open(self.cfg.dataset_dir / "split_test.json", encoding="utf-8") as f:
            samples = json.load(f)
        texts  = [s["text"]  for s in samples]
        labels = [s["label"] for s in samples]
        preds, _ = self.predict(texts)
        self._report("Clean test set (held-out)", labels, preds)
        return samples  # pass through for mixed test

    def _eval_obfuscated(self, clean_test_samples: list) -> None:
        if not self.cfg.dataset_obfuscated.exists():
            print("[skip] dataset_obfuscated.json not found")
            return

        with open(self.cfg.dataset_obfuscated, encoding="utf-8") as f:
            obf = json.load(f)

        texts_obf  = [self.extractor.to_text(s["code"]) for s in obf]
        labels_obf = [1] * len(obf)
        benign     = [s for s in clean_test_samples if s["label"] == 0]
        texts_mix  = texts_obf + [s["text"] for s in benign]
        labels_mix = labels_obf + [0] * len(benign)

        preds_mix, _ = self.predict(texts_mix)
        self._report("Obfuscated webshell (stress test)", labels_mix, preds_mix)

        preds_obf, _ = self.predict(texts_obf)
        groups: dict = {}
        for s, pred in zip(obf, preds_obf):
            groups.setdefault(s["obfuscation_score"], []).append(pred)

        print("\n--- Detection by obfuscation score ---")
        print(f"{'Score':>6} {'N':>5} {'Hit':>5} {'Miss':>6} {'Miss%':>7}")
        for sc in sorted(groups):
            ps = groups[sc]
            n, hit = len(ps), sum(ps)
            print(f"{sc:>6} {n:>5} {hit:>5} {n-hit:>6} {(n-hit)/n*100:>6.1f}%")

    def run(self) -> None:
        self.load()
        clean_samples = self._eval_clean()
        self._eval_obfuscated(clean_samples)
