"use client";

import { useRef, useState } from "react";
import type { MapItem } from "./MapCanvas";
import styles from "../app/page.module.css";

interface ToolbarProps {
	mode: "books" | "authors";
	items: MapItem[];
	onModeChange: (mode: "books" | "authors") => void;
	selectedLabel: string | null;
	onClear: () => void;
	onSearchSelect: (item: MapItem) => void;
	count: number;
}

export default function Toolbar({
	mode,
	items,
	onModeChange,
	selectedLabel,
	onClear,
	onSearchSelect,
	count,
}: ToolbarProps) {
	const [query, setQuery] = useState("");
	const [open, setOpen] = useState(false);
	const inputRef = useRef<HTMLInputElement>(null);

	const q = query.trim().toLowerCase();
	const results =
		q.length === 0
			? []
			: items.filter((it) => it.label.toLowerCase().includes(q)).slice(0, 8);

	const choose = (item: MapItem) => {
		onSearchSelect(item);
		setQuery("");
		setOpen(false);
		inputRef.current?.blur();
	};

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

			<div className={styles.search}>
				<input
					ref={inputRef}
					className={styles.searchInput}
					value={query}
					placeholder={mode === "books" ? "SEARCH BOOKS" : "SEARCH AUTHORS"}
					onChange={(e) => {
						setQuery(e.target.value);
						setOpen(true);
					}}
					onFocus={() => setOpen(true)}
					onBlur={() => setOpen(false)}
					onKeyDown={(e) => {
						if (e.key === "Escape") {
							setOpen(false);
							inputRef.current?.blur();
						} else if (e.key === "Enter" && results.length > 0) {
							choose(results[0]);
						}
					}}
				/>
				{open && results.length > 0 ? (
					<div className={styles.searchResults}>
						{results.map((it) => (
							<button
								key={it.key}
								className={styles.searchResult}
								onMouseDown={(e) => {
									e.preventDefault();
									choose(it);
								}}
							>
								<span className={styles.searchResultLabel}>{it.label}</span>
							</button>
						))}
					</div>
				) : null}
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
