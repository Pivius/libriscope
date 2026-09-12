"use client";

import { useEffect, useRef, useState } from "react";
import MapCanvas, { type MapItem } from "@/components/MapCanvas";
import Toolbar from "@/components/Toolbar";
import Shelf from "@/components/Shelf";
import { recommendAuthors, recommendBooks } from "@/lib/api";
import { useMapPoints } from "@/lib/useMapPoints";
import type {
	MapViewport,
	Recommendation,
	AuthorRecommendation,
} from "@/lib/types";
import styles from "./page.module.css";

const NEIGHBOR_LIMIT = 16;
const RADIAL_SPREAD = 0.35;

function buildBookNeighbors(
	recs: Recommendation[],
	center: MapItem,
	items: MapItem[],
): MapItem[] {
	return recs.map((rec, i) => {
		const angle = (2 * Math.PI * i) / recs.length - Math.PI / 2;
		const radius = (1 - rec.similarity) * RADIAL_SPREAD;
		const key = rec.work_id;
		const base = items.find((it) => it.key === key);
		return {
			key,
			label: rec.title ?? key,
			x: center.x + Math.cos(angle) * radius,
			y: center.y + Math.sin(angle) * radius,
			similarity: rec.similarity,
			neighbor: true,
			workCount: base?.workCount,
		};
	});
}

function buildAuthorNeighbors(
	recs: AuthorRecommendation[],
	center: MapItem,
	items: MapItem[],
): MapItem[] {
	return recs.map((rec, i) => {
		const angle = (2 * Math.PI * i) / recs.length - Math.PI / 2;
		const radius = (1 - rec.similarity) * RADIAL_SPREAD;
		const base = items.find((it) => it.key === rec.name);
		return {
			key: rec.name,
			label: rec.name,
			x: center.x + Math.cos(angle) * radius,
			y: center.y + Math.sin(angle) * radius,
			similarity: rec.similarity,
			neighbor: true,
			workCount: base?.workCount,
		};
	});
}

export default function Home() {
	const [mode, setMode] = useState<"books" | "authors">("books");
	const [viewport, setViewport] = useState<MapViewport | null>(null);
	const { items, total } = useMapPoints(mode === "books" ? "book" : "author", viewport);
	const [hovered, setHovered] = useState<MapItem | null>(null);
	const [selected, setSelected] = useState<MapItem | null>(null);
	const [neighbors, setNeighbors] = useState<MapItem[]>([]);
	const [focusRequest, setFocusRequest] = useState<{ item: MapItem; nonce: number } | null>(null);
	const [shelf, setShelf] = useState<MapItem[]>([]);
	const [genreMode, setGenreMode] = useState<"same" | "different" | null>(null);
	const [shelfResults, setShelfResults] = useState<Recommendation[]>([]);
	const [shelfLoading, setShelfLoading] = useState(false);

	const changeMode = (next: "books" | "authors") => {
		setMode(next);
		setSelected(null);
		setHovered(null);
		setNeighbors([]);
		setShelf([]);
		setShelfResults([]);
		setGenreMode(null);
	};

	const resolveBase = (item: MapItem): MapItem => items.find((it) => it.key === item.key) ?? item;

	const toggleShelf = (item: MapItem) => {
		const base = resolveBase(item);
		setShelf((prev) =>
			prev.some((it) => it.key === base.key)
				? prev.filter((it) => it.key !== base.key)
				: [...prev, base],
		);
	};

	const handleSelect = (item: MapItem | null, shiftKey?: boolean) => {
		if (shiftKey && mode === "books" && item) {
			toggleShelf(item);
			return;
		}
		if (item) {
			setSelected(resolveBase(item));
		} else {
			setSelected(null);
			setNeighbors([]);
		}
	};

	const handleSearchSelect = (item: MapItem) => {
		const base = resolveBase(item);
		setSelected(base);
		setFocusRequest((prev) => ({ item: base, nonce: (prev?.nonce ?? 0) + 1 }));
	};

	const handleRecommend = async () => {
		if (shelf.length === 0) return;
		setShelfLoading(true);
		try {
			const res = await recommendBooks(
				shelf.map((it) => it.key),
				30,
				genreMode,
			);
			setShelfResults(res.recommendations);
		} catch (err) {
			console.error("failed to recommend from shelf", err);
		} finally {
			setShelfLoading(false);
		}
	};

	const handleSelectResult = (workId: string, label: string) => {
		const base = items.find((it) => it.key === workId) ?? { key: workId, label, x: 0, y: 0 };
		setSelected(base);
		setFocusRequest((prev) => ({ item: base, nonce: (prev?.nonce ?? 0) + 1 }));
	};

	const selectedItem = selected
		? (items.find((it) => it.key === selected.key) ?? selected)
		: null;

	const itemsRef = useRef(items);
	useEffect(() => {
		itemsRef.current = items;
	}, [items]);

	useEffect(() => {
		let cancelled = false;

		if (!selectedItem) return;

		(async () => {
			try {
				if (mode === "books") {
					const res = await recommendBooks([selectedItem.key], NEIGHBOR_LIMIT);
					if (!cancelled) setNeighbors(buildBookNeighbors(res.recommendations, selectedItem, itemsRef.current));
				} else {
					const res = await recommendAuthors([selectedItem.key], NEIGHBOR_LIMIT);
					if (!cancelled) setNeighbors(buildAuthorNeighbors(res.recommendations, selectedItem, itemsRef.current));
				}
			} catch (err) {
				console.error("failed to fetch recommendations", err);
			}
		})();

		return () => {
			cancelled = true;
		};
	}, [selectedItem, mode]);

	return (
		<div className={styles.mapPage}>
		<Toolbar
			mode={mode}
			items={items}
			onModeChange={changeMode}
			selectedLabel={selectedItem?.label ?? null}
			onClear={() => handleSelect(null)}
			onSearchSelect={handleSearchSelect}
			count={total}
		/>
		<MapCanvas
			items={items}
			neighbors={neighbors}
			mode={mode}
			hovered={hovered}
			selected={selectedItem}
			total={total}
			onHover={setHovered}
			onSelect={handleSelect}
			focusRequest={focusRequest}
			onViewport={setViewport}
		/>
		{mode === "books" ? (
			<Shelf
				shelf={shelf}
				genreMode={genreMode}
				results={shelfResults}
				loading={shelfLoading}
				onGenreMode={setGenreMode}
				onRecommend={handleRecommend}
				onRemove={(key) => setShelf((prev) => prev.filter((it) => it.key !== key))}
				onClear={() => {
					setShelf([]);
					setShelfResults([]);
				}}
				onSelectResult={handleSelectResult}
			/>
		) : null}
		</div>
	);
}
