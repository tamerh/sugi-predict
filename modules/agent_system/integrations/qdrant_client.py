"""Qdrant vector database client for agent system."""

from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from ..core.config import QdrantConfig


# Embedding model used for text collections (PubMed, Patents, Clinical Trials)
TEXT_EMBEDDING_MODEL = "pritamdeka/S-BioBERT-snli-multinli-stsb"
TEXT_EMBEDDING_DIM = 768


class BioYodaQdrantClient:
    """
    Client for BioYoda's Qdrant vector database.

    Provides access to:
    - ESM-2 protein embeddings (573K+ proteins)
    - Chemical compound fingerprints (30M+ compounds)
    - PubMed abstracts (when available)
    - Clinical trials (when available)
    """

    def __init__(self, config: QdrantConfig):
        """
        Initialize Qdrant client.

        Args:
            config: Qdrant configuration (host, port, etc.)
        """
        self.config = config
        self._client: Optional[QdrantClient] = None
        self._text_encoder = None  # Lazy-loaded sentence transformer

    @property
    def client(self) -> QdrantClient:
        """Lazy-initialize and return Qdrant client."""
        if self._client is None:
            self._client = QdrantClient(
                host=self.config.host,
                port=self.config.port,
                timeout=self.config.timeout
            )
        return self._client

    def close(self):
        """Close the Qdrant connection."""
        if self._client is not None:
            self._client.close()
            self._client = None

    async def get_collections(self) -> List[Dict[str, Any]]:
        """
        Get list of available collections with their stats.

        Returns:
            List of collection info dicts
        """
        collections = self.client.get_collections()
        result = []

        for col in collections.collections:
            info = self.client.get_collection(col.name)
            result.append({
                "name": col.name,
                "points_count": info.points_count,
                "vectors_count": info.indexed_vectors_count,
                "status": info.status.value,
                "vector_size": info.config.params.vectors.size,
                "distance": info.config.params.vectors.distance.value
            })

        return result

    async def get_protein_vector(self, protein_id: str) -> Optional[List[float]]:
        """
        Get ESM-2 embedding vector for a protein.

        Args:
            protein_id: UniProt accession (e.g., "P04637")

        Returns:
            1280-dim embedding vector or None if not found
        """
        results = self.client.scroll(
            collection_name="esm2",
            scroll_filter=Filter(
                must=[FieldCondition(key="protein_id", match=MatchValue(value=protein_id))]
            ),
            limit=1,
            with_vectors=True
        )

        if results[0]:
            return results[0][0].vector
        return None

    async def search_similar_proteins(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search for similar proteins by ESM-2 embedding.

        Args:
            query_vector: 1280-dim ESM-2 embedding
            limit: Maximum number of results
            score_threshold: Minimum similarity score

        Returns:
            List of similar proteins with scores
        """
        results = self.client.query_points(
            collection_name="esm2",
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "protein_id": hit.payload.get("protein_id"),
                "score": hit.score,
                "id": hit.id
            }
            for hit in results.points
        ]

    async def search_proteins_by_id(
        self,
        protein_id: str,
        limit: int = 10,
        include_self: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Find proteins similar to a given protein ID.

        Args:
            protein_id: UniProt accession to search from
            limit: Maximum number of results
            include_self: Whether to include the query protein in results

        Returns:
            List of similar proteins with scores
        """
        # Get the query vector
        vector = await self.get_protein_vector(protein_id)
        if vector is None:
            return []

        # Search for similar
        actual_limit = limit + 1 if not include_self else limit
        results = await self.search_similar_proteins(vector, limit=actual_limit)

        # Filter out self if needed
        if not include_self:
            results = [r for r in results if r["protein_id"] != protein_id][:limit]

        return results

    async def get_compound_vector(self, surechembl_id: str) -> Optional[List[float]]:
        """
        Get Morgan fingerprint vector for a compound.

        Args:
            surechembl_id: SureChEMBL compound ID

        Returns:
            2048-dim fingerprint vector or None if not found
        """
        results = self.client.scroll(
            collection_name="patents_compounds",
            scroll_filter=Filter(
                must=[FieldCondition(key="surechembl_id", match=MatchValue(value=surechembl_id))]
            ),
            limit=1,
            with_vectors=True
        )

        if results[0]:
            return results[0][0].vector
        return None

    async def search_similar_compounds(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search for similar compounds by Morgan fingerprint.

        Args:
            query_vector: 2048-dim Morgan fingerprint
            limit: Maximum number of results
            score_threshold: Minimum similarity score

        Returns:
            List of similar compounds with SMILES and scores
        """
        results = self.client.query_points(
            collection_name="patents_compounds",
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "surechembl_id": hit.payload.get("surechembl_id"),
                "smiles": hit.payload.get("smiles"),
                "molecular_weight": hit.payload.get("molecular_weight"),
                "formula": hit.payload.get("formula"),
                "inchi": hit.payload.get("inchi"),
                "score": hit.score,
                "id": hit.id
            }
            for hit in results.points
        ]

    async def search_compounds_by_id(
        self,
        surechembl_id: str,
        limit: int = 10,
        include_self: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Find compounds similar to a given compound ID.

        Args:
            surechembl_id: SureChEMBL ID to search from
            limit: Maximum number of results
            include_self: Whether to include the query compound in results

        Returns:
            List of similar compounds with SMILES and scores
        """
        # Get the query vector
        vector = await self.get_compound_vector(surechembl_id)
        if vector is None:
            return []

        # Search for similar
        actual_limit = limit + 1 if not include_self else limit
        results = await self.search_similar_compounds(vector, limit=actual_limit)

        # Filter out self if needed
        if not include_self:
            results = [r for r in results if r["surechembl_id"] != surechembl_id][:limit]

        return results


    @property
    def text_encoder(self):
        """
        Lazy-load the text embedding model.

        Uses the same BioBERT model used to create PubMed/Patents embeddings.
        First call will download and load the model (~400MB).
        """
        if self._text_encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._text_encoder = SentenceTransformer(TEXT_EMBEDDING_MODEL)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for text search. "
                    "Install with: pip install sentence-transformers"
                )
        return self._text_encoder

    def encode_text(self, text: str) -> List[float]:
        """
        Encode text to embedding vector using BioBERT model.

        Args:
            text: Text to encode (query, abstract, etc.)

        Returns:
            768-dim embedding vector
        """
        vector = self.text_encoder.encode(text, convert_to_numpy=True)
        return vector.tolist()

    async def search_pubmed(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over PubMed abstracts.

        Uses BioBERT embeddings to find papers relevant to the query.

        Args:
            query: Search query (e.g., "EGFR inhibitor resistance glioblastoma")
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)

        Returns:
            List of matching papers with pmid, text snippet, and score

        Example:
            >>> papers = await client.search_pubmed("EGFR resistance mechanisms", limit=5)
            >>> for paper in papers:
            ...     print(f"PMID: {paper['pmid']}, Score: {paper['score']:.2f}")
        """
        # Encode query to vector
        query_vector = self.encode_text(query)

        # Search Qdrant
        results = self.client.query_points(
            collection_name="pubmed_abstracts",
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "pmid": hit.payload.get("pmid"),
                "text": hit.payload.get("chunk_text", "")[:500],  # First 500 chars
                "full_text": hit.payload.get("chunk_text", ""),
                "score": hit.score,
                "source": "pubmed"
            }
            for hit in results.points
        ]

    async def search_pubmed_for_entity(
        self,
        entity: str,
        disease: str,
        entity_type: str = "gene",
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search PubMed for papers about a specific gene/drug in disease context.

        Args:
            entity: Gene symbol or drug name
            disease: Disease context
            entity_type: "gene" or "drug"
            limit: Maximum papers to return

        Returns:
            List of relevant papers
        """
        if entity_type == "gene":
            query = f"{entity} {disease} gene target mechanism therapeutic"
        else:
            query = f"{entity} {disease} drug treatment efficacy clinical"

        return await self.search_pubmed(query, limit=limit)

    async def search_patents_text(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over patent text.

        Args:
            query: Search query
            limit: Maximum number of results
            score_threshold: Minimum similarity score

        Returns:
            List of matching patents with metadata
        """
        query_vector = self.encode_text(query)

        results = self.client.query_points(
            collection_name="patents_text",
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "patent_id": hit.payload.get("patent_id"),
                "title": hit.payload.get("title", ""),
                "pub_date": hit.payload.get("pub_date"),
                "assignees": hit.payload.get("assignees", []),
                "score": hit.score,
                "source": "patents"
            }
            for hit in results.points
        ]

    async def search_clinical_trials(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over clinical trials.

        Args:
            query: Search query (e.g., "EGFR inhibitor glioblastoma phase 3")
            limit: Maximum number of results
            score_threshold: Minimum similarity score

        Returns:
            List of matching trials with metadata
        """
        query_vector = self.encode_text(query)

        results = self.client.query_points(
            collection_name="clinical_trials",
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "nct_id": hit.payload.get("nct_id"),
                "title": hit.payload.get("brief_title", ""),
                "phase": hit.payload.get("phase"),
                "status": hit.payload.get("overall_status"),
                "conditions": hit.payload.get("conditions", []),
                "interventions": hit.payload.get("interventions", []),
                "sponsors": hit.payload.get("sponsors", []),
                "study_type": hit.payload.get("study_type"),
                "score": hit.score,
                "source": "clinical_trials"
            }
            for hit in results.points
        ]

    async def enrich_entities_with_literature(
        self,
        entities: List[Dict[str, Any]],
        disease: str,
        entity_type: str = "gene",
        papers_per_entity: int = 3
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Enrich a list of entities with relevant literature.

        Args:
            entities: List of entities (must have 'id' or 'symbol' field)
            disease: Disease context for search
            entity_type: "gene" or "drug"
            papers_per_entity: Number of papers to fetch per entity

        Returns:
            Dict mapping entity ID to list of papers

        Example:
            >>> genes = [{"symbol": "EGFR"}, {"symbol": "TP53"}]
            >>> literature = await client.enrich_entities_with_literature(
            ...     genes, "glioblastoma", entity_type="gene"
            ... )
            >>> print(literature["EGFR"])  # Papers about EGFR in glioblastoma
        """
        literature_by_entity = {}

        for entity in entities:
            entity_id = entity.get("symbol", entity.get("id", entity.get("name", "")))
            if not entity_id:
                continue

            papers = await self.search_pubmed_for_entity(
                entity=entity_id,
                disease=disease,
                entity_type=entity_type,
                limit=papers_per_entity
            )

            if papers:
                literature_by_entity[entity_id] = papers

        return literature_by_entity


def create_qdrant_client(config: QdrantConfig) -> BioYodaQdrantClient:
    """
    Create and return a Qdrant client instance.

    Args:
        config: Qdrant configuration

    Returns:
        Configured Qdrant client
    """
    return BioYodaQdrantClient(config)
