import os
import requests
import google.generativeai as genai
from dotenv import load_dotenv
import logging
from langchain_core.messages import BaseMessage
from typing import Dict, Optional
from qdrant_client import QdrantClient
from backend.rag_pipeline.logger_config import get_logger

from backend.rag_pipeline.retriever.embed import embed_query


logger = get_logger()

# === Collection mapping ===
COLLECTION_MAP: Dict[str, str] = {
    "criminal": "criminal_code",
    "civil": "civil_code",
    "labour": "labour_act",
    "constitution": "constitution_law",
}

# === Domain-specific keywords ===
DOMAIN_KEYWORDS: Dict[str, list[str]] = {
    "criminal": ["crime", "theft", "murder", "punishment", "jail", "rape", "arrest"],
    "civil": [
        "divorce",
        "property",
        "marriage",
        "inheritance",
        "contract",
        "ownership",
    ],
    "labour": [
        "labor",
        "employment",
        "strike",
        "salary",
        "work",
        "bonus",
        "termination",
    ],
    "constitution": [
        "president",
        "parliament",
        "constitution",
        "fundamental rights",
        "citizenship",
        "election",
    ],
}


def classify_query_domain(query: str) -> str:
    query_lower = query.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in query_lower for keyword in keywords):
            return domain
    return "criminal"  # Default fallback


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:latest")


def classify_with_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    """Use LLaMA via Ollama to classify domain from prompt."""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        if response.status_code == 200:
            return response.json()["response"].strip()
        else:
            raise RuntimeError(f"Ollama error: {response.text}")
    except Exception as e:
        logger.error(f"Ollama classification error: {e}")
        return "criminal"


def build_domain_prompt(user_query: str, history: Optional[list[BaseMessage]]) -> str:
    history_text = ""
    if history:
        for msg in history[-4:]:
            role = "user" if msg.type == "human" else "Assistant"
            history_text += f"{role}: {msg.content.strip()}\n"
    return f"""
    You are a legal domain classifier.

    Classify the following user question into exactly one of these domains:
    - criminal
    - civil
    - labour
    - constitution

    Use the full context of the conversation to classify the CURRENT QUESTION into exactly one domain.

    Only respond with a single word from the above list.

    Conversation History:
    {history_text.strip()}

    Current User Question:
    {user_query}
    Answer:""".strip()


def classify_query_domain_llama(
    user_query: str, history: Optional[list[BaseMessage]]
) -> str:
    prompt = build_domain_prompt(user_query, history)
    response = classify_with_ollama(prompt)

    domain = response.lower().split()[0]
    if domain not in {"criminal", "civil", "labour", "constitution"}:
        logger.info(f"Ollama raw domain response: '{response}'")
        logger.warning(
            f"Ollama returned unknown domain '{domain}', defaulting to 'criminal'"
        )
        return "criminal"
    return domain


def retrieve_routed_context(
    client: QdrantClient,
    user_query: str,
    history: Optional[list[BaseMessage]] = None,
    top_k: int = 5,
):
    try:
        domain = classify_query_domain_llama(user_query, history)
        collection = COLLECTION_MAP.get(domain)

        if not collection:
            logger.warning(
                f"No collection mapped for domain '{domain}', defaulting to 'criminal_code'"
            )
            collection = "criminal_code"

        logger.info(
            f" Routed query to collection: '{collection}' based on domain: '{domain}'"
        )

        query_vector = embed_query(user_query)  # must return List[float]

        if not query_vector or not isinstance(query_vector, list):
            logger.error(" Embedding failed or returned invalid format.")
            return []

        return client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
        )

    except Exception as e:
        logger.error(f"Retrieval failed for user query '{user_query}': {e}")
        return []
