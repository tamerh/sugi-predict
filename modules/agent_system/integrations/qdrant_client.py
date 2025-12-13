"""Qdrant vector database client for agent system."""

from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from ..core.config import QdrantConfig


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


def create_qdrant_client(config: QdrantConfig) -> BioYodaQdrantClient:
    """
    Create and return a Qdrant client instance.

    Args:
        config: Qdrant configuration

    Returns:
        Configured Qdrant client
    """
    return BioYodaQdrantClient(config)
