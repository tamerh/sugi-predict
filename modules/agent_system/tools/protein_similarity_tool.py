"""Protein similarity search tool using ESM-2 embeddings."""

from typing import Any, Dict, List, Optional

from .base import Tool, ToolResult
from ..llm.base import ToolDefinition
from ..integrations.qdrant_client import BioYodaQdrantClient
from ..integrations.biobtree_client import BioBTreeClient


class ProteinSimilarityTool(Tool):
    """
    Tool for finding similar proteins using ESM-2 embeddings.

    Uses Qdrant vector database with 573K+ SwissProt protein embeddings
    and BioBTree for enrichment with protein annotations.

    Example queries:
    - "Find proteins similar to TP53"
    - "What proteins are similar to P04637?"
    - "Find homologs of BRCA1"
    """

    def __init__(
        self,
        qdrant_client: BioYodaQdrantClient,
        biobtree_client: BioBTreeClient
    ):
        """
        Initialize protein similarity tool.

        Args:
            qdrant_client: Qdrant client for vector search
            biobtree_client: BioBTree client for enrichment
        """
        super().__init__(
            name="protein_similarity_search",
            description="Find proteins similar to a given protein using ESM-2 embeddings. "
                        "Input a UniProt accession (e.g., P04637) or gene name (e.g., TP53) "
                        "to find structurally and functionally similar proteins."
        )
        self.qdrant = qdrant_client
        self.biobtree = biobtree_client

    def get_definition(self) -> ToolDefinition:
        """Get tool definition for LLM function calling."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Protein identifier: UniProt accession (e.g., P04637) "
                                       "or gene name (e.g., TP53, BRCA1)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of similar proteins to return (default: 10)",
                        "default": 10
                    },
                    "include_enrichment": {
                        "type": "boolean",
                        "description": "Include protein annotations from UniProt (default: true)",
                        "default": True
                    }
                },
                "required": ["query"]
            }
        )

    async def execute(
        self,
        query: str,
        limit: int = 10,
        include_enrichment: bool = True,
        **kwargs
    ) -> ToolResult:
        """
        Execute protein similarity search.

        Args:
            query: Protein identifier (UniProt accession or gene name)
            limit: Maximum number of results
            include_enrichment: Whether to include UniProt annotations

        Returns:
            ToolResult with similar proteins and their annotations
        """
        try:
            # Step 1: Resolve query to UniProt accession if needed
            protein_id = await self._resolve_protein_id(query)
            if not protein_id:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Could not find protein for query: {query}"
                )

            # Step 2: Search for similar proteins in Qdrant
            similar_proteins = await self.qdrant.search_proteins_by_id(
                protein_id=protein_id,
                limit=limit,
                include_self=False
            )

            if not similar_proteins:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Protein {protein_id} not found in ESM-2 database. "
                          f"Only SwissProt proteins (573K) are currently indexed."
                )

            # Step 3: Enrich with BioBTree annotations if requested
            if include_enrichment:
                similar_proteins = await self._enrich_proteins(similar_proteins)

            # Step 4: Get query protein info
            query_info = await self._get_protein_info(protein_id)

            return ToolResult(
                success=True,
                data={
                    "query_protein": {
                        "id": protein_id,
                        "original_query": query,
                        **query_info
                    },
                    "similar_proteins": similar_proteins,
                    "count": len(similar_proteins),
                    "method": "ESM-2 embedding similarity (1280-dim)",
                    "database": "SwissProt (573K proteins)"
                },
                metadata={
                    "tool": self.name,
                    "limit": limit,
                    "enriched": include_enrichment
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"Protein similarity search failed: {str(e)}"
            )

    async def _resolve_protein_id(self, query: str) -> Optional[str]:
        """
        Resolve a query to a UniProt accession.

        Args:
            query: Gene name or UniProt accession

        Returns:
            UniProt accession or None
        """
        # Check if already a UniProt accession (6-10 alphanumeric chars)
        query_upper = query.upper().strip()

        # Try direct lookup first (might be a UniProt ID)
        vector = await self.qdrant.get_protein_vector(query_upper)
        if vector is not None:
            return query_upper

        # Try via BioBTree: gene name -> ensembl -> uniprot
        try:
            await self.biobtree.connect()
            result = await self.biobtree.map_query(
                terms=[query],
                mapfilter=">>ensembl[ensembl.genome==\"homo_sapiens\"]>>uniprot[uniprot.reviewed==true]",
                mode="lite"
            )

            # Extract first UniProt ID from results
            lite_result = result.get('results_lite', {})
            mappings = lite_result.get('mappings', [])

            for mapping in mappings:
                targets = mapping.get('targets', [])
                for target in targets:
                    if target.get('d') == 'uniprot':
                        uniprot_id = target.get('id')
                        # Verify it's in our Qdrant database
                        vector = await self.qdrant.get_protein_vector(uniprot_id)
                        if vector is not None:
                            return uniprot_id

        except Exception:
            pass

        # Try direct uniprot search
        try:
            result = await self.biobtree.search([query], dataset="uniprot")
            results = result.get('results', [])
            for r in results:
                if isinstance(r, dict):
                    uniprot_id = r.get('identifier')
                    if uniprot_id:
                        vector = await self.qdrant.get_protein_vector(uniprot_id)
                        if vector is not None:
                            return uniprot_id
        except Exception:
            pass

        return None

    async def _enrich_proteins(
        self,
        proteins: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich protein list with UniProt annotations.

        Args:
            proteins: List of protein dicts with 'protein_id' key

        Returns:
            Enriched protein list
        """
        if not proteins:
            return proteins

        try:
            await self.biobtree.connect()

            # Get all protein IDs
            protein_ids = [p['protein_id'] for p in proteins]

            # Query BioBTree for annotations
            result = await self.biobtree.map_query(
                terms=protein_ids,
                mapfilter=">>uniprot",
                mode="full"
            )

            # Build enrichment map
            enrichment_map = {}
            inner_results = result.get('results', {}).get('results', [])

            for r in inner_results:
                source = r.get('source', {})
                protein_id = source.get('identifier')
                uniprot = source.get('uniprot', {})

                if protein_id:
                    names = uniprot.get('names', [])
                    alt_names = uniprot.get('alternative_names', [])
                    enrichment_map[protein_id] = {
                        'name': names[0] if names else None,
                        'alternative_names': alt_names[:3] if alt_names else [],
                        'reviewed': uniprot.get('reviewed', False),
                        'gene': uniprot.get('gene'),
                        'organism': uniprot.get('organism')
                    }

            # Merge enrichment into proteins
            for protein in proteins:
                pid = protein['protein_id']
                if pid in enrichment_map:
                    protein.update(enrichment_map[pid])

        except Exception:
            # Return unenriched if BioBTree fails
            pass

        return proteins

    async def _get_protein_info(self, protein_id: str) -> Dict[str, Any]:
        """
        Get info for the query protein.

        Args:
            protein_id: UniProt accession

        Returns:
            Protein info dict
        """
        try:
            await self.biobtree.connect()
            result = await self.biobtree.map_query(
                terms=[protein_id],
                mapfilter=">>uniprot",
                mode="full"
            )

            inner_results = result.get('results', {}).get('results', [])
            if inner_results:
                source = inner_results[0].get('source', {})
                uniprot = source.get('uniprot', {})
                names = uniprot.get('names', [])
                alt_names = uniprot.get('alternative_names', [])

                return {
                    'name': names[0] if names else None,
                    'alternative_names': alt_names[:3] if alt_names else [],
                    'reviewed': uniprot.get('reviewed', False),
                    'gene': uniprot.get('gene'),
                    'organism': uniprot.get('organism')
                }

        except Exception:
            pass

        return {}


def _format_protein_similarity_result(result: ToolResult) -> str:
    """
    Format protein similarity result for agent display.

    Args:
        result: ToolResult from protein similarity search

    Returns:
        Formatted string for agent
    """
    if not result.success:
        return f"Error: {result.error}"

    data = result.data
    query = data.get('query_protein', {})
    similar = data.get('similar_proteins', [])

    lines = [
        f"## Protein Similarity Search Results",
        f"",
        f"**Query Protein**: {query.get('id')} ({query.get('name', 'Unknown')})",
    ]

    if query.get('gene'):
        lines.append(f"**Gene**: {query.get('gene')}")
    if query.get('organism'):
        lines.append(f"**Organism**: {query.get('organism')}")

    lines.extend([
        f"",
        f"**Similar Proteins** ({len(similar)} found):",
        f""
    ])

    for i, protein in enumerate(similar[:10], 1):
        pid = protein.get('protein_id', 'Unknown')
        score = protein.get('score', 0)
        name = protein.get('name', '')
        gene = protein.get('gene', '')

        name_str = f" - {name}" if name else ""
        gene_str = f" [{gene}]" if gene else ""

        lines.append(f"{i}. **{pid}** (similarity: {score:.4f}){name_str}{gene_str}")

    lines.extend([
        f"",
        f"*Method: {data.get('method', 'ESM-2')}*",
        f"*Database: {data.get('database', 'SwissProt')}*"
    ])

    return "\n".join(lines)
