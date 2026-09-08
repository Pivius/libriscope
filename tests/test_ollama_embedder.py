import pytest

from etl.embeddings.model import OllamaEmbedder


class _FakeResp:
	def __init__(self, payload, status=200):
		self._payload = payload
		self.status_code = status

	def raise_for_status(self):
		if self.status_code >= 400:
			raise RuntimeError(f"HTTP {self.status_code}")

	def json(self):
		return self._payload


def test_encode_parses_and_normalizes(monkeypatch):
	calls = []

	def fake_post(url, json, timeout):
		calls.append((url, json))
		return _FakeResp({"embeddings": [[3.0, 4.0], [0.0, 5.0]]})

	monkeypatch.setattr("requests.post", fake_post)

	emb = OllamaEmbedder(host="http://localhost:11434", model_name="nomic-embed-text")
	vecs = emb.encode(["alpha", "beta"], batch_size=32)

	# [3,4] normalizes to [0.6, 0.8]; [0,5] -> [0,1]
	assert vecs[0] == pytest.approx([0.6, 0.8])
	assert vecs[1] == pytest.approx([0.0, 1.0])

	url, payload = calls[0]
	assert url == "http://localhost:11434/api/embed"
	assert payload["model"] == "nomic-embed-text"
	assert payload["input"] == ["alpha", "beta"]


def test_encode_batches(monkeypatch):
	def fake_post(url, json, timeout):
		return _FakeResp({"embeddings": [[float(i)] for i in range(len(json["input"]))]})

	monkeypatch.setattr("requests.post", fake_post)

	emb = OllamaEmbedder(host="http://x", model_name="m")
	vecs = emb.encode(["a", "b", "c"], batch_size=2)
	assert len(vecs) == 3


def test_ping_true_when_model_present(monkeypatch):
	def fake_get(url, timeout):
		return _FakeResp({"models": [{"name": "nomic-embed-text:latest"}, {"name": "llama3"}]})

	monkeypatch.setattr("requests.get", fake_get)
	emb = OllamaEmbedder(host="http://x", model_name="nomic-embed-text")
	assert emb.ping() is True


def test_ping_false_otherwise(monkeypatch):
	def fake_get(url, timeout):
		raise OSError("down")

	monkeypatch.setattr("requests.get", fake_get)
	emb = OllamaEmbedder(host="http://x", model_name="nomic-embed-text")
	assert emb.ping() is False
