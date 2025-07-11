import json
import os
import time

import google.generativeai as genai
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from rag_pipeline.logger_config import get_logger
from tqdm import tqdm

load_dotenv()

# Set up logging
logger = get_logger(__name__)


# Load chunks from JSON
def load_chunks(path):
    with open(path, encoding="utf-8") as f:
        chunks = json.load(f)
    if not isinstance(chunks, list):
        raise ValueError("Chunked JSON file must contain a list of chunks")
    for chunk in chunks:
        if not all(key in chunk for key in ["id", "content", "metadata", "title"]):
            raise ValueError(
                f"Chunk missing required fields (id, content, metadata, title): {chunk}"
            )
    return chunks


# Load Gemini embedding model
def load_embedder_gemini(api_key):
    genai.configure(api_key=api_key)
    return True


# Embed a single chunk with Gemini
def embed_with_gemini(text, model):
    response = genai.embed_content(
        model="models/embedding-001", content=text, task_type="RETRIEVAL_DOCUMENT"
    )
    return response["embedding"]


# Connect to Qdrant
def connect_qdrant(api_key, url, collection_name, vector_dim):
    logger.info(f"Connecting to Qdrant at {url}")
    client = QdrantClient(url=url, api_key=api_key, timeout=60)
    if not client.collection_exists(collection_name=collection_name):
        logger.info(
            f"Creating collection {collection_name} with vector size {vector_dim}"
        )
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )
    return client


# Upload chunks to Qdrant
def upload_chunks(client, collection_name, chunks, batch_size=100, max_retries=3):
    logger.info(f"Uploading {len(chunks)} chunks to collection {collection_name}")
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        points = [
            PointStruct(
                id=chunk["id"],
                vector=chunk["vector"],
                payload={
                    **chunk["metadata"],
                    "title": chunk["title"],
                    "content": chunk["content"],
                },
            )
            for chunk in batch
        ]
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Uploading batch {i // batch_size + 1} ({len(points)} points)"
                )
                client.upsert(collection_name=collection_name, points=points)
                break
            except Exception as e:
                logger.error(
                    f"Batch {i // batch_size + 1} failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt + 1 == max_retries:
                    raise
                time.sleep(2**attempt)  # Exponential backoff
    logger.info("Upload complete")


# Main pipeline
def main():
    chunked_path = "./extraction/criminal_code_chunked_with_all.json"
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    qdrant_url = os.getenv("QDRANT_URL")
    collection = "test_criminal_civil_code"

    try:
        chunks = load_chunks(chunked_path)
        logger.info(f"Loaded {len(chunks)} chunks from {chunked_path}")

        model = load_embedder_gemini(gemini_api_key)
        logger.info("Embedding chunks with Gemini...")

        embedded = []
        for chunk in tqdm(chunks, desc="Embedding"):
            vec = embed_with_gemini(chunk["content"], model)
            chunk["vector"] = vec
            embedded.append(chunk)

        logger.info("Connecting to Qdrant...")
        client = connect_qdrant(
            qdrant_api_key, qdrant_url, collection, len(embedded[0]["vector"])
        )

        logger.info("Uploading to Qdrant...")
        upload_chunks(client, collection, embedded)

        logger.info("✅ Done!")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise


if __name__ == "__main__":
    main()
