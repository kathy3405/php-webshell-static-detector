from collections import Counter

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import DataLoader, TensorDataset

from detector.base_model import BaseClassifier


class _TextCNN(nn.Module):
    def __init__(self, vocab_size, embed_dim, num_filters, kernel_sizes):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.convs = nn.ModuleList([
            nn.Conv1d(embed_dim, num_filters, k) for k in kernel_sizes
        ])
        self.dropout = nn.Dropout(0.3)
        self.fc = nn.Linear(num_filters * len(kernel_sizes), 1)

    def forward(self, x):
        x = self.embedding(x).transpose(1, 2)           # (B, embed, L)
        pooled = [F.relu(c(x)).max(dim=2)[0] for c in self.convs]
        return self.fc(self.dropout(torch.cat(pooled, 1))).squeeze(1)


class TextCNNWrapper(BaseClassifier):
    def __init__(self, cfg):
        self.cfg     = cfg
        self.vocab   = {"<PAD>": 0, "<UNK>": 1}
        self.model   = None
        self._maxlen = None
        self.device  = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _build_vocab(self, texts: list) -> None:
        counter = Counter(tok for t in texts for tok in t.split())
        for word, _ in counter.most_common(self.cfg.textcnn_max_vocab - 2):
            if word not in self.vocab:
                self.vocab[word] = len(self.vocab)

    def _encode(self, texts: list, maxlen: int) -> np.ndarray:
        out = np.zeros((len(texts), maxlen), dtype=np.int64)
        for i, text in enumerate(texts):
            ids = [self.vocab.get(t, 1) for t in text.split()][:maxlen]
            out[i, : len(ids)] = ids
        return out

    def fit(self, texts: list, y: np.ndarray):
        self._build_vocab(texts)
        self._maxlen = min(
            max(len(t.split()) for t in texts),
            self.cfg.max_tokens,
        )
        X = self._encode(texts, self._maxlen)

        w     = compute_class_weight("balanced", classes=np.array([0, 1]), y=y)
        pos_w = torch.tensor([w[1] / w[0]], dtype=torch.float32).to(self.device)

        self.model = _TextCNN(
            vocab_size    = len(self.vocab),
            embed_dim     = self.cfg.textcnn_embed_dim,
            num_filters   = self.cfg.textcnn_num_filters,
            kernel_sizes  = self.cfg.textcnn_kernel_sizes,
        ).to(self.device)

        crit   = nn.BCEWithLogitsLoss(pos_weight=pos_w)
        opt    = torch.optim.Adam(self.model.parameters(), lr=self.cfg.lr)
        loader = DataLoader(
            TensorDataset(torch.tensor(X), torch.tensor(y, dtype=torch.float32)),
            batch_size=self.cfg.batch_size, shuffle=True,
        )

        for _ in range(self.cfg.epochs):
            self.model.train()
            for Xb, yb in loader:
                Xb, yb = Xb.to(self.device), yb.to(self.device)
                opt.zero_grad(); crit(self.model(Xb), yb).backward(); opt.step()
        return self

    def predict_proba(self, texts: list) -> np.ndarray:
        X      = self._encode(texts, self._maxlen)
        loader = DataLoader(torch.tensor(X), batch_size=self.cfg.batch_size)
        self.model.eval()
        probs  = []
        with torch.no_grad():
            for Xb in loader:
                p = torch.sigmoid(self.model(Xb.to(self.device))).cpu().numpy()
                probs.extend(p)
        probs = np.array(probs)
        return np.column_stack([1 - probs, probs])
