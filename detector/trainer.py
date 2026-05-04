import json
import pickle
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score,
    precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.utils.class_weight import compute_class_weight
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from config import Config
from detector.base_model import BaseClassifier
from detector.model import MLP
from detector.sklearn_models import TfidfMLP, TfidfRF, TfidfSVM
from detector.textcnn import TextCNNWrapper


class Trainer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        np.random.seed(cfg.seed)
        torch.manual_seed(cfg.seed)

    def _metrics(self, y_true, y_pred, y_prob) -> dict:
        return {
            "accuracy":  round(accuracy_score(y_true, y_pred), 4),
            "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
            "recall":    round(recall_score(y_true, y_pred, zero_division=0), 4),
            "f1":        round(f1_score(y_true, y_pred, zero_division=0), 4),
            "auc":       round(roc_auc_score(y_true, y_prob), 4),
            "confusion": confusion_matrix(y_true, y_pred).tolist(),
        }

    def _build_models(self) -> dict[str, type[BaseClassifier]]:
        """
        Add new model classes here.
        Each class must implement BaseClassifier (fit / predict_proba).
        """
        models = {
            "TF-IDF+SVM": TfidfSVM,
            "TF-IDF+RF":  TfidfRF,
            "TF-IDF+MLP": TfidfMLP,
            "TextCNN":    TextCNNWrapper,
        }
        if self.cfg.enable_codebert:
            from detector.codebert import CodeBERTWrapper
            models["CodeBERT"] = CodeBERTWrapper
        return models

    def cross_validate(self, texts: np.ndarray, y: np.ndarray) -> dict:
        skf     = StratifiedKFold(self.cfg.n_folds, shuffle=True, random_state=self.cfg.seed)
        models  = self._build_models()
        results = {name: [] for name in models}

        for fold, (tr_i, vl_i) in enumerate(skf.split(texts, y), 1):
            print(f"\n[CV {fold}/{self.cfg.n_folds}]")
            texts_tr = texts[tr_i].tolist()
            texts_vl = texts[vl_i].tolist()
            y_tr, y_vl = y[tr_i], y[vl_i]

            for name, Cls in models.items():
                clf   = Cls(self.cfg)
                clf.fit(texts_tr, y_tr)
                proba = clf.predict_proba(texts_vl)
                probs = proba[:, 1]
                preds = (probs >= 0.5).astype(int)
                m     = self._metrics(y_vl, preds, probs)
                results[name].append(m)
                print(f"  {name:<14} F1={m['f1']:.4f}  AUC={m['auc']:.4f}")

        return results

    def fit_final(self, texts: np.ndarray, y: np.ndarray) -> tuple[MLP, TfidfVectorizer]:
        """
        Fits TF-IDF + MLP on train split only.
        tfidf sees NO val/test data — zero leakage.
        """
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        tfidf  = TfidfVectorizer(max_features=self.cfg.max_features, sublinear_tf=True)
        X      = tfidf.fit_transform(texts).toarray().astype(np.float32)

        w     = compute_class_weight("balanced", classes=np.array([0, 1]), y=y)
        pos_w = torch.tensor([w[1] / w[0]], dtype=torch.float32).to(device)
        model = MLP(X.shape[1]).to(device)
        crit  = nn.BCEWithLogitsLoss(pos_weight=pos_w)
        opt   = torch.optim.Adam(model.parameters(), lr=self.cfg.lr)

        loader = DataLoader(
            TensorDataset(torch.tensor(X), torch.tensor(y, dtype=torch.float32)),
            batch_size=self.cfg.batch_size, shuffle=True,
        )
        for _ in range(self.cfg.epochs):
            model.train()
            for Xb, yb in loader:
                Xb, yb = Xb.to(device), yb.to(device)
                opt.zero_grad(); crit(model(Xb), yb).backward(); opt.step()

        return model, tfidf

    def save(self, model: MLP, tfidf: TfidfVectorizer) -> None:
        torch.save(model.state_dict(), self.cfg.model_file)
        with open(self.cfg.tfidf_file, "wb") as f:
            pickle.dump(tfidf, f)
        print(f"[saved] {self.cfg.model_file}")
        print(f"        {self.cfg.tfidf_file}  (fitted on train only)")

    def _eval(self, model, tfidf, texts, y, tag: str) -> dict:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        X = tfidf.transform(texts).toarray().astype(np.float32)
        model.eval()
        with torch.no_grad():
            probs = torch.sigmoid(model(torch.tensor(X).to(device))).cpu().numpy()
        preds = (probs >= 0.5).astype(int)
        m = self._metrics(y, preds, probs)
        tn, fp, fn, tp = np.array(m["confusion"]).ravel()
        print(f"[{tag}]  F1={m['f1']:.4f}  AUC={m['auc']:.4f}  "
              f"FNR={fn/(fn+tp)*100:.1f}%  FPR={fp/(fp+tn)*100:.1f}%")
        return m

    def run(self, splitter) -> None:
        X_train, y_train = splitter.load("train")
        X_val,   y_val   = splitter.load("val")
        X_test,  y_test  = splitter.load("test")
        print(f"Train={len(y_train)} | Val={len(y_val)} | Test={len(y_test)}")

        cv_results = self.cross_validate(X_train, y_train)

        print("\n[Final model: TF-IDF+MLP on train split]")
        model, tfidf = self.fit_final(X_train, y_train)
        self.save(model, tfidf)
        val_m  = self._eval(model, tfidf, X_val,  y_val,  "val ")
        test_m = self._eval(model, tfidf, X_test, y_test, "test")

        print("\n" + "=" * 68)
        print(f"{'Model':<14} {'Acc':>8} {'Prec':>8} {'Recall':>8} {'F1':>12} {'AUC':>8}")
        print("-" * 68)
        summary = {}
        for name, folds in cv_results.items():
            avg = {k: round(float(np.mean([f[k] for f in folds])), 4)
                   for k in ["accuracy", "precision", "recall", "f1", "auc"]}
            std = round(float(np.std([f["f1"] for f in folds])), 4)
            summary[name] = {**avg, "f1_std": std}
            print(f"{name:<14} {avg['accuracy']:>8.4f} {avg['precision']:>8.4f} "
                  f"{avg['recall']:>8.4f} {avg['f1']:>8.4f}±{std:.4f} {avg['auc']:>8.4f}")

        with open(self.cfg.results_file, "w") as f:
            json.dump({"cv": summary, "cv_folds": cv_results,
                       "val": val_m, "test": test_m}, f, indent=2)
        print(f"\n[saved] {self.cfg.results_file}")
