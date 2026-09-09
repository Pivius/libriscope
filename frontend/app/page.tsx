"use client";

import { useEffect, useState } from "react";
import MapCanvas, { type MapItem } from "@/components/MapCanvas";
import Toolbar from "@/components/Toolbar";
import {
	fetchMapAuthors,
	fetchMapBooks,
	recommendAuthors,
	recommendBooks,
} from "@/lib/api";
import type { Recommendation, AuthorRecommendation } from "@/lib/types";
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
	const [items, setItems] = useState<MapItem[]>([]);
	const [hovered, setHovered] = useState<MapItem | null>(null);
	const [selected, setSelected] = useState<MapItem | null>(null);
	const [neighbors, setNeighbors] = useState<MapItem[]>([]);
	const [focusRequest, setFocusRequest] = useState<{ item: MapItem; nonce: number } | null>(null);

	const changeMode = (next: "books" | "authors") => {
		setMode(next);
		setItems([]);
		setSelected(null);
		setHovered(null);
		setNeighbors([]);
	};

	const resolveBase = (item: MapItem): MapItem => items.find((it) => it.key === item.key) ?? item;

	const handleSelect = (item: MapItem | null) => {
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

	useEffect(() => {
		let cancelled = false;

		(async () => {
			try {
				if (mode === "books") {
					const nodes = await fetchMapBooks();

					if (!cancelled)
						setItems(
						nodes.map((n) => ({ key: n.id, label: n.label, x: n.x, y: n.y })),
					);
				} else {
					const nodes = await fetchMapAuthors();

					if (!cancelled)
						setItems(
						nodes.map((n) => ({
							key: n.name,
							label: n.name,
							x: n.x,
							y: n.y,
							workCount: n.work_count,
						})),
					);
				}
			} catch (err) {
				console.error("failed to load map", err);
			}
		})();

		return () => {
			cancelled = true;
		};
	}, [mode]);

	useEffect(() => {
		let cancelled = false;

		if (!selected) return;

		(async () => {
			try {
				if (mode === "books") {
					const res = await recommendBooks([selected.key], NEIGHBOR_LIMIT);
					if (!cancelled) setNeighbors(buildBookNeighbors(res.recommendations, selected, items));
				} else {
					const res = await recommendAuthors([selected.key], NEIGHBOR_LIMIT);
					if (!cancelled) setNeighbors(buildAuthorNeighbors(res.recommendations, selected, items));
				}
			} catch (err) {
				console.error("failed to fetch recommendations", err);
			}
		})();

		return () => {
			cancelled = true;
		};
	}, [selected, mode, items]);

	return (
		<div className={styles.mapPage}>
		<Toolbar
			mode={mode}
			items={items}
			onModeChange={changeMode}
			selectedLabel={selected?.label ?? null}
			onClear={() => handleSelect(null)}
			onSearchSelect={handleSearchSelect}
			count={items.length}
		/>
		<MapCanvas
			items={items}
			neighbors={neighbors}
			mode={mode}
			hovered={hovered}
			selected={selected}
			onHover={setHovered}
			onSelect={handleSelect}
			focusRequest={focusRequest}
		/>
		</div>
	);
}
