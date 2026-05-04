import numpy as np
import torch
import torch.nn as nn
from sklearn.utils.class_weight import compute_class_weight
from torch.utils.data import DataLoader, Dataset

from detector.base_model import BaseClassifier


class _CodeDataset(Dataset):
    def __init__(self, input_ids, attention_mask, labels=None):
        self.input_ids      = input_ids
        self.attention_mask = attention_mask
        self.labels         = labels

    def __len__(self):
        return len(self.input_ids)

    def __getitem__(self, i):
        item = {
            "input_ids":      torch.tensor(self.input_ids[i],      dtype=torch.long),
            "attention_mask": torch.tensor(self.attention_mask[i], dtype=torch.long),
        }
        if self.labels is not None:
            item["labels"] = torch.tensor(self.labels[i], dtype=torch.float32)
        return item


class _CodeBERTModel(nn.Module):
    def __init__(self, encoder):
        super().__init__()
        self.encoder    = encoder
        self.dropout    = nn.Dropout(0.1)
        self.classifier = nn.Linear(768, 1)

    def forward(self, input_ids, attention_mask):
        cls = self.encoder(
            input_ids=input_ids, attention_mask=attention_mask
        ).last_hidden_state[:, 0, :]
        return self.classifier(self.dropout(cls)).squeeze(1)


class CodeBERTWrapper(BaseClassifier):
    """
    Fine-tunes microsoft/codebert-base for binary classification.
    First run downloads ~500 MB from HuggingFace (cached afterward).
    Requires CUDA for reasonable training time.
    """

    def __init__(self, cfg):
        self.cfg       = cfg
        self.tokenizer = None
        self.model     = None
        self.device    = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _tokenize(self, texts: list) -> dict:
        return self.tokenizer(
            list(texts),
            max_length  = self.cfg.codebert_max_len,
            padding     = "max_length",
            truncation  = True,
            return_tensors = "np",
        )

    def fit(self, texts: list, y: np.ndarray):
        from transformers import AutoModel, AutoTokenizer

        if self.tokenizer is None:
            self.tokenizer = AutoTokenizer.from_pretrained(self.cfg.codebert_model)

        enc    = self._tokenize(texts)
        ds     = _CodeDataset(enc["input_ids"], enc["attention_mask"], y)
        loader = DataLoader(ds, batch_size=self.cfg.codebert_batch_size, shuffle=True)

        w     = compute_class_weight("balanced", classes=np.array([0, 1]), y=y)
        pos_w = torch.tensor([w[1] / w[0]], dtype=torch.float32).to(self.device)

        encoder    = AutoModel.from_pretrained(self.cfg.codebert_model)
        self.model = _CodeBERTModel(encoder).to(self.device)
        crit       = nn.BCEWithLogitsLoss(pos_weight=pos_w)
        opt        = torch.optim.AdamW(self.model.parameters(), lr=self.cfg.codebert_lr)

        for epoch in range(self.cfg.codebert_epochs):
            self.model.train()
            total = 0.0
            for batch in loader:
                ids  = batch["input_ids"].to(self.device)
                mask = batch["attention_mask"].to(self.device)
                lbls = batch["labels"].to(self.device)
                opt.zero_grad()
                loss = crit(self.model(ids, mask), lbls)
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                opt.step()
                total += loss.item()
            print(f"    [CodeBERT epoch {epoch+1}/{self.cfg.codebert_epochs}]"
                  f" loss={total/len(loader):.4f}")
        return self

    def predict_proba(self, texts: list) -> np.ndarray:
        enc    = self._tokenize(texts)
        ds     = _CodeDataset(enc["input_ids"], enc["attention_mask"])
        loader = DataLoader(ds, batch_size=self.cfg.codebert_batch_size)

        self.model.eval()
        probs = []
        with torch.no_grad():
            for batch in loader:
                ids  = batch["input_ids"].to(self.device)
                mask = batch["attention_mask"].to(self.device)
                p = torch.sigmoid(self.model(ids, mask)).cpu().numpy()
                probs.extend(p)
        probs = np.array(probs)
        return np.column_stack([1 - probs, probs])
