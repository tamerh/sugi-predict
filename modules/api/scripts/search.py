"""
Search engine implementation for BioYoda

Handles semantic search across Qdrant vector database collections.
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Optional, Any
import logging
import time

logger = logging.getLogger(__name__)


class BioYodaSearchEngine:
    """
    Semantic search engine for biomedical literature

    This class handles:
    - Query encoding with biomedical sentence transformers (supports multiple models)
    - Single and multi-collection search
    - Result merging and ranking
    - Metadata filtering

    Each collection can use a different embedding model. The search engine will
    automatically use the correct model when encoding queries for each collection.
    """

    def __init__(self, qdrant_url: str, collection_models: Optional[Dict[str, str]] = None,
                 model_name: Optional[str] = None, timeout: int = 180):
        """
        Initialize search engine

        Args:
            qdrant_url: Qdrant server URL
            collection_models: Dict mapping collection names to model names (preferred)
            model_name: Single model name for backward compatibility (deprecated)
            timeout: Qdrant client timeout in seconds
        """
        logger.info("Initializing BioYoda Search Engine...")
        logger.info(f"Qdrant URL: {qdrant_url}")

        try:
            # Initialize Qdrant client
            self.client = QdrantClient(url=qdrant_url, timeout=timeout)

            # Test connection
            collections = self.client.get_collections()
            logger.info(f"Connected to Qdrant. Available collections: {len(collections.collections)}")

            # Handle collection-specific models or fallback to single model
            if collection_models:
                self.collection_models = collection_models
                logger.info("Collection-model mappings:")
                for collection, model in collection_models.items():
                    logger.info(f"  - {collection}: {model}")
            elif model_name:
                # Backward compatibility: use single model for all collections
                logger.warning(f"Using single model for all collections: {model_name}")
                self.collection_models = {c.name: model_name for c in collections.collections}
            else:
                raise ValueError("Either collection_models or model_name must be provided")

            # Load all unique models
            unique_models = set(self.collection_models.values())
            self.models = {}  # model_name -> SentenceTransformer instance

            for model_name in unique_models:
                logger.info(f"Loading embedding model: {model_name}")
                self.models[model_name] = SentenceTransformer(model_name)
                logger.info(f"  ✓ {model_name} loaded successfully")

            # Legacy single model reference (for backward compatibility)
            self.model = list(self.models.values())[0] if self.models else None
            self.model_name = list(self.models.keys())[0] if self.models else None

            self.qdrant_url = qdrant_url

        except Exception as e:
            logger.error(f"Failed to initialize search engine: {e}")
            raise

    def get_model_for_collection(self, collection: str) -> SentenceTransformer:
        """
        Get the correct embedding model for a collection

        Args:
            collection: Collection name

        Returns:
            SentenceTransformer model instance

        Raises:
            ValueError: If collection has no associated model
        """
        model_name = self.collection_models.get(collection)
        if not model_name:
            # Fallback to first available model
            logger.warning(f"No model found for collection '{collection}', using default")
            model_name = list(self.models.keys())[0]

        model = self.models.get(model_name)
        if not model:
            raise ValueError(f"Model '{model_name}' not loaded for collection '{collection}'")

        return model

    def encode_query(self, query: str, collection: Optional[str] = None) -> List[float]:
        """
        Encode query text into vector embedding using the correct model

        Args:
            query: Query text
            collection: Collection name (to select correct model). If None, uses default model.

        Returns:
            Vector embedding as list of floats
        """
        start_time = time.time()

        # Select the correct model for this collection
        if collection:
            model = self.get_model_for_collection(collection)
            model_name = self.collection_models.get(collection, "unknown")
        else:
            # Fallback to default model for backward compatibility
            model = self.model
            model_name = self.model_name

        vector = model.encode([query])[0].tolist()
        encode_time = (time.time() - start_time) * 1000
        logger.debug(f"Query encoded in {encode_time:.2f}ms (model: {model_name})")
        return vector

    def get_protein_vector(self, protein_id: str, collection: str) -> Optional[List[float]]:
        """
        Get the embedding vector for a protein by its UniProt accession

        Args:
            protein_id: UniProt accession (e.g., "Q6GZX4")
            collection: Collection name (must be protein_similarity_esm2)

        Returns:
            Vector embedding as list of floats, or None if protein not found
        """
        try:
            # Search for the protein by ID using payload filter
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            results = self.client.scroll(
                collection_name=collection,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="protein_id",
                            match=MatchValue(value=protein_id)
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=True  # We need the vector for similarity search
            )

            if results[0] and len(results[0]) > 0:
                vector = results[0][0].vector
                logger.debug(f"Retrieved vector for protein {protein_id}")
                return vector
            else:
                logger.warning(f"Protein {protein_id} not found in collection {collection}")
                return None

        except Exception as e:
            logger.error(f"Error retrieving protein vector for {protein_id}: {e}")
            return None

    def search_single_collection(
        self,
        query: str,
        collection: str,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        search_ef: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search a single collection using the correct embedding model

        Args:
            query: Search query (text for text collections, UniProt accession for protein_similarity_esm2)
            collection: Collection name
            limit: Maximum number of results
            filters: Optional metadata filters
            search_ef: HNSW search parameter (higher = more accurate but slower)
                      Default: auto-scaled based on limit (4x limit)
                      For 27M+ docs: 128-256 recommended for speed, 512+ for accuracy

        Returns:
            List of search results with scores and payloads
        """
        try:
            # Special handling for protein similarity search
            if collection == "protein_similarity_esm2":
                # For proteins, query is a protein ID - look up its vector
                query_vector = self.get_protein_vector(query, collection)
                if query_vector is None:
                    logger.warning(f"Protein not found: {query}")
                    return []
            else:
                # For text collections, encode query with the correct model
                query_vector = self.encode_query(query, collection=collection)

            # Build filter if provided
            query_filter = None
            if filters:
                query_filter = self._build_filter(filters)
                logger.debug(f"Applying filters: {filters}")

            # Auto-scale ef based on limit if not provided
            # For large collections (27M+), use conservative ef for speed
            if search_ef is None:
                # Default: 4x limit, capped at 256 for very large collections
                search_ef = min(limit * 4, 256)
                logger.debug(f"Auto-scaled search_ef to {search_ef} (limit={limit})")

            # Perform search with HNSW optimization
            start_time = time.time()
            results = self.client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
                with_vectors=False,  # Don't return vectors (saves bandwidth)
                search_params={"hnsw_ef": search_ef}  # Control HNSW search accuracy
            )
            search_time = (time.time() - start_time) * 1000

            model_name = self.collection_models.get(collection, "unknown")
            logger.info(
                f"Searched '{collection}' (model: {model_name}): "
                f"{len(results)} results in {search_time:.2f}ms"
            )

            # Format results
            return [
                {
                    "id": str(result.id),
                    "score": result.score,
                    "collection": collection,
                    "payload": result.payload
                }
                for result in results
            ]

        except Exception as e:
            logger.error(f"Error searching collection '{collection}': {e}")
            # Return empty results rather than failing
            return []

    def search_multi_collection(
        self,
        query: str,
        collections: List[str],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search multiple collections in parallel

        Args:
            query: Search query
            collections: List of collection names
            limit: Maximum results per collection
            filters: Optional metadata filters

        Returns:
            Dictionary mapping collection names to their results
        """
        logger.info(f"Multi-collection search: query='{query}', collections={collections}")

        results = {}
        for collection in collections:
            results[collection] = self.search_single_collection(
                query=query,
                collection=collection,
                limit=limit,
                filters=filters
            )

        return results

    def merge_and_rank_results(
        self,
        results: Dict[str, List[Dict[str, Any]]],
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Merge results from multiple collections and re-rank by score

        Args:
            results: Dictionary of results per collection
            limit: Optional limit on total results (default: no limit)

        Returns:
            Merged and sorted list of results
        """
        # Flatten all results
        all_results = []
        for collection, collection_results in results.items():
            all_results.extend(collection_results)

        # Sort by score (descending)
        all_results.sort(key=lambda x: x['score'], reverse=True)

        # Apply limit if specified
        if limit:
            all_results = all_results[:limit]

        logger.debug(f"Merged {len(all_results)} total results from {len(results)} collections")

        return all_results

    def aggregate_chunks_by_document(
        self,
        results: List[Dict[str, Any]],
        limit: Optional[int] = None,
        scoring_strategy: str = "max"
    ) -> List[Dict[str, Any]]:
        """
        Aggregate chunks from the same document and deduplicate

        When a document is chunked (e.g., trial split into summary, eligibility, outcomes),
        this method groups all chunks by document ID and aggregates them.

        Args:
            results: List of search results (chunks)
            limit: Maximum number of documents to return
            scoring_strategy: How to score documents ("max", "avg", "sum")
                - "max": Use highest chunk score (best match wins)
                - "avg": Average of all chunk scores (balanced)
                - "sum": Sum of chunk scores (rewards multiple relevant chunks)

        Returns:
            List of aggregated document results (deduplicated)
        """
        if not results:
            return []

        # Group chunks by document ID
        documents = {}

        for result in results:
            payload = result.get('payload', {})

            # Extract document identifier
            doc_id = payload.get('nct_id') or payload.get('pmid') or result.get('id')

            if not doc_id:
                # No document ID found, treat as standalone result
                doc_id = f"unknown_{result.get('id')}"

            # Initialize document group if first time seeing this ID
            if doc_id not in documents:
                documents[doc_id] = {
                    'doc_id': doc_id,
                    'chunks': [],
                    'scores': [],
                    'collection': result.get('collection'),
                    'payload': payload.copy()  # Use first chunk's payload as base
                }

            # Add chunk to document
            documents[doc_id]['chunks'].append(result)
            documents[doc_id]['scores'].append(result.get('score', 0.0))

            # Merge important fields from additional chunks
            # Keep accumulating text/chunk_text
            if 'text' in payload or 'chunk_text' in payload:
                chunk_text = payload.get('chunk_text', payload.get('text', ''))
                if chunk_text:
                    # Accumulate text from multiple chunks
                    if 'aggregated_text' not in documents[doc_id]:
                        documents[doc_id]['aggregated_text'] = []
                    documents[doc_id]['aggregated_text'].append(chunk_text)

        # Aggregate and score each document
        aggregated_results = []

        for doc_id, doc_data in documents.items():
            chunks = doc_data['chunks']
            scores = doc_data['scores']

            # Calculate aggregate score based on strategy
            if scoring_strategy == "max":
                agg_score = max(scores)
            elif scoring_strategy == "avg":
                agg_score = sum(scores) / len(scores)
            elif scoring_strategy == "sum":
                agg_score = sum(scores)
            else:
                logger.warning(f"Unknown scoring strategy '{scoring_strategy}', using 'max'")
                agg_score = max(scores)

            # Build aggregated payload
            agg_payload = doc_data['payload'].copy()

            # Combine text from all chunks (for context)
            if 'aggregated_text' in doc_data:
                # Join all chunk texts with separator
                combined_text = ' | '.join(doc_data['aggregated_text'])
                agg_payload['chunk_text'] = combined_text[:2000]  # Limit length
                agg_payload['text'] = combined_text[:2000]
                agg_payload['num_chunks'] = len(chunks)

            # Add metadata about aggregation
            agg_payload['aggregated_from_chunks'] = len(chunks)
            agg_payload['chunk_scores'] = scores
            agg_payload['max_chunk_score'] = max(scores)
            agg_payload['avg_chunk_score'] = round(sum(scores) / len(scores), 4)

            aggregated_results.append({
                'id': doc_id,
                'score': agg_score,
                'collection': doc_data['collection'],
                'payload': agg_payload,
                'num_chunks': len(chunks)
            })

        # Sort by aggregated score
        aggregated_results.sort(key=lambda x: x['score'], reverse=True)

        # Apply limit
        if limit:
            aggregated_results = aggregated_results[:limit]

        logger.info(
            f"Aggregated {len(results)} chunks into {len(aggregated_results)} documents "
            f"(strategy={scoring_strategy})"
        )

        return aggregated_results

    def _build_filter(self, filters: Dict[str, Any]) -> Optional[Filter]:
        """
        Build Qdrant filter from dictionary

        Args:
            filters: Dictionary of field -> value mappings

        Returns:
            Qdrant Filter object or None
        """
        if not filters:
            return None

        conditions = []
        for key, value in filters.items():
            conditions.append(
                FieldCondition(
                    key=key,
                    match=MatchValue(value=value)
                )
            )

        return Filter(must=conditions) if conditions else None

    def get_collection_info(self, collection: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a collection

        Args:
            collection: Collection name

        Returns:
            Dictionary with collection info or None if error
        """
        try:
            info = self.client.get_collection(collection)
            return {
                "name": collection,
                "points_count": info.points_count,
                "status": info.status,
                "vector_size": info.config.params.vectors.size
            }
        except Exception as e:
            logger.error(f"Error getting collection info for '{collection}': {e}")
            return None

    def get_all_collections(self) -> List[str]:
        """
        Get list of all available collections

        Returns:
            List of collection names
        """
        try:
            collections = self.client.get_collections()
            return [c.name for c in collections.collections]
        except Exception as e:
            logger.error(f"Error getting collections: {e}")
            return []

    def health_check(self) -> bool:
        """
        Check if Qdrant is accessible

        Returns:
            True if Qdrant is accessible, False otherwise
        """
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return False
