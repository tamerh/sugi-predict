"""BioBTree query tool for agent system.

This module provides tools for querying BioBTree database with:
- Full pagination support to get ALL results
- Modular helper methods for reuse
- Clean separation between parsing, querying, and result formatting
"""

from typing import Optional, List, Dict, Any

from .base import Tool, ToolResult
from ..llm.base import ToolDefinition
from ..integrations.biobtree_client import BioBTreeClient


# =============================================================================
# PAGINATION HELPERS
# =============================================================================

async def paginated_map_query(
    client: BioBTreeClient,
    terms: List[str],
    mapfilter: str,
    mode: str = "full",
    max_pages: int = 20,
    preserve_sources: bool = True
) -> Dict[str, Any]:
    """
    Execute a BioBTree map query with pagination to get ALL results.

    BioBTree returns paginated results (75 per page for full mode, 150 for lite).
    This helper fetches all pages and combines them.

    Args:
        client: BioBTree client instance
        terms: List of input terms to query
        mapfilter: BioBTree mapfilter string (e.g., ">>ensembl>>uniprot")
        mode: Query mode - "full" or "lite"
        max_pages: Maximum pages to fetch (safety limit, default 20)
        preserve_sources: If True, preserve source-to-target mapping per input term
                         If False, flatten all targets into single list

    Returns:
        Combined result with all targets from all pages

    Example:
        # Get all drugs for a disease (may be 150+ results across 2+ pages)
        result = await paginated_map_query(
            client, ["glioblastoma"], ">>efo>>chembl_molecule"
        )
    """
    page_token = None

    if preserve_sources:
        # Preserve source-to-target mapping (each input term keeps its own targets)
        targets_by_source = {}  # source_id -> {"source": {}, "targets": []}

        for page_num in range(max_pages):
            result = await client.map_query(
                terms=terms,
                mapfilter=mapfilter,
                mode=mode,
                page=page_token
            )

            # Extract results based on mode
            if mode == "lite":
                results_data = result.get("results_lite", {})
                results_list = results_data.get("mappings", [])

                for mapping in results_list:
                    source_id = mapping.get("input", "unknown")
                    if source_id not in targets_by_source:
                        targets_by_source[source_id] = {
                            "source": mapping.get("source", {}),
                            "targets": []
                        }
                    targets_by_source[source_id]["targets"].extend(
                        mapping.get("targets", [])
                    )

                # Check pagination
                pagination = results_data.get("pagination", {})
                if pagination.get("has_next") and pagination.get("next_token"):
                    page_token = pagination["next_token"]
                else:
                    break
            else:
                # Full mode
                results_data = result.get("results", {})
                results_list = results_data.get("results", [])

                for r in results_list:
                    source = r.get("source", {})
                    source_id = source.get("keyword") or source.get("identifier", "unknown")
                    if source_id not in targets_by_source:
                        targets_by_source[source_id] = {"source": source, "targets": []}
                    targets_by_source[source_id]["targets"].extend(r.get("targets", []))

                # Check pagination
                nextpage = results_data.get("nextpage", "")
                if nextpage and nextpage != page_token:
                    page_token = nextpage
                else:
                    break

        # Rebuild results preserving source structure
        if mode == "lite":
            combined_mappings = [
                {
                    "input": source_id,
                    "source": data["source"],
                    "targets": data["targets"]
                }
                for source_id, data in targets_by_source.items()
            ]
            return {
                "results_lite": {
                    "mappings": combined_mappings,
                    "stats": {
                        "total_terms": len(terms),
                        "mapped": len([m for m in combined_mappings if m["targets"]]),
                        "total_targets": sum(len(m["targets"]) for m in combined_mappings)
                    }
                }
            }
        else:
            combined_results = [
                {"source": data["source"], "targets": data["targets"]}
                for data in targets_by_source.values()
            ]
            return {"results": {"results": combined_results}}

    else:
        # Flatten all targets into single list (for single-term queries)
        all_targets = []

        for page_num in range(max_pages):
            result = await client.map_query(
                terms=terms,
                mapfilter=mapfilter,
                mode=mode,
                page=page_token
            )

            if mode == "lite":
                results_data = result.get("results_lite", {})
                for mapping in results_data.get("mappings", []):
                    all_targets.extend(mapping.get("targets", []))

                pagination = results_data.get("pagination", {})
                if pagination.get("has_next") and pagination.get("next_token"):
                    page_token = pagination["next_token"]
                else:
                    break
            else:
                results_data = result.get("results", {})
                for r in results_data.get("results", []):
                    all_targets.extend(r.get("targets", []))

                nextpage = results_data.get("nextpage", "")
                if nextpage and nextpage != page_token:
                    page_token = nextpage
                else:
                    break

        if mode == "lite":
            return {
                "results_lite": {
                    "mappings": [{"targets": all_targets}],
                    "stats": {"total_targets": len(all_targets)}
                }
            }
        else:
            return {"results": {"results": [{"targets": all_targets}]}}


# =============================================================================
# QUERY PARSING HELPERS
# =============================================================================

def parse_chain_query(chain_query: str) -> tuple:
    """
    Parse a BioBTree chain query into terms and datasets.

    Args:
        chain_query: Query string like "EGFR >> ensembl >> uniprot"

    Returns:
        Tuple of (terms_list, datasets_list)

    Example:
        >>> parse_chain_query("BRCA1,TP53 >> ensembl >> uniprot")
        (['BRCA1', 'TP53'], ['ensembl', 'uniprot'])
    """
    parts = [p.strip() for p in chain_query.split(">>")]

    if len(parts) < 2:
        raise ValueError("Invalid query format. Use 'term >> dataset' or 'term >> dataset >> dataset'")

    # First part is terms (comma-separated if multiple)
    term_string = parts[0]
    if ',' in term_string:
        terms = [t.strip() for t in term_string.split(',')]
    else:
        terms = [term_string]

    # Remaining parts are datasets
    datasets = parts[1:]

    return terms, datasets


def build_mapfilter(
    datasets: List[str],
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
        Mapfilter string with filters applied

    Example:
        >>> build_mapfilter(["ensembl", "uniprot"], species="homo_sapiens", canonical_only=True)
        '>>ensembl[ensembl.genome=="homo_sapiens"]>>uniprot[uniprot.reviewed==true]'
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


# =============================================================================
# RESPONSE PARSING HELPERS
# =============================================================================

def parse_lite_response(result: Dict) -> Dict[str, Any]:
    """
    Parse lite mode response into a simplified format.

    Args:
        result: Raw response from BioBTree with results_lite

    Returns:
        Parsed response with mappings, stats, pagination
    """
    lite = result.get('results_lite', {})

    query_info = lite.get('query', {})
    original_terms = query_info.get('terms', [])

    mappings = []
    for i, m in enumerate(lite.get('mappings', [])):
        original_term = original_terms[i] if i < len(original_terms) else None

        mapping = {
            'term': original_term,
            'input': m.get('input', ''),
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


def count_results(result: Dict, mode: str) -> tuple:
    """
    Count sources and targets in a result.

    Args:
        result: BioBTree result dict
        mode: "lite" or "full"

    Returns:
        Tuple of (total_sources, total_targets)
    """
    if mode == "lite":
        lite = result.get('results_lite', {})
        mappings = lite.get('mappings', [])
        total_sources = len(mappings)
        total_targets = sum(len(m.get('targets', [])) for m in mappings)
    else:
        full_result = result.get('results', {})
        results_list = full_result.get('results', [])
        total_sources = len(results_list)
        total_targets = sum(len(r.get('targets', [])) for r in results_list)

    return total_sources, total_targets


# =============================================================================
# MAIN TOOL CLASSES
# =============================================================================

class BioBTreeQueryTool(Tool):
    """
    Tool for querying BioBTree database with chain syntax.

    Features:
    - Full pagination support (fetches ALL results, not just first page)
    - Species filtering (default: homo_sapiens)
    - Canonical protein filtering (default: reviewed only)
    - Both lite (compact) and full (detailed) response modes
    """

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
        Execute BioBTree query with full pagination.

        Args:
            chain_query: BioBTree chain query (e.g., "EGFR >> ensembl >> uniprot")
            species: Filter by genome (e.g., "homo_sapiens"). None for all species.
            canonical_only: If True, filter for reviewed/canonical proteins only
            mode: Response mode - "lite" (default, compact IDs) or "full" (all attributes)
            **kwargs: Additional parameters

        Returns:
            Tool result with ALL BioBTree results (paginated automatically)
        """
        try:
            # Parse query
            terms, datasets = parse_chain_query(chain_query)

            # Build mapfilter with filters
            mapfilter = build_mapfilter(datasets, species=species, canonical_only=canonical_only)

            # Execute query with FULL PAGINATION
            result = await paginated_map_query(
                self.client,
                terms=terms,
                mapfilter=mapfilter,
                mode=mode,
                preserve_sources=True
            )

            # Format response based on mode
            if mode == "lite":
                parsed = parse_lite_response(result)
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
                # Full mode
                total_sources, total_targets = count_results(result, mode)

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

        except ValueError as e:
            return ToolResult(
                success=False,
                data=None,
                error=str(e)
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
