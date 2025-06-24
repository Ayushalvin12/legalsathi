import json
import logging
import time
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
import google.generativeai as genai

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load chunks from JSON
def load_chunks(path):
    with open(path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    if not isinstance(chunks, list):
        raise ValueError("Chunked JSON file must contain a list of chunks")
    for chunk in chunks:
        if not all(key in chunk for key in ["id", "content", "metadata", "title"]):
            raise ValueError(f"Chunk missing required fields (id, content, metadata, title): {chunk}")
    return chunks

# Load Gemini embedding model
def load_embedder_gemini(api_key):
    genai.configure(api_key=api_key)
    return True

# Embed a single chunk with Gemini
def embed_with_gemini(text, model):
    response = genai.embed_content(
        model = "models/embedding-001",  
        content=text,
        task_type="RETRIEVAL_DOCUMENT"
    )
    return response['embedding']

# Connect to Qdrant
def connect_qdrant(api_key, url, collection_name, vector_dim):
    logger.info(f"Connecting to Qdrant at {url}")
    client = QdrantClient(url=url, api_key=api_key, timeout=60)
    if not client.collection_exists(collection_name=collection_name):
        logger.info(f"Creating collection {collection_name} with vector size {vector_dim}")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE)
        )
    return client

# Upload chunks to Qdrant
def upload_chunks(client, collection_name, chunks, batch_size=100, max_retries=3):
    logger.info(f"Uploading {len(chunks)} chunks to collection {collection_name}")
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        points = [
            PointStruct(
                id=chunk["id"],
                vector=chunk["vector"],
                payload={**chunk["metadata"], "title": chunk["title"], "content": chunk["content"]}
            )
            for chunk in batch
        ]
        for attempt in range(max_retries):
            try:
                logger.info(f"Uploading batch {i // batch_size + 1} ({len(points)} points)")
                client.upsert(collection_name=collection_name, points=points)
                break
            except Exception as e:
                logger.error(f"Batch {i // batch_size + 1} failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt + 1 == max_retries:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
    logger.info("Upload complete")

# Main pipeline
def main():
    chunked_path = "./extraction/criminal_code_chunked_with_all.json" 
    gemini_api_key = "AIzaSyAmiSB0MWbP7cu0rzOz-Bu1eXFcgbgpEyQ"  
    qdrant_api_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.XYLxnqdnEgQWlhek0do8deB-UcxcxjYPeeiB5tbeyLQ"
    qdrant_url = "https://d55c959d-3f9d-4589-bc1c-7703aac1e9bc.europe-west3-0.gcp.cloud.qdrant.io:6333"  
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
        client = connect_qdrant(qdrant_api_key, qdrant_url, collection, len(embedded[0]["vector"]))

        logger.info("Uploading to Qdrant...")
        upload_chunks(client, collection, embedded)

        logger.info("✅ Done!")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise

if __name__ == "__main__":
    main()
