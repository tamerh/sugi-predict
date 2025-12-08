"""BioBTree query tool for agent system."""

from typing import Optional, List, Dict, Any

from .base import Tool, ToolResult
from ..llm.base import ToolDefinition
from ..integrations.biobtree_client import BioBTreeClient
from ..core.config import BioBTreeConfig


class BioBTreeQueryTool(Tool):
    """Tool for querying BioBTree database with chain syntax."""

    def __init__(self, client: BioBTreeClient):
        """
        Initialize BioBTree query tool.

        Args:
            client: BioBTree client instance (shared, persistent connection)
        """
        super().__init__(
            name="biobtree_query",
            description=(
                "Map biological identifiers across 40+ databases using BioBTree. "
                "Use for: ID mapping, finding relationships, getting authoritative IDs. "
                "Syntax: 'identifier >> source_dataset >> target_dataset'. "
                "Examples: "
                "'EGFR >> ensembl >> uniprot' (gene to protein), "
                "'P04637 >> uniprot >> ensembl' (protein to gene), "
                "'EGFR >> ensembl >> uniprot >> chembl_target >> chembl_molecule' (gene to drugs), "
                "'BRCA1,TP53 >> ensembl >> uniprot' (multiple genes). "
                "Key datasets: ensembl, uniprot, chembl_target, chembl_molecule (drugs), reactome, go, dbsnp, drugbank."
            )
        )
        self.client = client

    def _build_filtered_mapfilter(
        self,
        datasets: list,
        species: Optional[str] = None,
        canonical_only: bool = False
    ) -> str:
        """
        Build BioBTree mapfilter with native filtering.

        Args:
            datasets: List of dataset names from chain query
            species: Species genome filter (e.g., "homo_sapiens")
            canonical_only: If True, add reviewed filter for uniprot

        Returns:
            Filtered mapfilter string

        Example:
            datasets=["ensembl", "uniprot"], species="homo_sapiens", canonical_only=True
            Returns: ">>ensembl[ensembl.genome==\"homo_sapiens\"]>>uniprot[uniprot.reviewed==true]"
        """
        filtered_parts = []

        for dataset in datasets:
            dataset = dataset.strip()

            # Add species filter to ensembl
            if dataset == "ensembl" and species:
                dataset = f'ensembl[ensembl.genome=="{species}"]'

            # Add canonical filter to uniprot
            elif dataset == "uniprot" and canonical_only:
                dataset = "uniprot[uniprot.reviewed==true]"

            filtered_parts.append(dataset)

        return ">>" + ">>".join(filtered_parts)

    def _parse_lite_response(self, result: Dict) -> Dict[str, Any]:
        """
        Parse lite mode response into a simplified format.

        Args:
            result: Raw response from BioBTree with results_lite

        Returns:
            Parsed response with mappings, stats, pagination
        """
        lite = result.get('results_lite', {})

        # Get original query terms to match with mappings
        query_info = lite.get('query', {})
        original_terms = query_info.get('terms', [])

        mappings = []
        for i, m in enumerate(lite.get('mappings', [])):
            # Get original term if available (by index matching)
            original_term = original_terms[i] if i < len(original_terms) else None

            mapping = {
                'term': original_term,  # Original query term (e.g., "EGFR")
                'input': m.get('input', ''),  # Resolved ID (e.g., "ENSG00000146648")
                'source': None,
                'targets': [],
                'error': m.get('error')
            }

            if m.get('source'):
                mapping['source'] = {
                    'dataset': m['source'].get('d', ''),
                    'id': m['source'].get('id', ''),
                    'has_attr': m['source'].get('has_attr', False)
                }

            for t in m.get('targets', []):
                mapping['targets'].append({
                    'dataset': t.get('d', ''),
                    'id': t.get('id', ''),
                    'has_attr': t.get('has_attr', False)
                })

            mappings.append(mapping)

        return {
            'mode': 'lite',
            'mappings': mappings,
            'stats': lite.get('stats', {}),
            'pagination': lite.get('pagination', {}),
            'query': lite.get('query', {})
        }

    def get_definition(self) -> ToolDefinition:
        """Get tool definition for LLM function calling."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "chain_query": {
                        "type": "string",
                        "description": (
                            "BioBTree chain query syntax: 'term >> dataset >> dataset'. "
                            "For MULTIPLE terms, use comma-separated: 'term1,term2 >> dataset'. "
                            "Common datasets: ensembl (genes), uniprot (proteins), "
                            "chembl_target (drug targets), chembl_compound (drugs), "
                            "dbsnp (variants), reactome (pathways), go (gene ontology). "
                            "Examples: 'BRCA1,TP53,EGFR >> ensembl >> uniprot'"
                        )
                    },
                    "species": {
                        "type": "string",
                        "description": (
                            "Filter by species/genome. Common values: 'homo_sapiens' (human, default), "
                            "'mus_musculus' (mouse), 'rattus_norvegicus' (rat), 'danio_rerio' (zebrafish). "
                            "Set to null to include all species."
                        )
                    },
                    "canonical_only": {
                        "type": "boolean",
                        "description": (
                            "If true (default), return only canonical/reviewed proteins from UniProt. "
                            "This filters out isoforms and fragments. Set to false to get all variants."
                        )
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["lite", "full"],
                        "description": (
                            "Response mode: 'lite' (default) returns compact IDs optimized for agents, "
                            "'full' returns complete metadata including sequences and attributes."
                        )
                    }
                },
                "required": ["chain_query"]
            }
        )

    async def execute(
        self,
        chain_query: str,
        species: Optional[str] = "homo_sapiens",
        canonical_only: bool = True,
        mode: str = "lite",
        **kwargs
    ) -> ToolResult:
        """
        Execute BioBTree query with optional native filtering.

        Args:
            chain_query: BioBTree chain query (e.g., "EGFR >> ensembl >> uniprot")
            species: Filter by genome (e.g., "homo_sapiens"). None for all species.
            canonical_only: If True, filter for reviewed/canonical proteins only
            mode: Response mode - "lite" (default, compact IDs) or "full" (all attributes)
            **kwargs: Additional parameters

        Returns:
            Tool result with BioBTree response
        """
        try:
            # Parse query to extract terms and mapfilter
            # Format: "term >> dataset >> dataset" or "term1,term2 >> dataset"
            parts = [p.strip() for p in chain_query.split(">>")]

            if len(parts) < 2:
                return ToolResult(
                    success=False,
                    data=None,
                    error="Invalid query format. Use 'term >> dataset' or 'term >> dataset >> dataset'"
                )

            # First part is the search term(s) - split by comma if multiple
            term_string = parts[0]
            if ',' in term_string:
                # Multiple terms: "TP53,BRCA1" -> ["TP53", "BRCA1"]
                terms = [t.strip() for t in term_string.split(',')]
            else:
                # Single term
                terms = [term_string]

            # Build mapping chain with native BioBTree filters
            mapfilter = self._build_filtered_mapfilter(
                parts[1:],
                species=species,
                canonical_only=canonical_only
            )

            # Execute query on shared connection (client will auto-connect)
            result = await self.client.map_query(
                terms=terms,
                mapfilter=mapfilter,
                mode=mode
            )

            # Handle response based on mode
            if mode == "lite":
                # Parse lite mode response
                parsed = self._parse_lite_response(result)
                stats = parsed.get('stats', {})

                return ToolResult(
                    success=True,
                    data=parsed,
                    metadata={
                        "terms": terms,
                        "mapfilter": mapfilter,
                        "species_filter": species,
                        "canonical_only": canonical_only,
                        "mode": mode,
                        "total_terms": stats.get('total_terms', len(terms)),
                        "mapped": stats.get('mapped', 0),
                        "failed": stats.get('failed', 0),
                        "total_targets": stats.get('total_targets', 0),
                        "summary": (
                            f"Mapped {stats.get('mapped', 0)}/{stats.get('total_terms', len(terms))} terms "
                            f"to {stats.get('total_targets', 0)} target(s)"
                        )
                    }
                )
            else:
                # Full mode - return raw result with full attributes
                full_result = result.get('results', {})
                results_list = full_result.get('results', [])
                stats = full_result.get('stats', {})

                total_sources = len(results_list)
                total_targets = sum(
                    len(r.get('targets', []))
                    for r in results_list
                )

                return ToolResult(
                    success=True,
                    data=result,
                    metadata={
                        "terms": terms,
                        "mapfilter": mapfilter,
                        "species_filter": species,
                        "canonical_only": canonical_only,
                        "mode": mode,
                        "total_sources": total_sources,
                        "total_targets": total_targets,
                        "summary": (
                            f"Found {total_targets} target(s) from {total_sources} source(s) "
                            f"with full attributes"
                        )
                    }
                )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"BioBTree query error: {str(e)}"
            )


class BioBTreeSearchTool(Tool):
    """Tool for searching BioBTree datasets."""

    def __init__(self, client: BioBTreeClient):
        """
        Initialize BioBTree search tool.

        Args:
            client: BioBTree client instance (shared, persistent connection)
        """
        super().__init__(
            name="biobtree_search",
            description=(
                "Search for identifiers across BioBTree datasets. "
                "Use this to find which datasets contain a specific term."
            )
        )
        self.client = client

    def get_definition(self) -> ToolDefinition:
        """Get tool definition for LLM function calling."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "Search term (gene symbol, protein ID, etc.)"
                    },
                    "dataset": {
                        "type": "string",
                        "description": "Optional: Specific dataset to search in (e.g., 'hgnc', 'uniprot')"
                    },
                    "detail": {
                        "type": "boolean",
                        "description": "Return detailed results"
                    }
                },
                "required": ["term"]
            }
        )

    async def execute(
        self,
        term: str,
        dataset: Optional[str] = None,
        detail: bool = False,
        **kwargs
    ) -> ToolResult:
        """
        Execute BioBTree search.

        Args:
            term: Search term
            dataset: Optional dataset filter
            detail: Return detailed results
            **kwargs: Additional parameters

        Returns:
            Tool result with search results
        """
        try:
            # Execute search on shared connection (client will auto-connect)
            result = await self.client.search(
                terms=[term],
                dataset=dataset,
                detail=detail
            )

            return ToolResult(
                success=True,
                data=result,
                metadata={
                    "term": term,
                    "dataset": dataset,
                    "detail": detail
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"BioBTree search error: {str(e)}"
            )
