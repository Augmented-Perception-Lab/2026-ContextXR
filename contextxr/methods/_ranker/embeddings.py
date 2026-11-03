"""Sentence Transformers embedding support for labels and facet descriptions.

Ported from the paper's research code (context_facet_ranker); logic unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

from .loader import EventDataset
from .normalization import clean_display_label


@dataclass
class EmbeddingConfig:
    model_id: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "auto"
    batch_size: int = 32
    normalize_embeddings: bool = True
    truncate_dim: int = 0
    # ContextXR: False skips loading the embedding model (methods that use no soft transfer).
    enabled: bool = True


@dataclass
class EmbeddingStore:
    keys: List[str]
    texts: Dict[str, str]
    matrix: np.ndarray


class SentenceTransformerTextEmbedder:
    """Lazy Sentence Transformers wrapper."""

    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or EmbeddingConfig()
        self._model: Any = None
        self._device: Optional[str] = None

    def __getstate__(self) -> Dict[str, Any]:
        state = dict(self.__dict__)
        state["_model"] = None
        return state

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._model = None

    def _resolve_device(self) -> str:
        if self.config.device and self.config.device != "auto":
            return str(self.config.device)
        try:
            import torch
        except Exception:
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model

        self._device = self._resolve_device()
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError("Could not import sentence-transformers. Install the [embed] extra: pip install 'contextxr[embed]'") from exc

        try:
            kwargs: Dict[str, Any] = {}
            if int(self.config.truncate_dim or 0) > 0:
                kwargs["truncate_dim"] = int(self.config.truncate_dim)
            model = SentenceTransformer(self.config.model_id, **kwargs)
            model = model.to(device=self._device)
        except Exception as exc:
            raise RuntimeError(
                "Could not load the configured Sentence Transformers model "
                f"'{self.config.model_id}'."
            ) from exc

        self._model = model
        return self._model

    def _encode_texts(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        model = self._load_model()
        encode_kwargs: Dict[str, Any] = {
            "sentences": list(texts),
            "batch_size": int(self.config.batch_size),
            "show_progress_bar": False,
            "convert_to_numpy": True,
            "normalize_embeddings": bool(self.config.normalize_embeddings),
        }
        embeddings = model.encode(**encode_kwargs)
        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        return matrix

    def encode_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._encode_texts(texts)

    def encode_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._encode_texts(texts)


class EmbeddingManager:
    def __init__(self, config: EmbeddingConfig | None = None) -> None:
        self.config = config or EmbeddingConfig()
        self.embedder = SentenceTransformerTextEmbedder(self.config)
        self.stores: Dict[str, EmbeddingStore] = {}

    @staticmethod
    def _task_text(label: str) -> str:
        return f"Task: {clean_display_label(label)}"

    @staticmethod
    def _environment_text(label: str) -> str:
        return f"Environment: {clean_display_label(label)}"

    @staticmethod
    def _app_text(label: str, category: str) -> str:
        body = clean_display_label(label)
        if category:
            body = f"{body}. Category: {clean_display_label(category)}"
        return f"App: {body}"

    @staticmethod
    def _facet_text(label: str, description: str, capabilities: Sequence[str]) -> str:
        parts = [f"Facet: {clean_display_label(label)}"]
        if description:
            parts.append(f"Description: {clean_display_label(description)}")
        if capabilities:
            parts.append(
                f"Capabilities: {', '.join(clean_display_label(item) for item in capabilities)}"
            )
        return ". ".join(parts)

    @staticmethod
    def _capability_text(label: str) -> str:
        return f"Capability: {clean_display_label(label)}"

    def fit(self, dataset: EventDataset) -> None:
        if not self.config.enabled:
            self.stores = {}
            return
        texts_by_type: Dict[str, Dict[str, str]] = {
            "task": {
                key: self._task_text(record.label)
                for key, record in dataset.schema.tasks.items()
            },
            "environment": {
                key: self._environment_text(record.label)
                for key, record in dataset.schema.environments.items()
            },
            "app": {
                key: self._app_text(record.label, record.properties.get("category", ""))
                for key, record in dataset.schema.apps.items()
            },
            "facet": {
                key: self._facet_text(
                    record.label,
                    record.properties.get("facet_description", ""),
                    sorted(
                        dataset.schema.relation_adjacency
                        .get("facet_composed_of_capability", {})
                        .get(key, set())
                    ),
                )
                for key, record in dataset.schema.facets.items()
            },
            "capability": {
                key: self._capability_text(record.label)
                for key, record in dataset.schema.capabilities.items()
            },
        }

        self.stores = {}
        for entity_type, text_map in texts_by_type.items():
            keys = list(text_map.keys())
            if not keys:
                self.stores[entity_type] = EmbeddingStore(
                    keys=[],
                    texts={},
                    matrix=np.zeros((0, 0), dtype=np.float32),
                )
                continue
            matrix = self.embedder.encode_documents([text_map[key] for key in keys])
            self.stores[entity_type] = EmbeddingStore(
                keys=keys,
                texts=dict(text_map),
                matrix=matrix,
            )

    @classmethod
    def _query_text(cls, entity_type: str, raw_label: str) -> str:
        label = clean_display_label(raw_label)
        if entity_type == "task":
            return f"Task: {label}"
        if entity_type == "environment":
            return f"Environment: {label}"
        if entity_type == "app":
            return f"App: {label}"
        if entity_type == "facet":
            return f"Facet: {label}"
        if entity_type == "capability":
            return f"Capability: {label}"
        raise KeyError(f"Unsupported embedding entity type: {entity_type}")

    def encode_query(self, entity_type: str, raw_label: str) -> np.ndarray:
        matrix = self.embedder.encode_queries([self._query_text(entity_type, raw_label)])
        if matrix.size == 0:
            return np.zeros((1, 0), dtype=np.float32)
        return matrix

    def nearest(
        self,
        entity_type: str,
        raw_label: str,
        *,
        top_k: int = 5,
        min_similarity: float = 0.0,
        exclude_keys: Iterable[str] = (),
    ) -> List[tuple[str, float]]:
        store = self.stores.get(entity_type)
        if store is None or len(store.keys) == 0 or store.matrix.shape[0] == 0:
            return []
        query_vec = self.encode_query(entity_type, raw_label)
        if query_vec.shape[1] == 0:
            return []
        from sklearn.metrics.pairwise import cosine_similarity

        scores = cosine_similarity(query_vec, store.matrix).ravel()
        excluded = set(str(item) for item in exclude_keys)
        ranked: List[tuple[str, float]] = []
        for index, key in enumerate(store.keys):
            if key in excluded:
                continue
            similarity = float(scores[index])
            if similarity < min_similarity:
                continue
            ranked.append((key, similarity))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked[:top_k]
