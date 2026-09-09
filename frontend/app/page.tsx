"use client";

import { useEffect, useState } from "react";
import MapCanvas, { type MapItem } from "@/components/MapCanvas";
import Toolbar from "@/components/Toolbar";
import { fetchMapAuthors, fetchMapBooks } from "@/lib/api";
import styles from "./page.module.css";

export default function Home() {
	const [mode, setMode] = useState<"books" | "authors">("books");
	const [items, setItems] = useState<MapItem[]>([]);
	const [hovered, setHovered] = useState<MapItem | null>(null);
	const [selected, setSelected] = useState<MapItem | null>(null);
	
	const changeMode = (next: "books" | "authors") => {
		setMode(next);
		setItems([]);
		setSelected(null);
		setHovered(null);
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
	
	return (
		<div className={styles.mapPage}>
		<Toolbar
			mode={mode}
			onModeChange={changeMode}
			selectedLabel={selected?.label ?? null}
			onClear={() => setSelected(null)}
			count={items.length}
		/>
		<MapCanvas
			items={items}
			mode={mode}
			hovered={hovered}
			selected={selected}
			onHover={setHovered}
			onSelect={setSelected}
		/>
		</div>
	);
}
