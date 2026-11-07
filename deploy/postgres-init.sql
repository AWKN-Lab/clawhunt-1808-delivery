-- Creates the pgvector extension used by the production knowledge-base path.
-- The embedding table is intentionally standalone: app-created tables land in
-- the same database, and a foreign key here would race the first app start.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_chunks_embedding (
    chunk_id TEXT PRIMARY KEY,
    embedding vector(1536)
);

CREATE INDEX IF NOT EXISTS kb_chunks_embedding_ivfflat
    ON kb_chunks_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
