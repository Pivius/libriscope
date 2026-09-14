# Model

This section explains how the recommendation system and map work, from the embedding model through vector search, recommendations, and the 2D projection.

## Embedding input

Each work is encoded from one space-joined string built by `etl/core/text_builder.py`. The fields in order:

1. title
2. subtitle
3. description
4. subjects, sorted
5. genres, sorted
6. author names
7. series

## Vector space

The default model, `BAAI/bge-base-en-v1.5`, is a transformer encoder with CLS pooling. It maps text to a vector in $R^768$. 
L2 normalization places every work vector on the unit sphere:

$$
\|v\| = 1
$$

Cosine similarity between unit vectors reduces to the dot product:

$$
\cos(u, v) = u \cdot v
$$

pgvector stores and indexes the complementary cosine distance:

$$
d(u, v) = 1 - u \cdot v, \qquad d \in [0, 2]
$$

The API defines `similarity = 1 - d` where 1 means identical direction. it's 0 for orthogonal, and negative for opposed directions. 
In practice, text embeddings generally fall in the range [0, 1].

Input length is capped at 512 tokens. Longer metadata is truncated by the tokenizer.

## HNSW index

The `work_embeddings.embedding` and `authors.embedding` use HNSW indexes for the cosine operator class.

The query starts at the top layer, moves to the closest neighbor, and then descends one layer at a time. At the bottom layer, the search widens to include a beam of ef candidates. 
The expected query cost grows logarithmically as the collection size increases.

Insertion uses the same greedy search to pick links for each node, resulting in a total build cost of about $O(N \log N)$ distance computations. 
This project uses the default settings: m = 16 and ef_construction = 64.

On the deployment machine, building the authors index took 40 minutes for 760,449 vectors with 768 dimensions on a GTX 1660, which is about 3 ms per vector. 
Vector storage at that scale is about 2.3 GB in float4.

The build cost is the reason the ETL drops the index before a bulk load and then recreates it at the end. Maintaining the graph per insert on the same table took 88s for the first 50k chunk and 232 s for a later one; this cost grows as the graph size increases.

## Centroids

An author has no text of their own. The author's vector is the mean of their works' vectors:
$$
a = \frac{1}{n} \sum_{i=1}^{n} v_i
$$

The mean of unit vectors has norm at most 1. Equality holds only when every work points the same way, so it measures how much an author's catalog agrees with itself. 
Cosine similarity doesn't change with positive scaling.

A selection of multiple works uses the same construction for the query vector:
$$
q = \frac{1}{k} \sum_{i \in S} v_i
$$

## Recommendations

The backend averages the vectors of the selected works into a query vector q. 
It then runs a knn query.

To limit results to n items, the query uses SELECT, ORDER BY, and LIMIT, with ORDER BY embedding <=>

Results have `similarity = 1, d`. There's a cap of 50 items on the list. 
For neighborhood rays around a selection, the frontend asks for 16 items, and it requests 30 items for shelf recommendations.

The `authors` table follows an identical flow. Since author vectors are centroids of work vectors, 
authors who wrote similar books are close to each other, and the cosine ranking already takes into account shared subject matter.

## Map projection

PCA reduces the n by $d$ matrix of vectors to two dimensions, $d$ being the dimensions of the embedding model.

1. Center each column by subtracting the mean: 

$$
\tilde{X} = X - \bar{X}
$$

1. Singular value decomposition:

$$
\tilde{X} = U S V^T
$$

3. Take v1 and v2, the two right singular vectors with the largest singular values

4. Project the data onto these vectors:

$$
(x, y) = (\tilde{X}v_1, \tilde{X}v_2)
$$

5. Normalize each axis to the range $[-1, 1]$ using min-max scaling

The variance explained by component $i$ is:

$$
\frac{S_i^2}{\sum_j S_j^2}
$$

Books and authors are projected separately using their own PCA, resulting in two distinct spaces.

## LOD grid

World coordinates live in $[-1, 1]$. Level $z$ divides each axis into $2^z$ cells of side $2 / 2^z$. 
To get a coordinate's cell index:

$$
c = \operatorname{clamp}\left(
\left\lfloor (x + 1) \cdot 2^{z-1} \right\rfloor,
0,
2^z - 1
\right)
$$

Each non-empty cell stores a point count, mean position. And a sample entity, the smallest entity ID, making the choice deterministic.

At level 0, there's one cell containing the entire catalog. The cell side at level 13 is about $0.000244$ world units.

Viewport queries convert bounding boxes to cell ranges and scan the index based on $(entity, level, cx, cy)$:

```sql
WHERE entity = $1 AND level = $2
  AND cx BETWEEN $3 AND $4 AND cy BETWEEN $5 AND $6
```

If the range would exceed 4096 cells, the level degrades by one until it fits. 
This means a wide viewport at a high zoom level can never explode the query. The response includes the effective level.

The frontend determines the level based on the zoom factor $k$:

$$ z = \operatorname{clamp}\left( \operatorname{round}(\log_2(31.7k)), 0, 13 \right) $$

This constant keeps cell size close to 24 px. Each cell spans $2^{1-z}$ world units, equivalent to

$$ 2^{1-z} \cdot 380 \cdot k $$

pixels at the frontend scale of 380 px per world unit.

## Quadrant labels

`make axis-labels` labels the four quadrants of each map from Library of Congress classifications. 
Each code's letter prefix maps to a readable label, for example, PS3511.A867 becomes "american literature". 
The score for each term per quadrant is lift times the square root of frequency:

$$
\operatorname{lift} = \frac{c_q / n_q}{c_t / n_t}
$$

$$
\operatorname{score} = \operatorname{lift} \cdot \sqrt{c_q}
$$

c_q is the count of the term in the quadrant, n_q counts all terms in the quadrant, 
c_t counts the term overall and n_t counts all terms overall. 
This favors terms that are concentrated in the quadrant, while the square root keep common terms competitive. 
The top three terms for each quadrant are stored in `frontend/public/axis-labels.json`.

## Selection on the map

Click a dot and it requests its nearest neighbors. Then it draws a ray to each of them. 
Neighbors show up at their real spot on the map if the viewport's already loaded them. 
If not, they show up on a circle around what you've selected, this mechanic will likely be changed in the future. 
The tooltip shows how similar things are, as a percentage. Dots are colored based on their angle around the map's center. 
It's a closed palette, so the color's hue mean direction rather than genre or category for now.

## Limitations

- Axes are variance directions, not named categories. The map is read by considering relative positions.
- Similar hues mean similar directions. Different hues don't mean works are necessarily unrelated.
- Embeddings only has metadata. It does not understand nuance at the prose level.
- Works are kept by the language filter if their title detects as English. 
A translated title can get a non-English work through the filter, and an English title on a foreign edition can also hold one back.