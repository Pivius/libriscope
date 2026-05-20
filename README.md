# Libriscope

A semantic literature discovery system meant to help readers find literature based on meaning, themes, tone, and personal preferences.

The goal of this project is to explore how vector databases and semantic similarity can be used to recommend literature based on meaning, themes, tone, and reader preference, rather than simple genre matching.

---

## Overview

Libriscope builds a searchable semantic space of literature using:

- Open Library data dumps (works, authors, editions, ratings)
- Embedding models for semantic representation of books
- PostgreSQL with pgvector for similarity search
- A backend API for querying and recommendations
- A frontend UI for exploring similar books

---

## Architecture

The system is split into four main components:

ETL Pipeline (Python) -> PostgreSQL + pgvector -> Backend API -> React Frontend

---

## Core Components

### 1. ETL Pipeline (`/etl`)
- Parses Open Library data dumps
- Cleans and normalizes works, authors, and editions
- Builds embedding-ready text representations
- Generates and stores embeddings

### 2. Database (`/infra`)
- PostgreSQL as primary datastore
- pgvector extension for semantic search
- Stores:
  - Works
  - Authors
  - Ratings
  - Embeddings

### 3. Backend (`/backend`)
- Rust-based API (Axum / Actix)
- Handles:
  - Search queries
  - Book detail retrieval
  - Similarity-based recommendations
- Combines vector similarity + metadata filtering

### 4. Frontend (`/frontend`)
- Web interface for exploring books
- Search and discovery UI
- Book detail pages with recommendations

---

## Data Sources

- Open Library Dumps: https://openlibrary.org/developers/dumps
- Ratings + reading logs (Open Library datasets)

---

## Running the project

Instructions will be added once the initial pipeline is implemented.
