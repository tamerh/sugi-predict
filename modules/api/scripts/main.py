"""
BioYoda Search API - Main Application

FastAPI application providing semantic search across biomedical literature.
"""
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import time
import logging
from typing import List
from contextlib import asynccontextmanager

from .models import (
    SearchRequest, SearchResponse, SearchResultItem,
    HealthResponse, CollectionInfo, ErrorResponse,
    AskRequest, AskResponse  # RAG models
)
from .search import BioYodaSearchEngine
from .rag import RAGEngine  # RAG engine
from .config import get_config
from . import __version__

import pprint
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
search_engine: BioYodaSearchEngine = None
rag_engine: RAGEngine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    global search_engine, rag_engine
    try:
        logger.info("="*80)
        logger.info("Starting BioYoda Search API v%s", __version__)
        logger.info("="*80)

        # Load configuration
        config = get_config()
        logger.info(f"Configuration loaded")
        logger.info(f"Qdrant URL: {config.qdrant_url}")
        logger.info(f"Model: {config.model_name}")
        logger.info(f"Collections configured: {len(config.collections)}")

        # Initialize search engine
        search_engine = BioYodaSearchEngine(
            qdrant_url=config.qdrant_url,
            model_name=config.model_name,
            timeout=30
        )

        # Initialize RAG engine (if configured)
        if hasattr(config, 'rag') and config.rag:
            logger.info("Initializing RAG engine...")
            logger.info(pprint.pformat(config.rag))
            rag_config = config.rag
            rag_engine = RAGEngine(
                search_engine=search_engine,
                llm_config=rag_config,
                default_collections=rag_config.get('default_collections', ['pubmed_abstracts', 'clinical_trials']),
                default_top_k=rag_config.get('default_top_k', 5),
                max_context_length=rag_config.get('max_context_length', 100000),
                enable_validation=rag_config.get('enable_validation', True)
            )
            logger.info(f"✅ RAG engine initialized with {rag_config.get('provider')} ({rag_config.get('model')})")
        else:
            logger.warning("RAG configuration not found - /ask endpoint will be unavailable")
            rag_engine = None

        logger.info("="*80)
        logger.info("BioYoda Search API ready to serve requests")
        logger.info(f"API available at: http://localhost:8000")
        logger.info(f"Documentation at: http://localhost:8000/docs")
        logger.info("="*80)

    except Exception as e:
        logger.error(f"Failed to start API: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down BioYoda Search API...")


# Initialize FastAPI app
app = FastAPI(
    title="BioYoda Search & RAG API",
    version=__version__,
    description=(
        "Semantic search and AI-powered Q&A for biomedical literature and clinical trials.\n\n"
        "**Features:**\n"
        "- **Semantic Search** (`/search`) - Vector-based search across 30M+ documents\n"
        "- **AI Q&A** (`/ask`) - RAG-powered question answering with citations\n\n"
        "**Data Sources:**\n"
        "- **PubMed abstracts** (30M+ biomedical research papers)\n"
        "- **ClinicalTrials.gov** (500K+ clinical trial records)\n\n"
        "**Technology Stack:**\n"
        "- S-BioBERT embeddings for semantic understanding\n"
        "- Qdrant vector database for efficient retrieval\n"
        "- Claude AI / GPT-4 for answer generation with citations"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS middleware (configure appropriately for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "ValidationError",
            "message": "Invalid request parameters",
            "detail": str(exc)
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTPException",
            "message": exc.detail
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
            "detail": str(exc) if logger.level == logging.DEBUG else None
        }
    )


# API Endpoints
@app.get(
    "/",
    summary="API Root",
    description="Get API information and available endpoints",
    response_model=dict
)
async def root():
    """API root endpoint - provides overview of available endpoints"""
    return {
        "name": "BioYoda Search & RAG API",
        "version": __version__,
        "status": "running",
        "description": "Semantic search and AI-powered Q&A for biomedical literature",
        "endpoints": {
            "health": "/health - Health check",
            "search": "/search (POST) - Semantic search",
            "ask": "/ask (POST) - RAG-powered Q&A with citations",
            "collections": "/collections - List collections",
            "docs": "/docs - Interactive API documentation",
            "redoc": "/redoc - Alternative API documentation"
        },
        "documentation": "https://github.com/your-org/bioyoda",
        "rag_enabled": rag_engine is not None
    }


@app.get(
    "/health",
    summary="Health Check",
    description="Check API health and component status",
    response_model=HealthResponse
)
async def health_check():
    """
    Health check endpoint

    Returns the status of the API and its components:
    - Overall API status
    - Qdrant connection status
    - Model loading status
    - Available collections
    """
    try:
        # Check Qdrant connection
        qdrant_connected = search_engine.health_check()

        # Get available collections
        collections = search_engine.get_all_collections()

        # Determine overall status
        if qdrant_connected and search_engine.model is not None:
            overall_status = "healthy"
        elif qdrant_connected or search_engine.model is not None:
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        return HealthResponse(
            status=overall_status,
            qdrant_connected=qdrant_connected,
            model_loaded=search_engine.model is not None,
            collections_available=collections,
            version=__version__
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: {str(e)}"
        )


@app.get(
    "/collections",
    summary="List Collections",
    description="Get list of available collections with statistics",
    response_model=List[CollectionInfo]
)
async def list_collections():
    """
    List available collections

    Returns information about each collection including:
    - Collection name and description
    - Number of documents
    - Collection status
    - Vector dimension
    """
    try:
        config = get_config()
        collections = search_engine.get_all_collections()

        result = []
        for collection_name in collections:
            # Get collection info from Qdrant
            info = search_engine.get_collection_info(collection_name)

            if info:
                # Get display info from config
                collection_config = config.get_collection_config(collection_name)
                description = collection_config.get('description', f"Collection: {collection_name}") if collection_config else f"Collection: {collection_name}"
                display_name = collection_config.get('display_name', collection_name) if collection_config else collection_name

                result.append(CollectionInfo(
                    name=info['name'],
                    description=description,
                    display_name=display_name,
                    points_count=info['points_count'],
                    status=info['status'],
                    vector_size=info['vector_size']
                ))

        logger.info(f"Listed {len(result)} collections")
        return result

    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list collections: {str(e)}"
        )


@app.post(
    "/search",
    summary="Semantic Search",
    description="Perform semantic search across biomedical literature",
    response_model=SearchResponse
)
async def search(request: SearchRequest):
    """
    Semantic search endpoint

    Performs semantic search across specified collections and returns
    ranked results based on relevance.

    ### Features:
    - **Multi-collection search**: Search PubMed and Clinical Trials simultaneously
    - **Semantic matching**: Uses S-BioBERT for biomedical domain understanding
    - **Metadata filtering**: Filter results by specific metadata fields
    - **Result merging**: Intelligently merge and rank cross-collection results

    ### Examples:

    Search PubMed only:
    ```json
    {
        "query": "CRISPR gene editing",
        "collections": ["pubmed_abstracts"],
        "limit": 10
    }
    ```

    Search all collections:
    ```json
    {
        "query": "Alzheimer disease treatment",
        "collections": ["pubmed_abstracts", "clinical_trials"],
        "limit": 5
    }
    ```

    Search with filters:
    ```json
    {
        "query": "cancer immunotherapy",
        "collections": ["pubmed_abstracts"],
        "limit": 10,
        "filters": {"source": "pubmed"}
    }
    ```
    """
    start_time = time.time()

    try:
        logger.info(f"Search request: query='{request.query}', collections={request.collections}, limit={request.limit}")

        # Validate collections exist
        available_collections = search_engine.get_all_collections()
        invalid_collections = [c for c in request.collections if c not in available_collections]
        if invalid_collections:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid collections: {invalid_collections}. Available: {available_collections}"
            )

        # Perform search
        results = search_engine.search_multi_collection(
            query=request.query,
            collections=request.collections,
            limit=request.limit,
            filters=request.filters
        )

        # Merge results if requested
        if request.merge_results:
            merged_results = search_engine.merge_and_rank_results(results)
        else:
            # Keep results separated by collection
            merged_results = []
            for collection, collection_results in results.items():
                merged_results.extend(collection_results)

        # Calculate statistics
        results_per_collection = {
            collection: len(collection_results)
            for collection, collection_results in results.items()
        }

        search_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Search completed: {len(merged_results)} total results in {search_time_ms:.2f}ms"
        )

        return SearchResponse(
            query=request.query,
            total_results=len(merged_results),
            results_per_collection=results_per_collection,
            results=[SearchResultItem(**r) for r in merged_results],
            search_time_ms=round(search_time_ms, 2)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@app.post(
    "/ask",
    summary="AI-Powered Q&A",
    description="Ask questions and get AI-generated answers with citations from biomedical literature",
    response_model=AskResponse
)
async def ask_question(request: AskRequest):
    """
    RAG-powered question answering endpoint

    Ask natural language questions and receive comprehensive answers with proper
    citations from PubMed abstracts and clinical trials.

    ### Features:
    - **Semantic Retrieval**: Uses S-BioBERT to find relevant sources
    - **AI Answer Generation**: Claude/GPT-4 generates comprehensive answers
    - **Citation Validation**: Ensures all claims are properly cited
    - **Quality Metrics**: Returns performance and validation metrics

    ### How it works:
    1. Your question is embedded using S-BioBERT
    2. Top-k most relevant papers/trials are retrieved
    3. Context is sent to LLM to generate answer
    4. Citations are validated and metrics calculated
    5. Answer with sources is returned

    ### Examples:

    Basic question:
    ```json
    {
        "question": "What is CRISPR gene editing?",
        "top_k": 5
    }
    ```

    Specific collection:
    ```json
    {
        "question": "Latest Alzheimer's treatments?",
        "collections": ["clinical_trials"],
        "top_k": 10
    }
    ```

    Adjust creativity:
    ```json
    {
        "question": "Explain immunotherapy for cancer",
        "temperature": 0.3,
        "max_tokens": 1500
    }
    ```

    ### Response:
    Returns:
    - **answer**: AI-generated answer with inline citations (e.g., "PMID:12345...")
    - **sources**: List of source documents with URLs
    - **metrics**: Performance timing and cost estimates
    - **validation**: Citation coverage and quality metrics
    """

    # Check if RAG is enabled
    if rag_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG engine not initialized. Please configure LLM provider in config."
        )

    try:
        logger.info(
            f"RAG request: question='{request.question[:100]}...', "
            f"collections={request.collections}, top_k={request.top_k}"
        )

        # Call RAG engine
        result = await rag_engine.ask(
            question=request.question,
            collections=request.collections,
            top_k=request.top_k,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            filters=request.filters
        )

        logger.info(
            f"RAG completed: {result['metrics']['total_time_ms']:.0f}ms, "
            f"cost: ${result['metrics']['estimated_cost_usd']:.4f}"
        )

        # Convert to response model
        return AskResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG failed: {str(e)}"
        )


# Development server entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
