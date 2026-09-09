import pytest

from etl.recommend.similarity import mean, normalize, cosine_similarity


def test_mean_centroid():
    assert mean([[1.0, 3.0], [3.0, 1.0]]) == pytest.approx([2.0, 2.0])


def test_mean_empty_raises():
    with pytest.raises(ValueError):
        mean([])


def test_mean_dimension_mismatch_raises():
    with pytest.raises(ValueError):
        mean([[1.0], [1.0, 2.0]])


def test_normalize_unit_vector():
    assert normalize([3.0, 4.0]) == pytest.approx([0.6, 0.8])


def test_normalize_zero_vector_returns_zero():
    assert normalize([0.0, 0.0]) == [0.0, 0.0]


def test_cosine_similarity_identical():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
