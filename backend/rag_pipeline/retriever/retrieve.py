import argparse
import datetime
import json
import os

import requests
from dotenv import load_dotenv
from langchain.memory import ConversationSummaryBufferMemory
from langchain.schema import messages_to_dict
from langchain_community.llms import Ollama
from mxbai_rerank import MxbaiRerankV2

# packages for BART summarizer
from langchain_core.language_models import BaseLLM
from langchain_core.outputs import LLMResult
from qdrant_client import QdrantClient

# == Token counter ==
from transformers import AutoTokenizer, pipeline

from rag_pipeline.embed import setup_gemini
from rag_pipeline.logger_config import get_logger
from rag_pipeline.routing import retrieve_routed_context

# === Load environment & setup logger ===
load_dotenv()
logger = get_logger()

# === Config ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
COLLECTION_NAME = "labour_act"
OLLAMA_MODEL = "llama3.1:latest"
TOP_K = 5


# Load the LLaMA 3.1 tokenizer
tokenizer = AutoTokenizer.from_pretrained("hf-internal-testing/llama-tokenizer")


def count_tokens(text):
    tokens = tokenizer.encode(text, add_special_tokens=False)
    return len(tokens)


def display_token_stats(name, text, max_tokens=8192):
    token_count = count_tokens(text)
    print(
        f"\n{name} token count: {token_count}/{max_tokens} ({token_count / max_tokens:.2%})"
    )


summarizer_llm = Ollama(model=OLLAMA_MODEL)

# === LangChain memory ===
memory = ConversationSummaryBufferMemory(
    llm=summarizer_llm, max_token_limit=500, return_messages=True
)


# === Qdrant Retrieval ===
def connect_qdrant():
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


# === Ollama Call ===
def generate_with_ollama(prompt, model=OLLAMA_MODEL):
    url = "http://localhost:11434/api/generate"
    response = requests.post(
        url, json={"model": model, "prompt": prompt, "stream": False}
    )
    if response.status_code == 200:
        return response.json()["response"].strip()
    else:
        raise RuntimeError(f"Ollama error: {response.text}")


# === Prompt Composition ===
def generate_answer(context_chunks, user_query, chat_history):
    context_text = ""
    for i, (chunk, score) in enumerate(context_chunks, start=1):
        context_text += (
            f"[{i}] {chunk.payload.get('title')}\n{chunk.payload.get('content')}\n\n"
        )

    # Combine chat history
    history_text = ""
    for msg in chat_history:
        role = "User" if msg.type == "human" else "Assistant"
        history_text += f"{role}: {msg.content}\n"

    # Final prompt with memory and context
    prompt = f"""
        You are a highly knowledgeable and precise legal assistant. 
        Your task is to provide a clear, concise, and accurate answer based on the Nepali legal context provided below. 
        Only use the information from the context and DO NOT rely on outside knowledge. 
        If the answer is not directly supported by the context, state that explicitly. Do NOT invent anything.

        If user asks follow up questions maintain a conversation using the the chat history 
        provided below.

        ### Chat History ###
        {history_text.strip()}

        ### Retrieved Context ###
        {context_text.strip()}

        User Question: {user_query}
        Answer:"""

    return generate_with_ollama(prompt)


# Saving the chat memory
def save_memory_as_json(memory, log_dir="logs"):
    os.makedirs(log_dir, exist_ok=True)

    # Generate unique session ID (e.g., session_20250701_1715)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    session_id = f"session_{timestamp}"

    # File paths
    raw_path = os.path.join(log_dir, f"{session_id}_raw.json")
    summary_path = os.path.join(log_dir, f"{session_id}_summary.txt")

    # Save raw memory
    raw_messages = messages_to_dict(memory.chat_memory.messages)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_messages, f, indent=2, ensure_ascii=False)

    # Save summary
    summary_text = None
    if hasattr(memory, "moving_summary_buffer"):
        summary_text = memory.moving_summary_buffer
    elif hasattr(memory, "buffer_summary"):
        summary_text = memory.buffer_summary

    if summary_text:
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_text)

    print(f"✅ Raw chat saved to: {raw_path}")
    if summary_text:
        print(f" Summary saved to: {summary_path}")

# Setup reranker
reranker = MxbaiRerankV2(
    "mixedbread-ai/mxbai-rerank-base-v2",
    max_length=8192  # default, can be adjusted up to 32k when needed
)

def rerank_results_v2(query: str, hits: list, text_key="content"):
    """
    Rerank hits using mxbai-rerank-v2.
    Returns: List of (hit, score) sorted descending.
    """
    docs = [hit.payload[text_key] for hit in hits]
    results = reranker.rank(
        query=query,
        documents=docs,
        return_documents=False  
    )
    
    scored = [
        (hits[result.index], result.score)
        for result in results
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# === Main RAG Chat Loop ===
def main():
    setup_gemini()
    client = connect_qdrant()
    conn = connect_db()

    user_id = get_or_create_user(conn, "test-user")
    conversation_id = create_conversation(conn, user_id)

    print(" Multi-turn Legal Chat")
    while True:
        user_query = input("\n🔎 Ask a legal question (or type 'exit'): ").strip()
        if user_query.lower() in {"exit", "quit"}:
            break

        history = memory.chat_memory.messages
        context = retrieve_routed_context(client, user_query, history=history)

        logger.info("Reranking the retrieved context for better accuracy...")
        reranked = rerank_results_v2(user_query, context, text_key="content")

        # query_vector = embed_query(user_query)
        # context = retrieve_context(client, query_vector)
        logger.info(f"retrieved context {context}")
        logger.info(f"reranked context {reranked}")


        if not context:
            print(" No relevant legal context found.")
            logger.info(" No relevant documents found.")
            continue

        history_text = "\n".join([f"{m.type.upper()}: {m.content}" for m in history])
        context_text = "\n".join(
            doc.payload["content"] for doc in context if "content" in doc.payload
        )

        # Counting the total input tokens
        total_input_tokens = (
            count_tokens(user_query)
            + count_tokens(context_text)
            + count_tokens(history_text)
        )

        # Get memory as list of messages
        history_messages = memory.chat_memory.messages

        # Generate response using Ollama
        logger.info(f"Total input tokens: {total_input_tokens}/8192")
        logger.info("Generating answer using Ollama model...")
        answer = generate_answer(reranked, user_query, history_messages)

        # Display and update memory
        print(f"\n LLaMA: {answer}")
        save_turn_to_memory_and_db(memory, conn, conversation_id, user_query, answer)

        memory.chat_memory.add_user_message(user_query)
        memory.chat_memory.add_ai_message(answer)
        logger.info("\ntokens {display_token_stats}")
        logger.info("\n Ollama's Answer:\n")
        logger.info(answer)
        logger.info("\n" + "=" * 80 + "\n")

        # logger.info("Saved to a file")
    save_memory_as_json(memory)


if __name__ == "__main__":
    main()
