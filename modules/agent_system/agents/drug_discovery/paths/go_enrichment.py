"""PATH 17: Gene Ontology Enrichment.

Enrich genes with GO annotations to understand functional context.
Groups genes by biological process, molecular function, and cellular component.

Use case: Understand what biological processes disease-associated genes are involved in,
which can inform therapeutic strategy.
"""

from typing import Dict, Any, List
from collections import defaultdict

from .base import BasePath, PathResult


class GOEnrichmentPath(BasePath):
    """
    PATH 17: Enrich genes with Gene Ontology annotations.

    Uses: genes >> ensembl >> uniprot >> go

    Provides:
    - GO terms grouped by namespace (biological_process, molecular_function, cellular_component)
    - Shared GO terms across disease-associated genes
    - Functional clustering of genes
    """

    @property
    def name(self) -> str:
        return "go_enrichment"

    @property
    def description(self) -> str:
        return "Gene Ontology functional annotations for disease-associated genes"

    async def execute(
        self,
        disease: str,
        genes: List[str] = None,
        top_terms_per_namespace: int = 10,
        **kwargs
    ) -> PathResult:
        """
        Enrich genes with GO annotations.

        Args:
            disease: Disease name (for context)
            genes: List of gene symbols to query (from GWAS/ClinVar/GenCC)
            top_terms_per_namespace: Number of top GO terms per namespace (default: 10)

        Returns:
            PathResult with GO annotations grouped by namespace
        """
        if not genes:
            return self._create_result(
                success=True,
                data={
                    "genes_with_go": {},
                    "go_by_namespace": {},
                    "shared_terms": {},
                    "gene_count": 0
                },
                metadata={
                    "query": "No genes provided",
                    "gene_count": 0
                }
            )

        try:
            # Query GO via uniprot (more comprehensive than ensembl >> go)
            # First get UniProt IDs, then GO terms
            mapfilter = ">>ensembl[ensembl.genome==\"homo_sapiens\"]>>uniprot[uniprot.reviewed==true]>>go"
            go_result = await self.biobtree.map_query_all_pages(
                terms=genes[:50],  # Limit to avoid timeout
                mapfilter=mapfilter,
                mode="full",
                preserve_sources=True
            )

            # Track GO terms by namespace
            go_by_namespace = {
                "biological_process": defaultdict(list),
                "molecular_function": defaultdict(list),
                "cellular_component": defaultdict(list),
            }
            genes_with_go = {}

            # Process results - handle preserve_sources format: results.results.results[]
            results_container = go_result.get("results", {})
            if isinstance(results_container, dict):
                results = results_container.get("results", [])
            else:
                results = results_container

            if not results:
                # Try flat format (no preserve_sources)
                targets = go_result.get("targets", [])
                if targets:
                    results = [{"source": {"keyword": genes[0]}, "targets": targets}]

            for result in results:
                source_gene = result.get("source", {}).get("keyword", "")
                targets = result.get("targets", [])

                if not source_gene or not targets:
                    continue

                gene_go_terms = {
                    "biological_process": [],
                    "molecular_function": [],
                    "cellular_component": [],
                }

                for target in targets:
                    # GO data is in "ontology" key (lowercase)
                    go = target.get("ontology", {})
                    if not go:
                        go = target.get("Attributes", {}).get("Ontology", {})

                    if not go:
                        continue

                    go_id = target.get("identifier", "")
                    go_name = go.get("name", "")
                    go_type = go.get("type", "")

                    if not go_id or not go_name or go_type not in go_by_namespace:
                        continue

                    # Track for this gene
                    gene_go_terms[go_type].append({
                        "go_id": go_id,
                        "name": go_name,
                        "synonyms": go.get("synonyms", [])[:3],  # Limit synonyms
                    })

                    # Track globally for shared term analysis
                    go_by_namespace[go_type][go_id].append({
                        "gene": source_gene,
                        "name": go_name,
                    })

                # Only include genes with GO terms
                total_terms = sum(len(v) for v in gene_go_terms.values())
                if total_terms > 0:
                    genes_with_go[source_gene] = {
                        "gene_symbol": source_gene,
                        "biological_process": gene_go_terms["biological_process"][:10],
                        "molecular_function": gene_go_terms["molecular_function"][:10],
                        "cellular_component": gene_go_terms["cellular_component"][:10],
                        "total_terms": total_terms,
                    }

            # Find shared GO terms (terms with multiple genes)
            shared_terms = {
                "biological_process": [],
                "molecular_function": [],
                "cellular_component": [],
            }

            for namespace, terms in go_by_namespace.items():
                # Sort by number of genes sharing the term
                sorted_terms = sorted(
                    terms.items(),
                    key=lambda x: len(x[1]),
                    reverse=True
                )

                for go_id, gene_list in sorted_terms[:top_terms_per_namespace]:
                    if len(gene_list) >= 2:  # Only include if shared by 2+ genes
                        shared_terms[namespace].append({
                            "go_id": go_id,
                            "name": gene_list[0]["name"],
                            "gene_count": len(gene_list),
                            "genes": [g["gene"] for g in gene_list][:10],  # Limit genes shown
                        })

            # Summary statistics
            summary = {
                "biological_process_terms": len(go_by_namespace["biological_process"]),
                "molecular_function_terms": len(go_by_namespace["molecular_function"]),
                "cellular_component_terms": len(go_by_namespace["cellular_component"]),
            }

            return self._create_result(
                success=True,
                data={
                    "genes_with_go": genes_with_go,
                    "shared_terms": shared_terms,
                    "summary": summary,
                    "gene_count": len(genes_with_go),
                    "genes_queried": len(genes),
                },
                genes=list(genes_with_go.keys()),
                metadata={
                    "query": "genes >> ensembl >> uniprot >> go",
                    "gene_count": len(genes_with_go),
                    "genes_queried": len(genes),
                    "top_terms_per_namespace": top_terms_per_namespace,
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "genes >> ensembl >> uniprot >> go"}
            )
