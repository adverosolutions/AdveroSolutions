# Local RAG Pipeline: Ollama Embeddings, Rerank, Cited Answers

```mermaid
flowchart LR
    subgraph sec_ingest["1 · NIGHTLY INGESTION: PULL, CHUNK, EMBED, STORE"]
        direction TB
        nightly(["1 · Nightly: Re-Index Documents"])
        pull["2 · Pull Documents From Source"]
        chunk["3 · Split Documents Into Chunks"]
        embed_docs["4 · Ollama: Embed Chunks · local"]
        upsert["5 · Vector Store: Upsert Chunks · pgvector"]
    end
    subgraph sec_retrieve["2 · RETRIEVE AND RERANK"]
        direction TB
        chat(["6 · User Question"])
        embed_q["7 · Ollama: Embed the Question · local"]
        topk["8 · Vector Store: Retrieve Top 20 Chunks"]
        rerank{{"9 · Rerank to Top 5 · local model"}}
        rerank_model{{"Ollama · local LLM, rerank<br/><i>ollama</i>"}}
    end
    subgraph sec_answer["3 · ANSWER WITH CITATIONS (LOCAL LLM + KAG)"]
        direction TB
        agent{{"10 · Answer With Citations"}}
        model{{"Ollama · local LLM<br/><i>ollama</i>"}}
        kag{{"Knowledge Graph Lookup · KAG<br/><i>http</i>"}}
        vstore{{"Search More Chunks If Needed · pgvector<br/><i>supabase</i>"}}
        embed_tool{{"Ollama Embeddings · local<br/><i>ollama</i>"}}
        parser{{"Answer + Sources + Confidence"}}
    end
    subgraph sec_respond["4 · RESPOND, OR ASK TO CLARIFY, AND TRACK ACCURACY"]
        direction TB
        confident{"11 · Confidence Above Threshold?"}
        reply_ok["12a · Return Answer + Sources"]
        reply_clarify["12b · Say What Is Missing, Ask to Clarify"]
        log[("13 · Log Question, Retrieval Hits, Score<br/><i>googleSheets</i>")]
    end
    subgraph sec_reliability["5 · RELIABILITY"]
        direction TB
        err(["14 · Any Node Fails, Anywhere<br/><i>n8n</i>"])
        alert["15 · Alert With a Link to the Failed Run<br/><i>slack</i>"]
    end
    nightly --> pull
    pull --> chunk
    chunk --> embed_docs
    embed_docs --> upsert
    upsert -.->|loop| chunk
    chat --> embed_q
    embed_q --> topk
    topk --> rerank
    rerank --> agent
    agent --> confident
    confident -->|true| reply_ok
    confident -->|false| reply_clarify
    reply_ok --> log
    reply_clarify --> log
    err --> alert
    rerank_model -.- rerank
    model -.- agent
    kag -.- agent
    vstore -.- agent
    embed_tool -.- vstore
    parser -.- agent
    style sec_ingest fill:#dbeafe,stroke:#94a3b8,color:#0f172a
    style sec_retrieve fill:#dcfce7,stroke:#94a3b8,color:#0f172a
    style sec_answer fill:#ede9fe,stroke:#94a3b8,color:#0f172a
    style sec_respond fill:#f1f5f9,stroke:#94a3b8,color:#0f172a
    style sec_reliability fill:#fef9c3,stroke:#94a3b8,color:#0f172a
```

- **1 · NIGHTLY INGESTION: PULL, CHUNK, EMBED, STORE** — Every night the source documents are pulled, cut into chunks, embedded on a local Ollama model and written to the vector store. Nothing leaves the box.
- **2 · RETRIEVE AND RERANK** — The question is embedded the same way, the 20 nearest chunks come back, and a local model reranks them to the 5 that actually answer it.
- **3 · ANSWER WITH CITATIONS (LOCAL LLM + KAG)** — The agent answers only from the reranked chunks and the knowledge graph. It has to return sources and a confidence score, not just text.
- **4 · RESPOND, OR ASK TO CLARIFY, AND TRACK ACCURACY** — Confident answers go back with sources. Weak ones say what is missing. Every question is logged so accuracy can be measured week over week.
- **5 · RELIABILITY** — Any failure anywhere raises an alert with a link to the run. Nothing fails silently.
