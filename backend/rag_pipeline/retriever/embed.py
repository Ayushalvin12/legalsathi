# embeddings.py or similar file
import os
import google.generativeai as genai


def setup_gemini():
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def embed_query(query):
    result = genai.embed_content(
        model="models/embedding-001", 
        content=query, 
        task_type="RETRIEVAL_QUERY"
    )
    return result["embedding"]  # This must be a list[float]
