import os
import google.generativeai as genai
from qdrant_client import QdrantClient
from dotenv import load_dotenv
from logger_config import get_logger
import requests

load_dotenv()

# Setup logging
logger = get_logger()

# Configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
COLLECTION_NAME = "test_criminal_civil_code"
OLLAMA_MODEL = "tinyllama:1.1b"
TOP_K = 2


# Setup Gemini for embedding
def setup_gemini():
    genai.configure(api_key=GEMINI_API_KEY)

# Embed query using Gemini embedding-001
def embed_query(query):
    logger.info("Generating embedding for the user query...")
    response = genai.embed_content(
        model="models/embedding-001",
        content=query,
        task_type="RETRIEVAL_QUERY"
    )
    return response["embedding"]

# Connect to Qdrant
def connect_qdrant():
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def retrieve_context(client, query_vector, top_k=TOP_K):
    logger.info(f"Retrieving the top: {top_k} context")
    try:
        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
        )
        logger.debug(f"Top results: {results}")
        return results
    except Exception as e:
        logger.error(f"Error during retrieval: {e}")


# Generate response using Ollama (local LLM)
def generate_with_ollama(prompt, model=OLLAMA_MODEL):
    url = "http://localhost:11434/api/generate"
    response = requests.post(url, json={
        "model": model,
        "prompt": prompt,
        "stream": False
    })
    if response.status_code == 200:
        return response.json()['response'].strip()
    else:
        logger.error(f"Ollama error: {response.text}")
        raise RuntimeError(f"Ollama error: {response.text}")

# Generate answer using Ollama and context
def generate_answer(context_chunks, user_query):
    context_text = ""
    for i, chunk in enumerate(context_chunks, start=1):
        context_text += f"[{i}] {chunk.payload.get('title')}\n{chunk.payload.get('content')}\n\n"

    prompt = f"""You are a highly knowledgeable and precise legal assistant. 
        Your task is to provide a clear, concise, and accurate answer based on the Nepali legal context provided below. 
        Only use the information from the context and DO NOT rely on outside knowledge. 
        If the answer is not directly supported by the context, state that explicitly.
        

    Context:
    {context_text}
    Question: {user_query}
    Answer (with reference to specific context numbers where applicable):
    """

    return generate_with_ollama(prompt)

# Main
def main():
    setup_gemini()
    client = connect_qdrant()

    while True:
        user_query = input("🔍 Enter your legal query (or type 'exit'): ").strip()
        if user_query.lower() in ["exit", "quit"]:
            break

        logger.info("Embedding query with Gemini...")
        query_vector = embed_query(user_query)

        logger.info("Retrieving from Qdrant...")
        results = retrieve_context(client, query_vector)

        if not results:
            logger.info("❌ No relevant documents found.")
            continue

        logger.info("Generating answer using Ollama model...")
        answer = generate_answer(results, user_query)

        logger.info("\n🧠 Ollama's Answer:\n")
        logger.info(answer)
        logger.info("\n" + "=" * 80 + "\n")

if __name__ == "__main__":
    main()