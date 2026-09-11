"use client";

import type { MapItem } from "./MapCanvas";
import type { Recommendation } from "@/lib/types";
import styles from "../app/page.module.css";

interface ShelfProps {
	shelf: MapItem[];
	genreMode: "same" | "different" | null;
	results: Recommendation[];
	loading: boolean;
	onGenreMode: (mode: "same" | "different" | null) => void;
	onRecommend: () => void;
	onRemove: (key: string) => void;
	onClear: () => void;
	onSelectResult: (workId: string, label: string) => void;
}

export default function Shelf({
	shelf,
	genreMode,
	results,
	loading,
	onGenreMode,
	onRecommend,
	onRemove,
	onClear,
	onSelectResult,
}: ShelfProps) {
	return (
		<aside className={styles.shelf}>
			<div className={styles.shelfHead}>
				<span className={styles.shelfTitle}>Shelf</span>
				<span className={styles.shelfKana}>本棚</span>
				<span className={styles.shelfCount}>{shelf.length}</span>
				{shelf.length > 0 ? (
					<button className={styles.shelfClear} onClick={onClear}>
						clear
					</button>
				) : null}
			</div>

			{shelf.length > 0 ? (
				<div className={styles.shelfItems}>
					{shelf.map((it) => (
						<div className={styles.shelfItem} key={it.key}>
							<span className={styles.shelfItemLabel}>{it.label}</span>
							<button
								className={styles.shelfRemove}
								onClick={() => onRemove(it.key)}
								aria-label={`remove ${it.label}`}
							>
								×
							</button>
						</div>
					))}
				</div>
			) : (
				<div className={styles.shelfEmpty}>shift+click books to add them</div>
			)}

			<div className={styles.shelfControls}>
				<div className={styles.genreToggle}>
					<button
						className={genreMode === null ? styles.active : ""}
						onClick={() => onGenreMode(null)}
					>
						Any
					</button>
					<button
						className={genreMode === "same" ? styles.active : ""}
						onClick={() => onGenreMode("same")}
					>
						Same
					</button>
					<button
						className={genreMode === "different" ? styles.active : ""}
						onClick={() => onGenreMode("different")}
					>
						Diff
					</button>
				</div>
				<button
					className={styles.recommendBtn}
					onClick={onRecommend}
					disabled={shelf.length === 0 || loading}
				>
					{loading ? "…" : "Recommend"}
				</button>
			</div>

			{results.length > 0 ? (
				<div className={styles.shelfResults}>
					{results.map((rec) => (
						<button
							className={styles.shelfResult}
							key={rec.work_id}
							onClick={() => onSelectResult(rec.work_id, rec.title ?? rec.work_id)}
						>
							<span className={styles.shelfResultLabel}>
								{rec.title ?? rec.work_id}
							</span>
							<span className={styles.shelfResultSim}>
								{Math.round(rec.similarity * 100)}%
							</span>
						</button>
					))}
				</div>
			) : null}
		</aside>
	);
}
