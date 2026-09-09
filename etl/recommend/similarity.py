from typing import List


def mean(vectors: List[List[float]]) -> List[float]:
    """Mean (centroid) of a list of equal-length vectors."""
    if not vectors:
        raise ValueError("cannot compute centroid of an empty list of vectors")
    n = len(vectors)
    dim = len(vectors[0])
    out = [0.0] * dim
    for vec in vectors:
        if len(vec) != dim:
            raise ValueError("all vectors must have the same dimension")
        for i in range(dim):
            out[i] += vec[i]
    return [v / n for v in out]


def normalize(vec: List[float]) -> List[float]:
    norm = sum(v * v for v in vec) ** 0.5
    if norm == 0:
        return list(vec)
    return [v / norm for v in vec]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
