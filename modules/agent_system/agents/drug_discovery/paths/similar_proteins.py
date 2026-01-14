"""PATH 8: Similar Proteins via ESM-2 Embeddings.

Find proteins structurally similar to disease-associated targets.
This helps identify:
- Homologous drug targets
- Off-target effects (similar proteins may bind same drugs)
- Drug repurposing opportunities

Use case: Given EGFR as disease target, find similar kinases that might
respond to same inhibitors.
"""

from typing import Dict, Any, List
from collections import defaultdict

from .base import BasePath, PathResult


class SimilarProteinsPath(BasePath):
    """
    PATH 8: Find proteins similar to disease-associated targets.

    Uses: Qdrant ESM-2 embeddings (573K proteins, 1280-dim)

    Input: Gene symbols from GWAS/ClinVar/GenCC paths
    Output: Similar proteins with UniProt IDs and similarity scores

    The ESM-2 model captures structural and functional similarity,
    so similar proteins often share druggability profiles.
    """

    @property
    def name(self) -> str:
        return "similar_proteins"

    @property
    def description(self) -> str:
        return "Find structurally similar proteins using ESM-2 embeddings"

    @property
    def requires_qdrant(self) -> bool:
        return True

    async def execute(
        self,
        disease: str,
        genes: List[str] = None,
        uniprot_ids: List[str] = None,
        top_k: int = 5,
        min_score: float = 0.8,
        **kwargs
    ) -> PathResult:
        """
        Find proteins similar to disease-associated targets.

        Args:
            disease: Disease name (for context)
            genes: List of gene symbols to find similar proteins for
            uniprot_ids: Alternative: provide UniProt IDs directly
            top_k: Number of similar proteins per query
            min_score: Minimum similarity score (0-1, cosine similarity)

        Returns:
            PathResult with similar proteins grouped by query
        """
        if not self.qdrant:
            return self._create_result(
                success=False,
                error="Qdrant client not available",
                metadata={"error": "Qdrant required for protein similarity search"}
            )

        # Get UniProt IDs from genes if not provided directly
        protein_ids = uniprot_ids or []
        gene_to_uniprot = {}

        if genes and not uniprot_ids:
            # Map genes to UniProt IDs via BioBTree
            try:
                mapfilter = ">>ensembl[ensembl.genome==\"homo_sapiens\"]>>uniprot[uniprot.reviewed==true]"
                result = await self.biobtree.map_query_all_pages(
                    terms=genes[:20],  # Limit to avoid timeout
                    mapfilter=mapfilter,
                    mode="full",
                    preserve_sources=True
                )

                results_container = result.get("results", {})
                if isinstance(results_container, dict):
                    results = results_container.get("results", [])
                else:
                    results = results_container

                for r in results:
                    source_gene = r.get("source", {}).get("keyword", "")
                    for target in r.get("targets", []):
                        uniprot_id = target.get("identifier", "")
                        if uniprot_id and uniprot_id.startswith(("P", "Q", "O", "A", "B", "C")):
                            protein_ids.append(uniprot_id)
                            gene_to_uniprot[source_gene] = uniprot_id
                            break  # One per gene

            except Exception as e:
                return self._create_result(
                    success=False,
                    error=f"Failed to map genes to UniProt: {e}",
                    metadata={"genes": genes}
                )

        if not protein_ids:
            return self._create_result(
                success=True,
                data={
                    "similar_proteins": {},
                    "protein_count": 0,
                    "message": "No proteins to search"
                },
                metadata={"query": "No valid UniProt IDs found"}
            )

        # Search for similar proteins
        similar_by_query = {}
        all_similar_proteins = set()
        errors = []

        for protein_id in protein_ids[:10]:  # Limit to 10 proteins
            try:
                similar = await self.qdrant.search_proteins_by_id(
                    protein_id=protein_id,
                    limit=top_k,
                    include_self=False
                )

                if similar:
                    # Filter by score threshold
                    filtered = [p for p in similar if p.get("score", 0) >= min_score]

                    if filtered:
                        similar_by_query[protein_id] = filtered
                        for p in filtered:
                            all_similar_proteins.add(p.get("protein_id"))

            except Exception as e:
                errors.append(f"{protein_id}: {str(e)}")

        # Enrich similar proteins with gene names via BioBTree
        protein_info = {}
        if all_similar_proteins:
            try:
                mapfilter = ">>uniprot>>ensembl"
                result = await self.biobtree.map_query_all_pages(
                    terms=list(all_similar_proteins)[:30],
                    mapfilter=mapfilter,
                    mode="full"
                )

                results_container = result.get("results", {})
                if isinstance(results_container, dict):
                    results = results_container.get("results", [])
                else:
                    results = results_container

                for r in results:
                    source = r.get("source", {})
                    uniprot_id = source.get("keyword", "") or source.get("identifier", "")

                    # Get gene symbol from target
                    for target in r.get("targets", []):
                        ensembl_data = target.get("ensembl", {})
                        if not ensembl_data:
                            ensembl_data = target.get("Attributes", {}).get("Ensembl", {})

                        gene_symbol = ensembl_data.get("symbol", "")
                        gene_desc = ensembl_data.get("description", "")

                        if gene_symbol:
                            protein_info[uniprot_id] = {
                                "gene_symbol": gene_symbol,
                                "description": gene_desc
                            }
                            break

            except Exception:
                pass  # Enrichment failure is non-critical

        # Build enriched results
        enriched_results = {}
        for query_protein, similar_list in similar_by_query.items():
            enriched = []
            for p in similar_list:
                pid = p.get("protein_id")
                info = protein_info.get(pid, {})
                enriched.append({
                    "uniprot_id": pid,
                    "gene_symbol": info.get("gene_symbol", ""),
                    "description": info.get("description", ""),
                    "similarity_score": round(p.get("score", 0), 4),
                    "url": f"https://www.uniprot.org/uniprotkb/{pid}"
                })
            enriched_results[query_protein] = enriched

        # Summary statistics
        total_similar = sum(len(v) for v in enriched_results.values())
        unique_similar = len(all_similar_proteins)

        return self._create_result(
            success=True,
            data={
                "similar_proteins": enriched_results,
                "gene_to_uniprot": gene_to_uniprot,
                "protein_count": len(enriched_results),
                "total_similar_found": total_similar,
                "unique_similar_proteins": unique_similar,
            },
            genes=[p.get("gene_symbol") for proteins in enriched_results.values()
                   for p in proteins if p.get("gene_symbol")],
            metadata={
                "query": "ESM-2 protein similarity search",
                "proteins_queried": len(protein_ids),
                "proteins_with_matches": len(enriched_results),
                "top_k": top_k,
                "min_score": min_score,
                "errors": errors if errors else None
            }
        )
