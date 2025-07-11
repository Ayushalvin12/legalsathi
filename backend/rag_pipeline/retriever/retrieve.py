import os
import json
import requests
import google.generativeai as genai
from qdrant_client import QdrantClient
from dotenv import load_dotenv
from rag_pipeline.logger_config import get_logger
from langchain.memory import ConversationSummaryBufferMemory
from langchain.schema import messages_from_dict, messages_to_dict
from langchain_community.llms import Ollama
import argparse
import tiktoken
import datetime

# packages for BART summarizer
from langchain_core.language_models import BaseLLM
from typing import Optional, List
from langchain_core.outputs import LLMResult
from transformers import pipeline


from db import connect_db, get_or_create_user,create_conversation, insert_message

# === Load environment & setup logger ===
load_dotenv()
logger = get_logger()

# === Config ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
COLLECTION_NAME = "criminal_code"
OLLAMA_MODEL = "tinyllama:1.1b"
TOP_K = 3

# == Token counter ==
tokenizer = tiktoken.get_encoding("cl100k_base")

def count_tokens(text):
    return len(tokenizer.encode(text))
def display_token_stats(name, text, max_tokens=4096):
    tokens = count_tokens(text)
    print(f"\n{name} token count: {tokens}/{max_tokens} ({tokens/max_tokens:.2%})")

#set up for summarizers via CLI
parser = argparse.ArgumentParser(description="Run Legal RAG Chat")
parser.add_argument("--summarizer", choices=["llama", "bart"], default="llama", help="Summarizer to use")
args = parser.parse_args()

if args.summarizer == "llama":
    summarizer_llm = Ollama(model=OLLAMA_MODEL)

# === LangChain memory ===
memory = ConversationSummaryBufferMemory(
    llm=summarizer_llm,
    max_token_limit= 1000,
    return_messages=True
    )

# === Gemini Embedding ===
def setup_gemini():
    genai.configure(api_key=GEMINI_API_KEY)

def embed_query(query):
    response = genai.embed_content(
        model="models/embedding-001",
        content=query,
        task_type="RETRIEVAL_QUERY"
    )
    return response["embedding"]

# === Qdrant Retrieval ===
def connect_qdrant():
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def retrieve_context(client, query_vector, top_k=TOP_K):
    try:
        return client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=top_k,
            with_payload=True,
        )
    except Exception as e:
        logger.error(f"❌ Qdrant Retrieval Failed: {e}")
        return []

# === Ollama Call ===
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
        raise RuntimeError(f"Ollama error: {response.text}")

# === Prompt Composition ===
def generate_answer(context_chunks, user_query, chat_history):
    context_text = ""
    for i, chunk in enumerate(context_chunks, start=1):
        context_text += f"[{i}] {chunk.payload.get('title')}\n{chunk.payload.get('content')}\n\n"

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
        print(f"✅ Summary saved to: {summary_path}")

# === Memory + DB Persistence ===
def save_turn_to_memory_and_db(memory, conn, conversation_id, user_input, assistant_output):
    memory.chat_memory.add_user_message(user_input)
    memory.chat_memory.add_ai_message(assistant_output)

    insert_message(conn, conversation_id, "user", user_input)
    insert_message(conn, conversation_id, "assistant", assistant_output)


# === Main RAG Chat Loop ===
def main():
    setup_gemini()
    client = connect_qdrant()
    conn = connect_db()

    user_id = get_or_create_user(conn, "test-user")
    conversation_id = create_conversation(conn, user_id)

    print("🧠 Multi-turn Legal Chat (LLaMA 3.1 + Qdrant + LangChain Memory)")
    while True:
        user_query = input("\n🔎 Ask a legal question (or type 'exit'): ").strip()
        if user_query.lower() in {"exit", "quit"}:
            break

        query_vector = embed_query(user_query)
        context = retrieve_context(client, query_vector)
        logger.info(f"retrieved context {context}")

        if not context:
            print(" No relevant legal context found.")
            logger.info(" No relevant documents found.")
            continue

        # Get memory as list of messages
        history_messages = memory.chat_memory.messages

        # Generate response using Ollama
        logger.info("Generating answer using Ollama model...")
        answer = generate_answer(context, user_query, history_messages)

        # Display and update memory
        print(f"\n LLaMA: {answer}")
        save_turn_to_memory_and_db(memory, conn, conversation_id, user_query, answer)

        logger.info("\n Ollama's Answer:\n")
        logger.info(answer)
        logger.info("\n" + "=" * 80 + "\n")

        logger.info("Saved to a file")
    save_memory_as_json(memory)
    conn.close()

if __name__ == "__main__":
    main()
