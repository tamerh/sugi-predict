"""
BioYoda API v1 - Main Application

FastAPI application providing REST endpoints for the agent system.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from . import __version__
from .routes import (
    health_router,
    query_router,
    drug_discovery_router,
    id_mapping_router,
    protein_similarity_router,
    compound_similarity_router,
)
from .dependencies import (
    get_biobtree_client,
    get_qdrant_client,
    get_reasoning_engine,
    init_clients,
    close_clients,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Initializes:
    - BioBTree gRPC client
    - Qdrant vector database client
    - Agent system (ReasoningEngine with agents)
    """
    # Startup
    try:
        logger.info("=" * 80)
        logger.info(f"Starting BioYoda API v{__version__}")
        logger.info("=" * 80)

        # Initialize all clients and agents
        await init_clients()

        logger.info("=" * 80)
        logger.info("BioYoda API ready to serve requests")
        logger.info("API available at: http://localhost:8000")
        logger.info("Documentation at: http://localhost:8000/docs")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Failed to start API: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down BioYoda API...")
    await close_clients()


# Initialize FastAPI app
app = FastAPI(
    title="BioYoda API",
    version=__version__,
    description=(
        "AI-powered drug discovery and bioinformatics API.\n\n"
        "## Endpoints\n\n"
        "### Unified Query\n"
        "- **POST /v1/query** - Natural language queries routed to appropriate agents\n\n"
        "### Direct Agent Access\n"
        "- **POST /v1/drug-discovery** - Find drugs for diseases\n"
        "- **POST /v1/id-mapping** - Map biological identifiers\n"
        "- **POST /v1/protein-similarity** - Find similar proteins (ESM-2)\n"
        "- **POST /v1/compound-similarity** - Find similar compounds (Morgan FP)\n\n"
        "### System\n"
        "- **GET /v1/health** - Health check\n\n"
        "## Features\n"
        "- 9-path drug discovery with BioBTree (40+ databases)\n"
        "- Protein similarity search (573K SwissProt proteins)\n"
        "- Compound similarity search (30.8M patent compounds)\n"
        "- Intelligent query routing via ReasoningEngine\n"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    """Add X-Response-Time header to all responses."""
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Response-Time"] = f"{process_time:.2f}ms"
    return response


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with clear messages."""
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "ValidationError",
            "message": "Invalid request parameters",
            "details": exc.errors(),
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTPException",
            "message": exc.detail,
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "message": "An unexpected error occurred",
        }
    )


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """API root - overview of available endpoints."""
    return {
        "name": "BioYoda API",
        "version": __version__,
        "status": "running",
        "description": "AI-powered drug discovery and bioinformatics",
        "endpoints": {
            "query": "POST /v1/query - Natural language queries",
            "drug_discovery": "POST /v1/drug-discovery - Find drugs for diseases",
            "id_mapping": "POST /v1/id-mapping - Map biological identifiers",
            "protein_similarity": "POST /v1/protein-similarity - Find similar proteins",
            "compound_similarity": "POST /v1/compound-similarity - Find similar compounds",
            "health": "GET /v1/health - Health check",
            "docs": "GET /docs - Interactive API documentation",
        },
    }


# Register routers with /v1 prefix
app.include_router(health_router, prefix="/v1", tags=["Health"])
app.include_router(query_router, prefix="/v1", tags=["Query"])
app.include_router(drug_discovery_router, prefix="/v1", tags=["Drug Discovery"])
app.include_router(id_mapping_router, prefix="/v1", tags=["ID Mapping"])
app.include_router(protein_similarity_router, prefix="/v1", tags=["Similarity"])
app.include_router(compound_similarity_router, prefix="/v1", tags=["Similarity"])


# Development server entry point
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "modules.api_v1.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
