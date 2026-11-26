| Config | Gold page in chunks | All gold pages | Rerank s/step (median, max) |
|---|---|---|---|
| none | 36/50 | 35/50 | - |
| bge-reranker-base@20 | 38/50 | 38/50 | 0.092, 0.133 |
| bge-reranker-base@50 | 35/50 | 34/50 | 0.193, 0.236 |
| bge-reranker-base@100 | 37/50 | 36/50 | 0.354, 0.433 |
| bge-reranker-v2-m3@20 | 38/50 | 37/50 | 0.27, 0.322 |
| bge-reranker-v2-m3@50 | 41/50 | 39/50 | 0.59, 0.731 |
| bge-reranker-v2-m3@100 | 43/50 | 40/50 | 1.086, 1.341 |

Ceiling: a gold page is in the top 100 vector candidates for 49/50.

Per question (1 = gold page in chunks):

| ID | none | bge-reranker-base@20 | bge-reranker-base@50 | bge-reranker-base@100 | bge-reranker-v2-m3@20 | bge-reranker-v2-m3@50 | bge-reranker-v2-m3@100 |
|---|---|---|---|---|---|---|---|
| dev_0001 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev_0004 | 0 | 1 | 1 | 1 | 1 | 1 | 1 |
| dev_0007 | 0 | 1 | 1 | 1 | 0 | 0 | 0 |
| dev_0009 | 1 | 1 | 0 | 0 | 1 | 1 | 1 |
| dev_0014 | 0 | 0 | 0 | 0 | 1 | 1 | 1 |
| dev_0015 | 0 | 1 | 1 | 1 | 1 | 1 | 1 |
| dev_0016 | 0 | 0 | 0 | 1 | 0 | 0 | 1 |
| dev_0024 | 0 | 1 | 1 | 1 | 1 | 1 | 1 |
| dev_0029 | 0 | 0 | 1 | 1 | 0 | 1 | 1 |
| dev_0030 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| dev_0031 | 1 | 1 | 1 | 1 | 0 | 1 | 1 |
| dev_0032 | 1 | 1 | 0 | 0 | 1 | 1 | 1 |
| dev_0038 | 1 | 1 | 0 | 0 | 1 | 1 | 1 |
| dev_0043 | 1 | 0 | 0 | 0 | 1 | 1 | 1 |
| dev_0044 | 0 | 1 | 0 | 0 | 1 | 1 | 1 |
| dev_0045 | 0 | 0 | 0 | 1 | 0 | 0 | 1 |
| dev_0049 | 0 | 0 | 0 | 0 | 0 | 1 | 1 |
