import numpy as np
import pytest

from etl.embeddings.model import SentenceTransformerEmbedder, get_model


class _FakeST:
	"""Minimal stand-in for sentence_transformers.SentenceTransformer."""

	def __init__(self, model_name, **kwargs):
		self._name = model_name
		self.max_seq_length = 512

	def to(self, device):
		return self

	def eval(self):
		return self

	def encode(self, texts, *, batch_size, normalize_embeddings, show_progress_bar, convert_to_numpy):
		out = np.array([[float(i + 1), float(i + 2)] for i in range(len(texts))])
		if normalize_embeddings:
			norms = np.linalg.norm(out, axis=1, keepdims=True)
			out = out / norms
		return out

	def get_sentence_embedding_dimension(self):
		return 2


class _RecordingST(_FakeST):
	"""Fake that records encode() calls like the real SentenceTransformer."""

	def __init__(self, model_name, calls, **kwargs):
		super().__init__(model_name, **kwargs)
		self._calls = calls

	def encode(self, texts, **kwargs):
		self._calls.append((list(texts), kwargs))
		return super().encode(texts, **kwargs)


def test_encode_uses_sentence_transformer(monkeypatch):
	calls = []

	def make(model_name, **kwargs):
		return _RecordingST(model_name, calls, **kwargs)

	monkeypatch.setattr("sentence_transformers.SentenceTransformer", make)

	emb = SentenceTransformerEmbedder(model_name="BAAI/bge-base-en-v1.5", batch_size=2)
	vecs = emb.encode(["a", "b", "c"], batch_size=2)

	assert len(vecs) == 3
	assert all(len(v) == 2 for v in vecs)
	assert len(calls) == 1
	texts, kwargs = calls[0]
	assert texts == ["a", "b", "c"]
	assert kwargs["normalize_embeddings"] is True
	assert kwargs["batch_size"] == 2
	# [1,2] -> [0.4472, 0.8944]
	assert vecs[0][0] == pytest.approx(1 / 5**0.5, rel=1e-4)
	assert vecs[0][1] == pytest.approx(2 / 5**0.5, rel=1e-4)


def test_empty_input_returns_empty(monkeypatch):
	monkeypatch.setattr("sentence_transformers.SentenceTransformer", lambda name, **kwargs: _FakeST(name, **kwargs))
	emb = SentenceTransformerEmbedder(model_name="x")
	assert emb.encode([]) == []


def test_dimension_from_model(monkeypatch):
	monkeypatch.setattr("sentence_transformers.SentenceTransformer", lambda name, **kwargs: _FakeST(name, **kwargs))
	emb = SentenceTransformerEmbedder(model_name="x")
	assert emb.dimension == 2


def test_ping_true_when_model_loads(monkeypatch):
	monkeypatch.setattr("sentence_transformers.SentenceTransformer", lambda name, **kwargs: _FakeST(name, **kwargs))
	emb = SentenceTransformerEmbedder(model_name="x")
	assert emb.ping() is True


def test_ping_false_when_model_load_fails(monkeypatch):
	def boom(name, **kwargs):
		raise RuntimeError("no model")

	monkeypatch.setattr("sentence_transformers.SentenceTransformer", boom)
	emb = SentenceTransformerEmbedder(model_name="x")
	assert emb.ping() is False


def test_get_model_singleton():
	assert get_model() is get_model()