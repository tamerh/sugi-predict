from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import faiss
import json
from sentence_transformers import SentenceTransformer
from datetime import datetime

# --- Configuration & Model Loading ---
MODEL_NAME = 'all-MiniLM-L6-v2'
FAISS_INDEX_PATH = "../../data/final/pubmed/master_pubmed_merge3.index" # Using merge3 results
METADATA_PATH = "../../data/final/pubmed/master_metadata_mergee3.json" # Using merge3 metadata

app = FastAPI()

# Load models and data on startup
@app.on_event("startup")
def load_resources():
    app.state.model = SentenceTransformer(MODEL_NAME)
    app.state.index = faiss.read_index(FAISS_INDEX_PATH)
    with open(METADATA_PATH, 'r') as f:
        app.state.metadata = json.load(f)
    print(f"[{datetime.now()}] Resources loaded successfully.")

# --- Data Models ---
class QueryRequest(BaseModel):
    query: str
    top_k: int = 5

class SearchResult(BaseModel):
    pmid: str
    score: float
    text: str

# --- The Adapter Pattern (Data Access Layer) ---
# For now, we'll build a simple FAISS repository directly.
# Later, this can be abstracted into the interface/class structure we discussed.
def search_faiss(query_text: str, top_k: int):
    query_vector = app.state.model.encode([query_text])[0]
    distances, indices = app.state.index.search(query_vector.reshape(1, -1), top_k)
    
    results = []
    for i in range(top_k):
        index_id = str(indices[0][i])
        metadata_item = app.state.metadata.get(index_id)
        if metadata_item:
            results.append(SearchResult(
                pmid=metadata_item['pmid'],
                score=1 - distances[0][i], # Convert L2 distance to a similarity score
                text=metadata_item['chunk_text']
            ))
    return results

# --- API Endpoint ---
@app.post("/search")
async def search(request: QueryRequest):
    """
    Performs a semantic search on the PubMed abstract database.
    This endpoint only does the RETRIEVAL step.
    """
    if not all([hasattr(app.state, 'model'), hasattr(app.state, 'index'), hasattr(app.state, 'metadata')]):
        raise HTTPException(status_code=503, detail="Resources not loaded yet.")

    try:
        results = search_faiss(request.query, request.top_k)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Placeholder for the full RAG endpoint
@app.post("/query")
async def query_with_rag(request: QueryRequest):
    # This is where you will add the OpenAI API call
    # 1. Call search_faiss() to get context
    # 2. Construct a prompt with the context
    # 3. Call OpenAI's API
    # 4. Return the synthesized answer
    return {"message": "RAG endpoint not yet implemented."}