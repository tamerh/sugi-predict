"""PATH 7: Reactome Pathway Context.

Query biological pathways for disease-associated genes.
Path: genes >> ensembl >> reactome
"""

from typing import Dict, Any, List

from .base import BasePath, PathResult
from ..extractors.pathway_extractor import PathwayExtractor


class ReactomePath(BasePath):
    """
    PATH 7: Query Reactome pathways for disease-associated genes.

    Provides biological pathway context for genes identified from
    GWAS, ClinVar, and other sources.
    """

    @property
    def name(self) -> str:
        return "reactome"

    @property
    def description(self) -> str:
        return "Biological pathways from Reactome for disease-associated genes"

    async def execute(self, disease: str, genes: List[str] = None, **kwargs) -> PathResult:
        """
        Execute Reactome pathway query.

        Args:
            disease: Disease name or ID (for metadata)
            genes: List of genes to query (required)

        Returns:
            PathResult with Reactome pathways
        """
        if not genes:
            return self._create_result(
                success=True,
                data={"genes": [], "pathways_by_gene": {}},
                metadata={
                    "query": "genes >> reactome",
                    "note": "No genes provided"
                }
            )

        try:
            # Query: genes >> ensembl >> reactome (preserve_sources to track gene->pathway)
            mapfilter = (
                ">>ensembl[ensembl.genome==\"homo_sapiens\"]"
                ">>reactome"
            )
            result = await self.biobtree.map_query_all_pages(
                terms=genes,
                mapfilter=mapfilter,
                mode="full",
                preserve_sources=True  # Keep gene->pathway mapping
            )

            # Extract pathways grouped by gene (preserve_sources returns {"results": {"results": [...]}})
            extractor = PathwayExtractor()
            pathways_by_gene = extractor.extract_pathways({"data": result})

            # Count total pathways
            total_pathways = sum(len(p) for p in pathways_by_gene.values())

            return self._create_result(
                success=True,
                data={
                    "genes": list(pathways_by_gene.keys()),
                    "pathways_by_gene": pathways_by_gene,
                    "gene_count": len(pathways_by_gene),
                    "pathway_count": total_pathways,
                    "note": "Reactome pathways for disease-associated genes"
                },
                genes=list(pathways_by_gene.keys()),
                metadata={
                    "query": "genes >> ensembl >> reactome",
                    "input_genes": len(genes),
                    "gene_count": len(pathways_by_gene),
                    "pathway_count": total_pathways
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "genes >> reactome"}
            )
