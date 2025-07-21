from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

# Connect to Qdrant
client = QdrantClient(
    url="https://d55c959d-3f9d-4589-bc1c-7703aac1e9bc.europe-west3-0.gcp.cloud.qdrant.io",  
    api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.XYLxnqdnEgQWlhek0do8deB-UcxcxjYPeeiB5tbeyLQ"  
)


from qdrant_client.http.models import PayloadSchemaType

# Create index for metadata fields you want to filter by
try:
    client.create_payload_index(
        collection_name="criminal_code",
        field_name="OriginalID",
        field_schema=PayloadSchemaType.KEYWORD
    )
except Exception as e:
    print(f"Could not create index for field: {e}")