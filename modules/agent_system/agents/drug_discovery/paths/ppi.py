"""PATH 18: Protein-Protein Interactions (STRING/IntAct).

Enrich genes with protein interaction networks from STRING and IntAct.
This helps identify drug targets that interact with disease-associated proteins.

Use case: Find proteins that interact with disease targets - these may be
alternative drug targets or help explain mechanisms.
"""

from typing import Dict, Any, List
from collections import defaultdict

from .base import BasePath, PathResult


class PPIPath(BasePath):
    """
    PATH 18: Enrich genes with protein-protein interaction data.

    Uses: genes >> ensembl >> uniprot >> string (and/or intact)

    Provides:
    - STRING interaction partners with scores
    - IntAct curated interactions with PubMed references
    - Network analysis of disease-associated proteins
    """

    @property
    def name(self) -> str:
        return "ppi"

    @property
    def description(self) -> str:
        return "Protein-protein interaction networks for disease-associated genes"

    async def execute(
        self,
        disease: str,
        genes: List[str] = None,
        min_string_score: int = 400,  # STRING scores are 0-1000
        top_interactions: int = 10,
        **kwargs
    ) -> PathResult:
        """
        Enrich genes with PPI data from STRING.

        Args:
            disease: Disease name (for context)
            genes: List of gene symbols to query (from GWAS/ClinVar/GenCC)
            min_string_score: Minimum STRING confidence score (default: 400 = medium)
            top_interactions: Number of top interactions per gene (default: 10)

        Returns:
            PathResult with PPI data for each gene
        """
        if not genes:
            return self._create_result(
                success=True,
                data={
                    "genes_with_ppi": {},
                    "interaction_summary": {},
                    "gene_count": 0
                },
                metadata={
                    "query": "No genes provided",
                    "gene_count": 0
                }
            )

        try:
            # Query STRING via UniProt
            mapfilter = ">>ensembl[ensembl.genome==\"homo_sapiens\"]>>uniprot[uniprot.reviewed==true]>>string"
            ppi_result = await self.biobtree.map_query_all_pages(
                terms=genes[:30],  # Limit to avoid timeout
                mapfilter=mapfilter,
                mode="full",
                preserve_sources=True
            )

            genes_with_ppi = {}
            all_partners = defaultdict(int)  # Track how often each partner appears

            # Process results
            results_container = ppi_result.get("results", {})
            if isinstance(results_container, dict):
                results = results_container.get("results", [])
            else:
                results = results_container

            for result in results:
                source_gene = result.get("source", {}).get("keyword", "")
                targets = result.get("targets", [])

                if not source_gene or not targets:
                    continue

                interactions = []

                for target in targets:
                    # STRING data is in "stringattr" key (lowercase)
                    string_data = target.get("stringattr", {})
                    if not string_data:
                        string_data = target.get("Attributes", {}).get("Stringattr", {})

                    if not string_data:
                        continue

                    # Extract interactions from STRING data
                    raw_interactions = string_data.get("interactions", [])
                    for inter in raw_interactions:
                        score = inter.get("score", 0)
                        if score >= min_string_score:
                            partner = inter.get("partner", "")
                            interactions.append({
                                "partner_uniprot": partner,
                                "score": score,
                                "has_database": inter.get("has_database", False),
                            })
                            all_partners[partner] += 1

                # Sort by score and limit
                interactions.sort(key=lambda x: x["score"], reverse=True)
                interactions = interactions[:top_interactions]

                if interactions:
                    genes_with_ppi[source_gene] = {
                        "gene_symbol": source_gene,
                        "string_id": string_data.get("string_id", ""),
                        "preferred_name": string_data.get("preferred_name", ""),
                        "annotation": string_data.get("annotation", "")[:200],  # Truncate
                        "interactions": interactions,
                        "total_interactions": len(interactions),
                    }

            # Find hub proteins (partners that interact with multiple disease genes)
            hub_proteins = []
            for partner, count in sorted(all_partners.items(), key=lambda x: x[1], reverse=True)[:20]:
                if count >= 2:  # Only include if interacts with 2+ disease genes
                    hub_proteins.append({
                        "partner_uniprot": partner,
                        "disease_gene_count": count,
                    })

            return self._create_result(
                success=True,
                data={
                    "genes_with_ppi": genes_with_ppi,
                    "hub_proteins": hub_proteins,
                    "gene_count": len(genes_with_ppi),
                    "genes_queried": len(genes),
                    "total_interactions": sum(g["total_interactions"] for g in genes_with_ppi.values()),
                },
                genes=list(genes_with_ppi.keys()),
                metadata={
                    "query": "genes >> ensembl >> uniprot >> string",
                    "gene_count": len(genes_with_ppi),
                    "genes_queried": len(genes),
                    "min_string_score": min_string_score,
                    "top_interactions": top_interactions,
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "genes >> ensembl >> uniprot >> string"}
            )
