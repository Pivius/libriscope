import { useEffect, useRef, useState } from "react";
import type { MapItem } from "@/components/MapCanvas";
import { levelForZoom } from "./constants";
import type { MapPointsResponse, MapViewport } from "./types";

interface LevelCache {
	cells: Map<string, MapItem>;
}

export function useMapPoints(
	entity: "book" | "author",
	viewport: MapViewport | null,
): { items: MapItem[]; total: number } {
	const [items, setItems] = useState<MapItem[]>([]);
	const [total, setTotal] = useState(0);

	const cachesRef = useRef(new Map<string, LevelCache>());
	const abortRef = useRef<AbortController | null>(null);
	const genRef = useRef(0);

	useEffect(() => {
		if (!viewport) return;

		const z = levelForZoom(viewport.k);
		const caches = cachesRef.current;

		const snapshot = (level: number): MapItem[] => {
			const cache = caches.get(`${entity}:${level}`);
			if (!cache) return [];
			
			const margin = 2 / 2 ** level;
			const nodes = [...cache.cells.values()].filter(
				(n) =>
					n.x >= viewport.x0 - margin &&
					n.x <= viewport.x1 + margin &&
					n.y >= viewport.y0 - margin &&
					n.y <= viewport.y1 + margin,
			);
			nodes.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
			return nodes;
		};

		const publish = (level: number) => {
			const nodes = snapshot(level);
			setItems(nodes);
			setTotal(nodes.reduce((sum, n) => sum + (n.count ?? 1), 0));
		};

		// render
		publish(z);

		const gen = ++genRef.current;
		abortRef.current?.abort();
		const controller = new AbortController();
		abortRef.current = controller;

		const params = new URLSearchParams({
			entity,
			z: String(z),
			x0: String(viewport.x0),
			y0: String(viewport.y0),
			x1: String(viewport.x1),
			y1: String(viewport.y1),
		});

		(async () => {
			try {
				const res = await fetch(`/api/map/points?${params.toString()}`, {
					signal: controller.signal,
				});
				if (!res.ok) {
					throw new Error(`GET /map/points failed: ${res.status}`);
				}
				const data = (await res.json()) as MapPointsResponse;
				if (genRef.current !== gen) return;

				const cacheKey = `${entity}:${data.level}`;
				let cache = caches.get(cacheKey);
				if (!cache) {
					cache = { cells: new Map<string, MapItem>() };
					caches.set(cacheKey, cache);
				}
				for (const n of data.nodes) {
					const prev = cache.cells.get(n.id);

					if (
						prev &&
						prev.label === n.label &&
						prev.x === n.x &&
						prev.y === n.y &&
						prev.count === n.count
					) {
						continue;
					}
					cache.cells.set(n.id, {
						key: n.id,
						label: n.label,
						x: n.x,
						y: n.y,
						count: n.count,
					});
				}
				publish(data.level);
			} catch (err) {
				if ((err as Error).name !== "AbortError") {
					console.error("failed to load map points", err);
				}
			}
		})();

		return () => {
			controller.abort();
		};
	}, [entity, viewport]);

	return { items, total };
}
