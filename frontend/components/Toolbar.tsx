"use client";

import styles from "../app/page.module.css";

interface ToolbarProps {
	mode: "books" | "authors";
	onModeChange: (mode: "books" | "authors") => void;
	selectedLabel: string | null;
	onClear: () => void;
	count: number;
}

export default function Toolbar({
	mode,
	onModeChange,
	selectedLabel,
	onClear,
	count,
}: ToolbarProps) {
	return (
		<header className={styles.toolbar}>
			<div className={styles.brand}>
				<span className={styles.brandMark} />
				<div className={styles.brandText}>
					<span className={styles.brandKana}>リブリスコープ</span>
					<span className={styles.brandLatin}>Libriscope</span>
				</div>
			</div>
			
			<div className={styles.toggle}>
				<button
					className={mode === "books" ? styles.active : ""}
					onClick={() => onModeChange("books")}
				>
					<span className={styles.ja}>本</span>
					<span>Books</span>
				</button>
				<button
					className={mode === "authors" ? styles.active : ""}
					onClick={() => onModeChange("authors")}
				>
					<span className={styles.ja}>著者</span>
					<span>Authors</span>
				</button>
			</div>
			
			<div className={styles.countMeta}>{count} 冊</div>
			
			{selectedLabel ? (
				<button className={styles.selectedChip} onClick={onClear}>
				<span className={styles.label}>{selectedLabel}</span>
				<span className={styles.clear}>×</span>
				</button>
			) : null}
		</header>
	);
}
