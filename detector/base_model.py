from abc import ABC, abstractmethod
import numpy as np


class BaseClassifier(ABC):
    """
    All model wrappers implement this interface.
    Each wrapper owns its own featurization (TF-IDF / vocab / BPE).
    """

    @abstractmethod
    def fit(self, texts: list, y: np.ndarray) -> "BaseClassifier": ...

    @abstractmethod
    def predict_proba(self, texts: list) -> np.ndarray:
        """Returns (N, 2): col-0 = P(benign), col-1 = P(webshell)."""
        ...

    def predict(self, texts: list) -> np.ndarray:
        return (self.predict_proba(texts)[:, 1] >= 0.5).astype(int)
