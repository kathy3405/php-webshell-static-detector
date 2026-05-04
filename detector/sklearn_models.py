import numpy as np
import torch
import torch.nn as nn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import DataLoader, TensorDataset

from detector.base_model import BaseClassifier
from detector.model import MLP


class _TfidfBase(BaseClassifier):
    def __init__(self, cfg):
        self.cfg   = cfg
        self.tfidf = None

    def _fit_tfidf(self, texts):
        self.tfidf = TfidfVectorizer(max_features=self.cfg.max_features, sublinear_tf=True)
        return self.tfidf.fit_transform(texts).toarray().astype(np.float32)

    def _transform(self, texts):
        return self.tfidf.transform(texts).toarray().astype(np.float32)


class TfidfSVM(_TfidfBase):
    def fit(self, texts, y):
        X = self._fit_tfidf(texts)
        self.clf = CalibratedClassifierCV(LinearSVC(class_weight="balanced", max_iter=2000))
        self.clf.fit(X, y)
        return self

    def predict_proba(self, texts):
        return self.clf.predict_proba(self._transform(texts))


class TfidfRF(_TfidfBase):
    def fit(self, texts, y):
        X = self._fit_tfidf(texts)
        self.clf = RandomForestClassifier(
            200, class_weight="balanced", random_state=self.cfg.seed, n_jobs=-1
        )
        self.clf.fit(X, y)
        return self

    def predict_proba(self, texts):
        return self.clf.predict_proba(self._transform(texts))


class TfidfMLP(_TfidfBase):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.model  = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def fit(self, texts, y):
        X = self._fit_tfidf(texts)
        w     = compute_class_weight("balanced", classes=np.array([0, 1]), y=y)
        pos_w = torch.tensor([w[1] / w[0]], dtype=torch.float32).to(self.device)

        self.model = MLP(X.shape[1]).to(self.device)
        crit = nn.BCEWithLogitsLoss(pos_weight=pos_w)
        opt  = torch.optim.Adam(self.model.parameters(), lr=self.cfg.lr)
        ds   = TensorDataset(torch.tensor(X), torch.tensor(y, dtype=torch.float32))
        loader = DataLoader(ds, batch_size=self.cfg.batch_size, shuffle=True)

        for _ in range(self.cfg.epochs):
            self.model.train()
            for Xb, yb in loader:
                Xb, yb = Xb.to(self.device), yb.to(self.device)
                opt.zero_grad(); crit(self.model(Xb), yb).backward(); opt.step()
        return self

    def predict_proba(self, texts):
        X = self._transform(texts)
        self.model.eval()
        with torch.no_grad():
            probs = torch.sigmoid(self.model(torch.tensor(X).to(self.device))).cpu().numpy()
        return np.column_stack([1 - probs, probs])
