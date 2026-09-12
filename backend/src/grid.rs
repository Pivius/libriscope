/// Highest LOD level written by the ETL. `cell side = 2 / 2^MAX_LEVEL`
pub const MAX_LEVEL: i32 = 13;

/// Index of the grid cell containing `coord` at `level`.
///
/// World coords are in [-1, 1]; cell `c` spans world
/// `[-1 + c * 2/2^level, -1 + (c + 1) * 2/2^level)`. The exact right edge
/// clamps into the last cell so the index is always in
/// [0, 2^level), matching the ETL's `cell_of`.
pub fn cell_of(coord: f64, level: i32) -> i32 {
	let span = 1i32 << level;
	let c = ((coord + 1.0) * 0.5 * f64::from(span)).floor() as i64;
	c.clamp(0, i64::from(span) - 1) as i32
}

/// Number of grid cells spanned by the bbox at `level`.
pub fn cell_range_size(x0: f64, x1: f64, y0: f64, y1: f64, level: i32) -> i64 {
	let nx = (i64::from(cell_of(x1, level) - cell_of(x0, level)) + 1).max(1);
	let ny = (i64::from(cell_of(y1, level) - cell_of(y0, level)) + 1).max(1);
	nx * ny
}

#[cfg(test)]
mod tests {
	use super::*;

	#[test]
	fn cell_of_matches_etl_semantics() {
		assert_eq!(cell_of(-1.0, 0), 0);
		assert_eq!(cell_of(1.0, 0), 0);
		assert_eq!(cell_of(0.0, 3), 4);
		assert_eq!(cell_of(-1.0, 3), 0);
		assert_eq!(cell_of(0.999, 3), 7);
		assert_eq!(cell_of(1.0, 3), 7);
		assert_eq!(cell_of(-5.0, 3), 0);
		assert_eq!(cell_of(5.0, 3), 7);
	}

	#[test]
	fn cell_range_size_is_inclusive() {
		assert_eq!(cell_range_size(-1.0, 1.0, -1.0, 1.0, 0), 1);
		assert_eq!(cell_range_size(-1.0, 1.0, -1.0, 1.0, 3), 64);
		assert_eq!(cell_range_size(0.0, 0.001, 0.0, 0.001, 3), 1);
	}
}
