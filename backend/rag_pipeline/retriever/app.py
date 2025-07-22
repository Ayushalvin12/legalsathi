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
from langchain_core.language_models import BaseLLM
from langchain_core.outputs import LLMResult
from qdrant_client import QdrantClient
from transformers import AutoTokenizer, pipeline

from rag_pipeline.embed import setup_gemini
from rag_pipeline.logger_config import get_logger
from rag_pipeline.retriever.routing import retrieve_routed_context
from rag_pipeline.retriever.db import (
    connect_db,
    get_or_create_user,
    create_conversation,
    insert_message,
)

# === FastAPI imports ===
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# === Load environment & setup logger ===
load_dotenv()
logger = get_logger()

# === Config ===
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
COLLECTION_NAME = "labour_act"
OLLAMA_MODEL = "tinyllama:1.1b"
TOP_K = 5

# Load tokenizer
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
memory = ConversationSummaryBufferMemory(
    llm=summarizer_llm, max_token_limit=500, return_messages=True
)


def connect_qdrant():
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def generate_with_ollama(prompt, model=OLLAMA_MODEL):
    url = "http://localhost:11434/api/generate"
    response = requests.post(
        url, json={"model": model, "prompt": prompt, "stream": False}
    )
    if response.status_code == 200:
        return response.json()["response"].strip()
    else:
        raise RuntimeError(f"Ollama error: {response.text}")


def generate_answer(context_chunks, user_query, chat_history):
    context_text = ""
    for i, (chunk, score) in enumerate(context_chunks, start=1):
        context_text += (
            f"[{i}] {chunk.payload.get('title')}\n{chunk.payload.get('content')}\n\n"
        )

    history_text = ""
    for msg in chat_history:
        role = "User" if msg.type == "human" else "Assistant"
        history_text += f"{role}: {msg.content}\n"

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


def save_memory_as_json(memory, log_dir="logs"):
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    session_id = f"session_{timestamp}"
    raw_path = os.path.join(log_dir, f"{session_id}_raw.json")
    summary_path = os.path.join(log_dir, f"{session_id}_summary.txt")
    raw_messages = messages_to_dict(memory.chat_memory.messages)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_messages, f, indent=2, ensure_ascii=False)
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


reranker = MxbaiRerankV2("mixedbread-ai/mxbai-rerank-base-v2", max_length=8192)


def rerank_results_v2(query: str, hits: list, text_key="content"):
    docs = [hit.payload[text_key] for hit in hits]
    results = reranker.rank(query=query, documents=docs, return_documents=False)
    scored = [(hits[result.index], result.score) for result in results]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def save_turn_to_memory_and_db(memory, conn, conversation_id, user_input, answer):
    memory.chat_memory.add_user_message(user_input)
    memory.chat_memory.add_ai_message(answer)
    insert_message(conn, conversation_id, "user", user_input)
    insert_message(conn, conversation_id, "assistant", answer)


# === FastAPI app ===
app = FastAPI()


class QueryRequest(BaseModel):
    user_query: str


# Setup clients once
setup_gemini()
qdrant_client = connect_qdrant()
db_conn = connect_db()
user_id = get_or_create_user(db_conn, "api-user")
conversation_id = create_conversation(db_conn, user_id)


@app.post("/chat")
async def chat_endpoint(request: QueryRequest):
    try:
        user_query = request.user_query.strip()
        if not user_query:
            raise HTTPException(status_code=400, detail="Empty query")

        history = memory.chat_memory.messages
        context = retrieve_routed_context(qdrant_client, user_query, history=history)
        if not context:
            return {"answer": None, "message": "No relevant context found."}

        reranked = rerank_results_v2(user_query, context, text_key="content")
        answer = generate_answer(reranked, user_query, history)

        save_turn_to_memory_and_db(memory, db_conn, conversation_id, user_query, answer)

        return {
            "question": user_query,
            "answer": answer,
        }
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# === CLI mode ===
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Legal RAG assistant")
    parser.add_argument("--mode", choices=["cli", "api"], default="api",
                        help="Run in CLI or API mode (default: api)")
    parser.add_argument("--port", type=int, default=8080,
                        help="Port for API mode (default: 8080)")
    args = parser.parse_args()

    if args.mode == "cli":
        setup_gemini()
        client = connect_qdrant()
        conn = connect_db()
        user_id = get_or_create_user(conn, "test-user")
        conversation_id = create_conversation(conn, user_id)
        print(" Multi-turn Legal Chat")
        while True:
            user_query = input("\n Ask a legal question (or type 'exit'): ").strip()
            if user_query.lower() in {"exit", "quit"}:
                break
            history = memory.chat_memory.messages
            context = retrieve_routed_context(client, user_query, history=history)
            logger.info("Reranking context...")
            reranked = rerank_results_v2(user_query, context, text_key="content")
            if not context:
                print("No relevant context found.")
                continue
            history_text = "\n".join([f"{m.type.upper()}: {m.content}" for m in history])
            context_text = "\n".join(
                doc.payload["content"] for doc in context if "content" in doc.payload
            )
            total_input_tokens = (
                count_tokens(user_query)
                + count_tokens(context_text)
                + count_tokens(history_text)
            )
            history_messages = memory.chat_memory.messages
            logger.info(f"Total tokens: {total_input_tokens}/8192")
            answer = generate_answer(reranked, user_query, history_messages)
            print(f"\n LLaMA: {answer}")
            save_turn_to_memory_and_db(memory, conn, conversation_id, user_query, answer)
        save_memory_as_json(memory)

    else:
        import uvicorn
        uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)


if __name__ == "__main__":
    main()

