"use client";

import { useEffect, useRef, useState } from "react";
import type { MapItem } from "./MapCanvas";
import { searchMap } from "@/lib/api";
import type { MapNode } from "@/lib/types";
import styles from "../app/page.module.css";

interface ToolbarProps {
	mode: "books" | "authors";
	onModeChange: (mode: "books" | "authors") => void;
	selectedLabel: string | null;
	onClear: () => void;
	onSearchSelect: (item: MapItem) => void;
	count: number;
}

const SEARCH_DEBOUNCE_MS = 250;

export default function Toolbar({
	mode,
	onModeChange,
	selectedLabel,
	onClear,
	onSearchSelect,
	count,
}: ToolbarProps) {
	const [query, setQuery] = useState("");
	const [search, setSearch] = useState<{ entity: string; items: MapItem[] } | null>(null);
	const [open, setOpen] = useState(false);
	const inputRef = useRef<HTMLInputElement>(null);
	const abortRef = useRef<AbortController | null>(null);

	const entity = mode === "books" ? "book" : "author";

	// debounced server-side search across the whole dataset
	useEffect(() => {
		const q = query.trim();
		if (q.length === 0) return;
		const timer = setTimeout(() => {
			abortRef.current?.abort();
			const controller = new AbortController();
			abortRef.current = controller;
			searchMap(q, entity, 8)
				.then((res) => {
					if (controller.signal.aborted) return;
					setSearch({
						entity,
						items: res.nodes.map((n: MapNode) => ({
							key: n.id,
							label: n.label,
							x: n.x,
							y: n.y,
						})),
					});
				})
				.catch((err) => {
					if ((err as Error).name !== "AbortError") {
						console.error("search failed", err);
					}
				});
		}, SEARCH_DEBOUNCE_MS);
		return () => clearTimeout(timer);
	}, [query, entity]);

	const q = query.trim().toLowerCase();
	const visibleResults =
		q.length === 0 || search === null || search.entity !== entity
			? []
			: search.items;

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
						} else if (e.key === "Enter" && visibleResults.length > 0) {
							choose(visibleResults[0]);
						}
					}}
				/>
				{open && visibleResults.length > 0 ? (
					<div className={styles.searchResults}>
						{visibleResults.map((it) => (
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
