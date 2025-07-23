import os
import tempfile
from datetime import datetime

from backend.rag_pipeline.extraction.chunks import chunk_legal_sections
from backend.rag_pipeline.extraction.data_embedding import (
    connect_qdrant,
    embed_with_gemini,
    load_embedder_gemini,
    upload_chunks,
)
from dotenv import load_dotenv
from backend.rag_pipeline.extraction.extractor import extract_from_pdf
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from backend.rag_pipeline.logger_config import get_logger

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

# Create a router for modularity
router = APIRouter()

@router.get("/")
async def root():
    return {"message": "Health-check!"}

@router.post("/upload-pdf/")
async def upload_pdf(
    file: UploadFile = File(...),
    save_extract: bool = Query(False, description="Save extracted JSON"),
    save_chunks: bool = Query(False, description="Save chunked JSON"),
):
    """
    Upload a PDF file for processing.

    - save_extract: If true, the extracted content will be saved as JSON.
    - save_chunks: If true, the chunked content will be saved as JSON.
    """
    # Validation for the uploaded file type (only PDF supported!)
    if file.content_type != "application/pdf":
        logger.error("Invalid file type. Must be a PDF.")
        raise HTTPException(status_code=400, detail="File must be a pdf")

    # Validation for output paths if write_outputs is True
    filename_base = os.path.splitext(file.filename)[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(os.getcwd(), "saved_outputs")
    os.makedirs(output_dir, exist_ok=True)

    extracted_path = (
        os.path.join(output_dir, f"{filename_base}_{timestamp}_extracted.json")
        if save_extract
        else None
    )
    chunked_path = (
        os.path.join(output_dir, f"{filename_base}_{timestamp}_chunks.json")
        if save_chunks
        else None
    )

    temp_file_path = None
    try:
        max_file_size = 10 * 1024 * 1024  # 10MB
        # Save the uploaded PDF to a temporary file
        content = await file.read()
        if len(content) > max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds 10MB limit",
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name

        # Step 1: Extract structured content from the PDF
        logger.info(f"Extracting structured content from PDF...{file.filename}")
        data = extract_from_pdf(temp_file_path, output_path=extracted_path)
        if not data:
            logger.error("Failed to extract data.")
            return {"error": "Failed to extract data"}

        # Step 2: Chunk the extracted sections
        logger.info(" Chunking extracted sections...")
        chunks = chunk_legal_sections(data, output_file=chunked_path)
        if not chunks:
            logger.error(" No chunks produced.")
            return {"error": "No chunks produced"}
        logger.info(f"Chunked {len(chunks)} sections.")

        # Step 3: Embed chunks using Gemini
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        logger.info(" Loading Gemini embedder...")
        model = load_embedder_gemini("AIzaSyAmiSB0MWbP7cu0rzOz-Bu1eXFcgbgpEyQ")

        logger.info(f"env file variables.....{os.getenv("QDRANT_URL")}")

        logger.info(" Embedding chunks...")
        for chunk in chunks:
            chunk["vector"] = embed_with_gemini(chunk["content"], model)

        # Step 4: Connect to Qdrant
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        qdrant_url = os.getenv("QDRANT_URL")
        collection = "test_criminal_civil_code"
        vector_dim = len(chunks[0]["vector"])

        # logger.info(f"Qdrant_url: {os.getenv("QDRANT_API_KEY")}")
        logger.info(" Connecting to Qdrant...")
        
        client = connect_qdrant(
            qdrant_api_key,
            qdrant_url,
            collection,
            vector_dim
        )

        # Step 5: Upload embedded chunks to Qdrant
        logger.info("Uploading embedded chunks to Qdrant...")
        upload_chunks(client, collection, chunks)

        logger.info("All done!")
        return {"status": "success", "chunks_uploaded": len(chunks)}

    except Exception as e:
        logger.error(f"Error during processing: {e}")
        raise HTTPException(
            status_code=500, detail=f"Processing error: {str(e)}"
        ) from e

    finally:
        # Clean up the temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)