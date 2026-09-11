export interface Book {
	id: string;
	title: string | null;
	subtitle: string | null;
	description: string | null;
	subjects: string[];
	genres: string[];
	authors: string[];
	languages: string[];
	first_publish_date: string | null;
	series: string[];
}

export interface MapNode {
	id: string;
	label: string;
	x: number;
	y: number;
}

export interface MapBooksResponse {
	nodes: MapNode[];
	total: number;
}

export interface AuthorNode {
	name: string;
	work_count: number;
	x: number;
	y: number;
}

export interface MapAuthorsResponse {
	nodes: AuthorNode[];
	total: number;
}

export interface AuthorDetail {
	name: string;
	work_count: number;
	works: Book[];
}

export interface Recommendation {
	work_id: string;
	title: string | null;
	similarity: number;
}

export interface RecommendResponse {
	recommendations: Recommendation[];
}

export interface AuthorRecommendation {
	name: string;
	similarity: number;
}

export interface AuthorRecommendResponse {
	recommendations: AuthorRecommendation[];
}
