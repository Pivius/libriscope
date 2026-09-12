export const WORLD_SCALE = 380; // pixels per unit
export const MAX_Z = 13; // backend grid::MAX_LEVEL / ETL MAX_LEVEL
export const TARGET_CELL_PX = 24; // ~24 px grid cells

// z ≈ round(log2(31.7k)) = cell side (2/2^z world units) ~ 24 px
export function levelForZoom(k: number): number {
	return Math.max(
		0,
		Math.min(MAX_Z, Math.round(Math.log2(((WORLD_SCALE * 2) / TARGET_CELL_PX) * k))),
	);
}
