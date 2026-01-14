"""PATH 16: Bgee Tissue Expression.

Enrich genes with tissue-specific expression data from Bgee.
This helps prioritize drug targets by understanding where they are expressed.

Use case: Identify if disease-associated genes are expressed in relevant tissues
and find tissues where off-target effects might occur.
"""

from typing import Dict, Any, List

from .base import BasePath, PathResult


class BgeeExpressionPath(BasePath):
    """
    PATH 16: Enrich genes with Bgee tissue expression data.

    Uses: genes >> ensembl >> bgee

    Provides:
    - Tissue/cell type expression levels
    - Expression scores and ranks
    - Quality indicators (gold/silver)
    - Present/absent calls
    """

    @property
    def name(self) -> str:
        return "bgee_expression"

    @property
    def description(self) -> str:
        return "Tissue-specific expression data for disease-associated genes (Bgee)"

    async def execute(
        self,
        disease: str,
        genes: List[str] = None,
        top_tissues: int = 10,
        min_expression_score: float = 70.0,
        **kwargs
    ) -> PathResult:
        """
        Enrich genes with Bgee expression data.

        Args:
            disease: Disease name (for context)
            genes: List of gene symbols to query (from GWAS/ClinVar/GenCC)
            top_tissues: Number of top tissues to return per gene (default: 10)
            min_expression_score: Minimum expression score to include (default: 70.0)

        Returns:
            PathResult with tissue expression data for each gene
        """
        if not genes:
            return self._create_result(
                success=True,
                data={
                    "genes_with_expression": {},
                    "tissue_summary": {},
                    "gene_count": 0
                },
                metadata={
                    "query": "No genes provided",
                    "gene_count": 0
                }
            )

        try:
            # Query Bgee via ensembl
            mapfilter = ">>ensembl[ensembl.genome==\"homo_sapiens\"]>>bgee"
            bgee_result = await self.biobtree.map_query_all_pages(
                terms=genes[:50],  # Limit to avoid timeout
                mapfilter=mapfilter,
                mode="full",
                preserve_sources=True
            )

            # Extract expression data
            genes_with_expression = {}
            tissue_summary = {}  # Track which tissues genes are expressed in

            # Process results
            results = bgee_result.get("results", {}).get("results", [])
            for result in results:
                source_gene = result.get("source", {}).get("keyword", "")
                targets = result.get("targets", [])

                if not source_gene or not targets:
                    continue

                for target in targets:
                    bgee = target.get("Attributes", {}).get("Bgee", {})
                    if not bgee:
                        bgee = target.get("bgee", {})

                    if not bgee:
                        continue

                    gene_name = bgee.get("gene_name", source_gene)
                    conditions = bgee.get("expression_conditions", [])

                    if not conditions:
                        continue

                    # Filter and sort by expression score
                    expressed_tissues = []
                    for cond in conditions:
                        if cond.get("expression") == "present":
                            score = cond.get("expression_score", 0)
                            if score >= min_expression_score:
                                tissue = cond.get("anatomical_entity_name", "")
                                expressed_tissues.append({
                                    "tissue": tissue,
                                    "tissue_id": cond.get("anatomical_entity_id", ""),
                                    "expression_score": score,
                                    "expression_rank": cond.get("expression_rank", 0),
                                    "quality": cond.get("call_quality", ""),
                                })
                                # Track tissue summary
                                if tissue not in tissue_summary:
                                    tissue_summary[tissue] = []
                                tissue_summary[tissue].append(gene_name)

                    # Sort by expression score (highest first)
                    expressed_tissues.sort(key=lambda x: x["expression_score"], reverse=True)

                    if expressed_tissues:
                        genes_with_expression[gene_name] = {
                            "gene_symbol": gene_name,
                            "ensembl_id": bgee.get("gene_id", ""),
                            "species": bgee.get("species", ""),
                            "top_tissues": expressed_tissues[:top_tissues],
                            "total_tissues_expressed": len(expressed_tissues),
                            "highest_expression_score": expressed_tissues[0]["expression_score"] if expressed_tissues else 0,
                            "highest_expression_tissue": expressed_tissues[0]["tissue"] if expressed_tissues else "",
                        }

            # Sort tissue summary by number of genes
            tissue_summary_sorted = dict(
                sorted(
                    tissue_summary.items(),
                    key=lambda x: len(x[1]),
                    reverse=True
                )
            )

            # Create summary of top tissues across all genes
            top_shared_tissues = []
            for tissue, tissue_genes in list(tissue_summary_sorted.items())[:20]:
                top_shared_tissues.append({
                    "tissue": tissue,
                    "gene_count": len(tissue_genes),
                    "genes": tissue_genes[:10]  # Limit genes shown
                })

            return self._create_result(
                success=True,
                data={
                    "genes_with_expression": genes_with_expression,
                    "top_shared_tissues": top_shared_tissues,
                    "gene_count": len(genes_with_expression),
                    "genes_queried": len(genes),
                },
                genes=list(genes_with_expression.keys()),
                metadata={
                    "query": f"genes >> ensembl >> bgee",
                    "gene_count": len(genes_with_expression),
                    "genes_queried": len(genes),
                    "min_expression_score": min_expression_score,
                    "top_tissues_per_gene": top_tissues
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "genes >> ensembl >> bgee"}
            )
