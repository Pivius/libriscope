from queue import Queue

from etl.core.canonical import CanonicalItem
from etl.core.pipeline import _SENTINEL, _read_worker, _write_worker


class _FakeAdapter:
	def __init__(self, items):
		self._items = items

	def collate_from_dir(self, processed_dir, enabled=None, max_aux=None):
		return iter(self._items)


class _FakeStore:
	def __init__(self):
		self.flushes = []

	def bulk_upsert(self, items, ids_to_vectors, batch_size=2000):
		self.flushes.append(([i.id for i in items], dict(ids_to_vectors), batch_size))

	def upsert_embedding(self, work_id, vector):
		self.flushes.append(([work_id], {work_id: vector}, "single"))


def _items(n):
	return [CanonicalItem(id=f"/works/{i}W", title=f"book {i}") for i in range(n)]


def _collect(q):
	out = []
	while True:
		payload = q.get()
		if payload is _SENTINEL:
			break
		ids, texts, items = payload
		out.append((ids, texts, items))
	return out


def test_read_worker_chunks_builds_text_and_sends_sentinel():
	items = _items(5)
	in_q = Queue()
	result = {}
	_read_worker(_FakeAdapter(items), "dir", None, None, 2, set(), None, in_q, result)
	chunks = _collect(in_q)
	assert [i for _, _, batch in chunks for i in [c.id for c in batch]] == [f"/works/{i}W" for i in range(5)]
	assert all(len(ids) == len(items) for ids, texts, items in chunks)
	assert chunks[0][1][0] == "book 0"
	assert result["count"] == 5
	assert result["skipped"] == 0


def test_read_worker_skips_existing_and_stops_at_max_works():
	items = _items(10)
	in_q = Queue()
	result = {}
	_read_worker(_FakeAdapter(items), "dir", None, None, 2, {"/works/0W", "/works/5W"}, 5, in_q, result)
	chunks = _collect(in_q)
	processed = [item.id for _, _, batch in chunks for item in batch]
	assert processed == ["/works/1W", "/works/2W", "/works/3W", "/works/4W", "/works/6W"]
	assert result["count"] == 5
	assert result["skipped"] == 2


def test_write_worker_flushes_in_writer_batches():
	store = _FakeStore()
	out_q = Queue()
	payloads = []
	for i in range(0, 6):
		payloads.append(([f"/works/{i}W"], [CanonicalItem(id=f"/works/{i}W", title="x")], [(float(i),)]))
	out_q.put(payloads[0])
	out_q.put(payloads[1])
	out_q.put(_SENTINEL)
	result = {}
	_write_worker(store, out_q, True, result)
	assert store.flushes and store.flushes[0][0] == ["/works/0W", "/works/1W"]
	assert store.flushes[0][1] == {"/works/0W": (0.0,), "/works/1W": (1.0,)}
	assert "exc" not in result


def test_write_worker_records_error_but_keeps_draining():
	class _BoomStore:
		def bulk_upsert(self, items, ids_to_vectors, batch_size=2000):
			raise RuntimeError("boom")

	store = _BoomStore()
	out_q = Queue()
	out_q.put((["/works/0W"], _items(1), [("/works/0W", (1.0,))]))
	out_q.put((["/works/1W"], _items(1), [("/works/1W", (1.0,))]))
	out_q.put(_SENTINEL)
	result = {}
	_write_worker(store, out_q, True, result)
	assert isinstance(result["exc"], RuntimeError)