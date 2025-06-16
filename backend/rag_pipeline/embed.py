import json
import numpy as np
from sentence_transformers import SentenceTransformer

input_path = "../chunks/civil_code_chunked.json"
output_path = "../embeddings/civil_code_embedding.json"

def embed_chunks(input_file, output_file, model_name="all-MiniLM-L6-v2"):
    with open(input_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    model = SentenceTransformer(model_name)

    texts = [chunk["content"] for chunk in chunks]
    embeddings = model.encode(texts, show_progress_bar=True)

    embedded_chunks = [
        {
            "id": chunk["id"],
            "title":chunk["title"],
            "content": chunk["content"],
            "embedding": embedding.tolist(),
            "metadata": chunk.get("metadata",{})
        }
        for chunk, embedding in zip(chunks, embeddings)
    ]

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(embedded_chunks, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Embedded {len(embedded_chunks)} chunks and saved to '{output_file}'")

if __name__ == "__main__":
    embed_chunks(input_path, output_path)