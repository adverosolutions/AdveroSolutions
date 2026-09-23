@direction LR
@spacing 60

(1 · Nightly: Re-Index Documents) -> [2 · Pull Documents From Source]
[2 · Pull Documents From Source] -> [3 · Split Documents Into Chunks]
[3 · Split Documents Into Chunks] -> [4 · Ollama: Embed Chunks · local]
[4 · Ollama: Embed Chunks · local] -> [5 · Vector Store: Upsert Chunks · pgvector]
[5 · Vector Store: Upsert Chunks · pgvector] --> [3 · Split Documents Into Chunks]
(6 · User Question) -> [7 · Ollama: Embed the Question · local]
[7 · Ollama: Embed the Question · local] -> [8 · Vector Store: Retrieve Top 20 Chunks]
[8 · Vector Store: Retrieve Top 20 Chunks] -> [9 · Rerank to Top 5 · local model]
[9 · Rerank to Top 5 · local model] -> [10 · Answer With Citations]
[10 · Answer With Citations] -> {11 · Confidence Above Threshold?}
{11 · Confidence Above Threshold?} -> "true" -> [12a · Return Answer + Sources]
{11 · Confidence Above Threshold?} -> "false" -> [12b · Say What Is Missing, Ask to Clarify]
[12a · Return Answer + Sources] -> [[13 · Log Question, Retrieval Hits, Score]]
[12b · Say What Is Missing, Ask to Clarify] -> [[13 · Log Question, Retrieval Hits, Score]]
(14 · Any Node Fails, Anywhere) -> [15 · Alert With a Link to the Failed Run]
[Ollama · local LLM, rerank] --> [9 · Rerank to Top 5 · local model]
[Ollama · local LLM] --> [10 · Answer With Citations]
[Knowledge Graph Lookup · KAG] --> [10 · Answer With Citations]
[[Search More Chunks If Needed · pgvector]] --> [10 · Answer With Citations]
[Ollama Embeddings · local] --> [[Search More Chunks If Needed · pgvector]]
[Answer + Sources + Confidence] --> [10 · Answer With Citations]
