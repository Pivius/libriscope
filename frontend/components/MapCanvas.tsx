"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { select } from "d3-selection";
import { zoom, zoomIdentity } from "d3-zoom";
import type { D3ZoomEvent, ZoomBehavior } from "d3-zoom";
import styles from "../app/page.module.css";

export interface MapItem {
	key: string;
	label: string;
	x: number;
	y: number;
	workCount?: number;
	similarity?: number;
	neighbor?: boolean;
}

interface MapCanvasProps {
	items: MapItem[];
	neighbors: MapItem[];
	mode: "books" | "authors";
	hovered: MapItem | null;
	selected: MapItem | null;
	onHover: (item: MapItem | null) => void;
	onSelect: (item: MapItem | null) => void;
	focusRequest: { item: MapItem; nonce: number } | null;
}

const WORLD_SCALE = 380; // pixels per unit (coords are in [-1, 1])
const LABEL_MIN_ZOOM = 2.0;
const DOT_RADIUS = 2.4;
const LABEL_FONT = "11px 'Helvetica Neue', 'Hiragino Sans', 'Yu Gothic', 'Noto Sans JP', 'Meiryo', Arial, sans-serif";
const META_FONT = "10px 'Helvetica Neue', 'Hiragino Sans', 'Yu Gothic', 'Noto Sans JP', 'Meiryo', Arial, sans-serif";
const GRID_CELL = 14; 
const RULER_PITCHES = [0.5, 0.25, 0.1, 0.05, 0.02, 0.01];

const PAPER_TOP = "#f5efd8";
const PAPER_BOTTOM = "#ece4c8";
const INK = "#221f1c";
const INK_SOFT = "#848a86";
const INK_OUTLINE = "rgba(34, 31, 28, 0.15)";
const ACCENT = "#e34234";

// interpolated by angle for the dots
const PALETTE: [number, number, number][] = [
	[22, 94, 131], // ai-indigo
	[76, 108, 179], // gunjo
	[47, 158, 120], // rokusho
	[155, 180, 60], // moegi
	[232, 163, 61], // yamabuki
	[227, 66, 52], // shu
	[141, 43, 69], // suou
	[22, 94, 131], 
];

function colorFor(x: number, y: number): string {
	const angle = (Math.atan2(y, x) + Math.PI) / (2 * Math.PI); // [0, 1)
	const seg = angle * (PALETTE.length - 1);
	const i = Math.min(Math.floor(seg), PALETTE.length - 2);
	const f = seg - i;
	const a = PALETTE[i];
	const b = PALETTE[i + 1];
	const r = Math.round(a[0] + (b[0] - a[0]) * f);
	const g = Math.round(a[1] + (b[1] - a[1]) * f);
	const bl = Math.round(a[2] + (b[2] - a[2]) * f);
	return `rgb(${r}, ${g}, ${bl})`;
}

function pickRulerPitch(k: number): number {
	for (const p of RULER_PITCHES) {
		if (p * WORLD_SCALE * k >= 70) return p;
	}
	return RULER_PITCHES[0];
}

function setLetterSpacing(ctx: CanvasRenderingContext2D, value: string) {
	try {
		(ctx as CanvasRenderingContext2D & { letterSpacing: string }).letterSpacing = value;
	} catch {
		throw new Error("Could not set letter spacing.");
	}
}

interface RenderState {
	items: MapItem[];
	neighbors: MapItem[];
	mode: "books" | "authors";
	hovered: MapItem | null;
	selected: MapItem | null;
	onHover: (item: MapItem | null) => void;
	onSelect: (item: MapItem | null) => void;
}

export default function MapCanvas({
	items,
	neighbors,
	mode,
	hovered,
	selected,
	onHover,
	onSelect,
	focusRequest,
}: MapCanvasProps) {
	const canvasRef = useRef<HTMLCanvasElement>(null);
	const wrapRef = useRef<HTMLDivElement>(null);
	const transformRef = useRef(zoomIdentity);
	const zoomRef = useRef<ZoomBehavior<HTMLCanvasElement, unknown> | null>(null);
	const screenRef = useRef<{ item: MapItem; sx: number; sy: number }[]>([]);
	const [tooltip, setTooltip] = useState<{ x: number; y: number } | null>(null);
	
	// latest props accessible from stable handlers
	const stateRef = useRef<RenderState>({
		items,
		neighbors,
		mode,
		hovered,
		selected,
		onHover,
		onSelect,
	});
	useEffect(() => {
		stateRef.current = { items, neighbors, mode, hovered, selected, onHover, onSelect };
	}, [items, neighbors, mode, hovered, selected, onHover, onSelect]);
	
	const draw = useCallback(() => {
		const canvas = canvasRef.current;
		const wrap = wrapRef.current;
		if (!canvas || !wrap) return;

		const ctx = canvas.getContext("2d");
		if (!ctx) return;
		
		const { items: nodes, neighbors: nbrs, mode: m, hovered: hov, selected: sel } =
		stateRef.current;
		
		const dpr = window.devicePixelRatio || 1;
		const w = wrap.clientWidth;
		const h = wrap.clientHeight;

		if (
			canvas.width !== Math.round(w * dpr) ||
			canvas.height !== Math.round(h * dpr)
		) {
			canvas.width = Math.round(w * dpr);
			canvas.height = Math.round(h * dpr);
		}

		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		
		// background: washi gradient + indigo corner wash + warm glow
		const bg = ctx.createLinearGradient(0, 0, 0, h);
		bg.addColorStop(0, PAPER_TOP);
		bg.addColorStop(1, PAPER_BOTTOM);
		ctx.fillStyle = bg;
		ctx.fillRect(0, 0, w, h);

		const corner = ctx.createLinearGradient(w, 0, w * 0.55, h * 0.45);
		corner.addColorStop(0, "rgba(22, 94, 131, 0.10)");
		corner.addColorStop(1, "rgba(22, 94, 131, 0)");
		ctx.fillStyle = corner;
		ctx.fillRect(0, 0, w, h);
		
		const glow = ctx.createRadialGradient(
			w / 2,
			h / 2,
			0,
			w / 2,
			h / 2,
			Math.max(w, h) * 0.6,
		);
		glow.addColorStop(0, "rgba(232, 163, 61, 0.10)");
		glow.addColorStop(1, "rgba(232, 163, 61, 0)");
		ctx.fillStyle = glow;
		ctx.fillRect(0, 0, w, h);
		

		const t = transformRef.current;
		const toScreen = (x: number, y: number): [number, number] => [
			t.applyX(x * WORLD_SCALE + w / 2),
			t.applyY(y * WORLD_SCALE + h / 2),
		];

		// world-coordinate edge rulers (track the viewport as you pan/zoom)
		const pitch = pickRulerPitch(t.k);
		ctx.strokeStyle = "rgba(34, 31, 28, 0.30)";
		ctx.fillStyle = INK_SOFT;
		ctx.font = "9px 'Helvetica Neue', Arial, sans-serif";
		setLetterSpacing(ctx, "0.1em");
		ctx.textBaseline = "alphabetic";

		const worldLeft = (t.invertX(0) - w / 2) / WORLD_SCALE;
		const worldRight = (t.invertX(w) - w / 2) / WORLD_SCALE;
		const worldTop = (t.invertY(0) - h / 2) / WORLD_SCALE;
		const worldBottom = (t.invertY(h) - h / 2) / WORLD_SCALE;

		const firstX = Math.ceil(worldLeft / pitch) * pitch;
		for (let wx = firstX; wx <= worldRight; wx += pitch) {
			const sx = t.applyX(wx * WORLD_SCALE + w / 2);
			ctx.beginPath();
			ctx.moveTo(sx + 0.5, 0);
			ctx.lineTo(sx + 0.5, 10);
			ctx.stroke();
			ctx.fillText(Number(wx.toFixed(3)).toString(), sx + 4, 22);
		}

		const firstY = Math.ceil(worldTop / pitch) * pitch;
		for (let wy = firstY; wy <= worldBottom; wy += pitch) {
			const sy = t.applyY(wy * WORLD_SCALE + h / 2);
			ctx.beginPath();
			ctx.moveTo(0, sy + 0.5);
			ctx.lineTo(10, sy + 0.5);
			ctx.stroke();
			ctx.fillText(Number(wy.toFixed(3)).toString(), 16, sy + 3);
		}

		setLetterSpacing(ctx, "0em");
		
		const screen: { item: MapItem; sx: number; sy: number }[] = [];
		const margin = 80;

		for (const item of nodes) {
			const [sx, sy] = toScreen(item.x, item.y);

			if (sx < -margin || sx > w + margin || sy < -margin || sy > h + margin)
				continue;
			screen.push({ item, sx, sy });
		}
		screenRef.current = screen;

		const nbrScreen = nbrs.map((item) => {
			const [sx, sy] = toScreen(item.x, item.y);
			return { item, sx, sy };
		});
		screenRef.current = screen.concat(nbrScreen);

		const hasNbr = nbrScreen.length > 0;
		const selScreen = screen.find((s) => s.item.key === sel?.key) ?? null;

		// rays from selection to each neighbor
		if (hasNbr && selScreen) {
			ctx.strokeStyle = "rgba(227, 66, 52, 0.28)";
			ctx.lineWidth = 1;
			for (const nb of nbrScreen) {
				ctx.beginPath();
				ctx.moveTo(selScreen.sx, selScreen.sy);
				ctx.lineTo(nb.sx, nb.sy);
				ctx.stroke();
			}
		}

		// base dots (faded while a neighborhood is shown)
		for (const { item, sx, sy } of screen) {
			const isSel = sel?.key === item.key;
			if (isSel) continue;
			const isHov = hov?.key === item.key;
			ctx.globalAlpha = hasNbr ? 0.22 : 1;
			ctx.beginPath();
			ctx.arc(sx, sy, isHov ? 3.5 : DOT_RADIUS, 0, Math.PI * 2);
			ctx.fillStyle = isHov ? INK : colorFor(item.x, item.y);
			ctx.fill();
			if (!isHov) {
				ctx.strokeStyle = INK_OUTLINE;
				ctx.lineWidth = 0.5;
				ctx.stroke();
			}
		}
		ctx.globalAlpha = 1;

		// selected node stays bright
		if (selScreen) {
			ctx.beginPath();
			ctx.arc(selScreen.sx, selScreen.sy, DOT_RADIUS + 3, 0, Math.PI * 2);
			ctx.strokeStyle = PAPER_TOP;
			ctx.lineWidth = 2.5;
			ctx.stroke();
			ctx.beginPath();
			ctx.arc(selScreen.sx, selScreen.sy, 4.5, 0, Math.PI * 2);
			ctx.fillStyle = ACCENT;
			ctx.fill();
		}

		// neighbor dots
		for (const nb of nbrScreen) {
			const isHov = hov?.key === nb.item.key;
			ctx.beginPath();
			ctx.arc(nb.sx, nb.sy, isHov ? 4 : 3, 0, Math.PI * 2);
			ctx.fillStyle = isHov ? INK : ACCENT;
			ctx.fill();
		}
		
		if (t.k >= LABEL_MIN_ZOOM) {
			const cx = w / 2;
			const cy = h / 2;
			const labelSet = hasNbr
				? nbrScreen.concat(selScreen ? [selScreen] : [])
				: screen;
			const sorted = [...labelSet].sort((a, b) => {
				const da = (a.sx - cx) ** 2 + (a.sy - cy) ** 2;
				const db = (b.sx - cx) ** 2 + (b.sy - cy) ** 2;
				return da - db;
			});
			
			type Rect = [number, number, number, number];
			const grid = new Map<string, Rect[]>();
			const occupied = (r: Rect): boolean => {
				const gx0 = Math.floor(r[0] / GRID_CELL);
				const gx1 = Math.floor(r[2] / GRID_CELL);
				const gy0 = Math.floor(r[1] / GRID_CELL);
				const gy1 = Math.floor(r[3] / GRID_CELL);
				const cells: string[] = [];

				for (let gx = gx0; gx <= gx1; gx++)
					for (let gy = gy0; gy <= gy1; gy++) cells.push(`${gx},${gy}`);
				for (const c of cells) {
					const list = grid.get(c);

					if (list)
						for (const r2 of list)
							if (r[0] < r2[2] && r[2] > r2[0] && r[1] < r2[3] && r[3] > r2[1])
								return false;
				}

				for (const c of cells) {
					const list = grid.get(c);
					if (list) list.push(r);
					else grid.set(c, [r]);
				}
				return true;
			};
			
			ctx.font = LABEL_FONT;
			ctx.textBaseline = "middle";
			setLetterSpacing(ctx, "0.04em");
			for (const { item, sx, sy } of sorted) {
				const isSel = sel?.key === item.key;
				const isHov = hov?.key === item.key;
				const text = item.label.length > 48 ? `${item.label.slice(0, 47)}…` : item.label;
				const tw = ctx.measureText(text).width;
				const lx = sx + (isSel ? 8 : 5);
				const r: Rect = [lx, sy - 8, lx + tw + 4, sy + 8];

				if (!occupied(r)) continue;
				
				if (isHov) {
					ctx.fillStyle = ACCENT;
					ctx.fillRect(lx - 3, sy - 8, 1.5, 16);
				}
				ctx.fillStyle = isSel ? ACCENT : INK;
				ctx.fillText(text, lx + 2, sy);
				if (isSel) {
					ctx.strokeStyle = ACCENT;
					ctx.lineWidth = 1;
					ctx.beginPath();
					ctx.moveTo(lx + 2, sy + 10);
					ctx.lineTo(lx + 2 + tw, sy + 10);
					ctx.stroke();
				}
			}
			setLetterSpacing(ctx, "0em");
		}
		
		// bilingual meta line, bottom-left
		const jaUnit = m === "books" ? "本" : "著者";
		ctx.textBaseline = "alphabetic";
		ctx.fillStyle = INK_SOFT;
		ctx.font = META_FONT;
		setLetterSpacing(ctx, "0.22em");
		ctx.fillText(
			`${nodes.length} ${m.toUpperCase()}`,
			16,
			h - 28,
		);
		setLetterSpacing(ctx, "0.08em");
		ctx.fillText(
			`${jaUnit} ${nodes.length}`,
			16,
			h - 14,
		);
		setLetterSpacing(ctx, "0em");
	}, []);

	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;
		
		const zoomBehavior: ZoomBehavior<HTMLCanvasElement, unknown> =
		zoom<HTMLCanvasElement, unknown>()
			.scaleExtent([0.3, 40])
			.on("zoom", (event: D3ZoomEvent<HTMLCanvasElement, unknown>) => {
				transformRef.current = event.transform;
				draw();
			});
		
		select(canvas)
			.call(zoomBehavior)
			.on("dblclick.zoom", null);
		
		select(canvas).call(zoomBehavior);
		
		zoomRef.current = zoomBehavior;
		
		return () => {
			select(canvas).on(".zoom", null);
			zoomRef.current = null;
		};
	}, [draw]);

	useEffect(() => {
		const canvas = canvasRef.current;
		const wrap = wrapRef.current;
		const z = zoomRef.current;
		if (!canvas || !wrap || !z || !focusRequest || !focusRequest.item) return;
		const k = Math.max(transformRef.current.k, 3);
		const lx = focusRequest.item.x * WORLD_SCALE;
		const ly = focusRequest.item.y * WORLD_SCALE;
		const target = zoomIdentity
			.translate(wrap.clientWidth / 2 - k * lx, wrap.clientHeight / 2 - k * ly)
			.scale(k);

		const start = transformRef.current;
		const duration = 600;
		const startTime = performance.now();

		let raf = 0;
		const step = (now: number) => {
			const p = Math.min(1, (now - startTime) / duration);
			const e = 1 - Math.pow(1 - p, 3);
			const t = zoomIdentity
				.translate(
					start.x + (target.x - start.x) * e,
					start.y + (target.y - start.y) * e,
				)
				.scale(start.k + (target.k - start.k) * e);
			transformRef.current = t;
			select(canvas).call(z.transform, t);
			if (p < 1) raf = requestAnimationFrame(step);
		};
		raf = requestAnimationFrame(step);

		return () => cancelAnimationFrame(raf);
	}, [focusRequest]);
	
	useEffect(() => {
		const canvas = canvasRef.current;
		if (!canvas) return;
		
		let down: [number, number] | null = null;
		
		const hitTest = (px: number, py: number): MapItem | null => {
			let best: MapItem | null = null;
			let bestD = Infinity;
			for (const { item, sx, sy } of screenRef.current) {
				const d = (sx - px) ** 2 + (sy - py) ** 2;
				if (d < bestD) {
					bestD = d;
					best = item;
				}
			}
			const threshold =
			transformRef.current.k >= LABEL_MIN_ZOOM ? 10 : 8;
			return bestD <= threshold * threshold ? best : null;
		};
		
		const onMove = (e: MouseEvent) => {
			const rect = canvas.getBoundingClientRect();
			const px = e.clientX - rect.left;
			const py = e.clientY - rect.top;
			stateRef.current.onHover(hitTest(px, py));
			setTooltip({ x: e.clientX, y: e.clientY });
		};
		
		const onDown = (e: MouseEvent) => {
			down = [e.clientX, e.clientY];
		};
		
		const onUp = (e: MouseEvent) => {
			if (!down) return;

			const dx = e.clientX - down[0];
			const dy = e.clientY - down[1];
			down = null;

			if (dx * dx + dy * dy > 25) return; // was a drag

			const rect = canvas.getBoundingClientRect();
			const px = e.clientX - rect.left;
			const py = e.clientY - rect.top;
			stateRef.current.onSelect(hitTest(px, py));
		};
		
		const onLeave = () => {
			stateRef.current.onHover(null);
			setTooltip(null);
		};
		
		canvas.addEventListener("mousemove", onMove);
		canvas.addEventListener("mousedown", onDown);
		canvas.addEventListener("mouseup", onUp);
		canvas.addEventListener("mouseleave", onLeave);
		return () => {
			canvas.removeEventListener("mousemove", onMove);
			canvas.removeEventListener("mousedown", onDown);
			canvas.removeEventListener("mouseup", onUp);
			canvas.removeEventListener("mouseleave", onLeave);
		};
	}, []);
	
	useEffect(() => {
		draw();
		const wrap = wrapRef.current;
		if (!wrap) return;
		const ro = new ResizeObserver(() => draw());
		ro.observe(wrap);
		return () => ro.disconnect();
	}, [draw]);
	
	useEffect(() => {
		draw();
	}, [items, neighbors, mode, hovered, selected, draw]);

	const tooltipItem = hovered;

	return (
		<div ref={wrapRef} className={styles.mapCanvasWrap}>
		<canvas ref={canvasRef} className={styles.mapCanvas} />
		{tooltipItem && tooltip ? (
			<div
				className={styles.tooltip}
				style={{ left: tooltip.x, top: tooltip.y }}
			>
			<div className={styles.title}>{tooltipItem.label}</div>
			{tooltipItem.similarity !== undefined || tooltipItem.workCount !== undefined ? (
				<>
				<div className={styles.rule} />
				{tooltipItem.similarity !== undefined ? (
					<div className={styles.sub}>
						{Math.round(tooltipItem.similarity * 100)}% similar
					</div>
				) : null}
				{tooltipItem.workCount !== undefined ? (
					<div className={styles.sub}>
						{tooltipItem.workCount} works
					</div>
				) : null}
				</>
			) : null}
			</div>
		) : null}
		</div>
	);
}
