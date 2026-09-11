import pytest

from etl.jobs.run_map_grids import aggregate_rows, cell_of, MAX_LEVEL


@pytest.mark.parametrize("level", range(MAX_LEVEL + 1))
def test_cell_of_always_in_range(level):
	span = 1 << level
	for i in range(1001):
		coord = -1.0 + 2.0 * i / 1000.0
		assert 0 <= cell_of(coord, level) < span, (coord, level)


def test_cell_of_edge_and_center():
	assert cell_of(-1.0, 0) == 0
	assert cell_of(1.0, 0) == 0  # right edge clamps into the single cell
	assert cell_of(0.0, 1) == 1  # (0+1)/2 * 2 = 1
	assert cell_of(1.0, 2) == 3  # clamps to last cell of 4
	assert cell_of(-0.999, 13) >= 0


def test_cell_of_partition():
	# a coord exactly on a cell boundary goes to the higher cell
	assert cell_of(0.0, 2) == 2          # boundary of cells 1 and 2
	assert cell_of(-0.5, 1) == 0         # (-0.5+1)/2*2 = 0.5 -> floor 0


def test_aggregate_rows_averages_and_deterministic_sample():
	# level 1: cell (0,0) covers world x in [-1,0), y in [-1,0)
	rows = [
		("z-1", -0.9, -0.1),   # cell (0,0)
		("z-2", -0.5, -0.5),   # cell (0,0), later in entity_id order
		("zz", 0.5, 0.5),      # cell (1,1)
	]
	acc = aggregate_rows(rows, 1)

	# count, x_avg, y_avg over both rows; sample is the first seen by entity_id
	assert acc[(0, 0)] == (2, -0.7, -0.3, "z-1")
	assert acc[(1, 1)] == (1, 0.5, 0.5, "zz")


def test_aggregate_rows_single_cell_at_level_zero():
	acc = aggregate_rows([("a", 0.9, -0.9), ("b", -0.9, 0.9), ("c", 0.1, 0.1)], 0)
	assert acc == {(0, 0): (3, pytest.approx(0.1 / 3), pytest.approx(0.1 / 3), "a")}