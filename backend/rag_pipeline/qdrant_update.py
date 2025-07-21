from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

# Connect to Qdrant
client = QdrantClient(
    url="https://d55c959d-3f9d-4589-bc1c-7703aac1e9bc.europe-west3-0.gcp.cloud.qdrant.io",  
    api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.XYLxnqdnEgQWlhek0do8deB-UcxcxjYPeeiB5tbeyLQ"  
)

collection_name = "criminal_code"  # Replace with your collection name

# Define the payload filter
filter_conditions = Filter(
    must=[
        FieldCondition(
            key="OriginalID",
            match=MatchValue(value="Part-2_Chapter-5_106.")
        )
    ]
)

# Search with the filter (no vector needed if just fetching)
results = client.scroll(
    collection_name=collection_name,
    scroll_filter=filter_conditions,
    with_payload=True,
    with_vectors=False,
    limit=10  # adjust as needed
)

# Display results
for point in results[0]:  # results[0] is the list of points
    print("ID:", point.id)
    print("Vector:", point.vector)
    print("Payload:", point.payload)
    print("-----")


