import os
from datetime import datetime
from pathlib import Path

from .chunks import chunk_legal_sections
from .data_embedding import (
    connect_qdrant,
    embed_with_gemini,
    load_embedder_gemini,
    upload_chunks,
)
from dotenv import load_dotenv
from .extractor import extract_from_pdf
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status, Depends
from rag_pipeline.logger_config import get_logger
from auth.routes import get_current_user

from .db import connect_db

load_dotenv(dotenv_path="E:/legal_sathi/backend/.env")
logger = get_logger(__name__)

router = APIRouter()


@router.get("/")
async def root():
    return {"message": "Health-check!"}

# Directory for storing PDFs
UPLOAD_DIR = Path("uploaded_pdfs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/upload-pdf/")
async def upload_pdf(
    file: UploadFile = File(...),
    save_extract: bool = Query(False, description="Save extracted JSON"),
    save_chunks: bool = Query(False, description="Save chunked JSON"),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["id"]
    """
    Upload a PDF file for processing.

    - save_extract: If true, the extracted content will be saved as JSON.
    - save_chunks: If true, the chunked content will be saved as JSON.
    """
    # validation for the uploaded file type(only pdf supported!)
    if file.content_type != "application/pdf":
        logger.error("Invalid file type. Must be a PDF.")
        raise HTTPException(status_code=400, detail="File must be a pdf")

    # Validation for output paths if write_outputs is True
    filename_base = os.path.splitext(file.filename)[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save dir for PDFs
    pdf_dir = os.path.join(os.getcwd(), "uploaded_pdfs")
    os.makedirs(pdf_dir, exist_ok=True)

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
    pdf_file_path = os.path.join(pdf_dir, f"{filename_base}_{timestamp}.pdf")


    try:
        max_file_size = 10 * 1024 * 1024  # 10MB
        # Save the uploaded PDF to a temporary file
        content = await file.read()
        if len(content) > max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds 10MB limit",
            )

         # Save file permanently
        with open(pdf_file_path, "wb") as f:
            f.write(content)

        logger.info(f"PDF saved to {pdf_file_path}")

        # --- INSERT INTO POSTGRESQL ---
        conn = connect_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO documents (user_id, filename, filepath, uploaded_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (user_id, file.filename, pdf_file_path, datetime.now())
        )
        document_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Inserted document metadata into DB with ID={document_id}")

        # Step 1: Extract structured content from the PDF
        logger.info(f"Extracting structured content from PDF...{file.filename}")
        data = extract_from_pdf(pdf_file_path, output_path=extracted_path)
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
        model = load_embedder_gemini(gemini_api_key)

        logger.info(" Embedding chunks...")
        for chunk in chunks:
            chunk["vector"] = embed_with_gemini(chunk["content"], model)

        # Step 4: Connect to Qdrant
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        qdrant_url = os.getenv("QDRANT_URL")
        collection = "test_criminal_civil_code"
        vector_dim = len(chunks[0]["vector"])

        logger.info(" Connecting to Qdrant...")
        client = connect_qdrant(qdrant_api_key, qdrant_url, collection, vector_dim)

        # Step 5: Upload embedded chunks to Qdrant
        logger.info("Uploading embedded chunks to Qdrant...")
        upload_chunks(client, collection, chunks)

        logger.info("All done!")
        return {
            "status": "success", 
            "document_id": document_id,
            "chunks_uploaded": len(chunks),
            "file_path": pdf_file_path
            }

    except Exception as e:
        logger.error(f"Error during processing: {e}")
        raise HTTPException(
            status_code=500, detail=f"Processing error: {str(e)}"
        ) from e

