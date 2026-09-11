import type {
	AuthorDetail,
	AuthorRecommendResponse,
	Book,
	MapBooksResponse,
	MapAuthorsResponse,
	RecommendResponse,
} from "./types";

const API_PREFIX = "/api";
const MAP_LIMIT = 5000;

async function getJson<T>(path: string): Promise<T> {
	const res = await fetch(`${API_PREFIX}${path}`);

	if (!res.ok) {
		throw new Error(`GET ${path} failed: ${res.status}`);
	}

	return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
	const res = await fetch(`${API_PREFIX}${path}`, {
		method: "POST",
		headers: { "content-type": "application/json" },
		body: JSON.stringify(body),
	});

	if (!res.ok) {
		throw new Error(`POST ${path} failed: ${res.status}`);
	}

	return res.json() as Promise<T>;
}

export function fetchMapBooks(limit = MAP_LIMIT): Promise<MapBooksResponse> {
	return getJson<MapBooksResponse>(`/map/books?limit=${limit}`);
}

export function fetchMapAuthors(limit = MAP_LIMIT): Promise<MapAuthorsResponse> {
	return getJson<MapAuthorsResponse>(`/map/authors?limit=${limit}`);
}

export function fetchBook(id: string): Promise<Book> {
	return getJson<Book>(`/books/${encodeURIComponent(id)}`);
}

export function fetchAuthor(name: string): Promise<AuthorDetail> {
	return getJson<AuthorDetail>(`/authors/${encodeURIComponent(name)}`);
}

export function recommendBooks(
	workIds: string[],
	limit = 30,
	genreMode: "same" | "different" | null = null,
): Promise<RecommendResponse> {
	return postJson<RecommendResponse>("/recommend", {
		work_ids: workIds,
		limit,
		genre_mode: genreMode,
	});
}

export function recommendAuthors(
	names: string[],
	limit = 30,
): Promise<AuthorRecommendResponse> {
	return postJson<AuthorRecommendResponse>("/recommend-authors", {
		author_names: names,
		limit,
	});
}
