"""PATH 20: InterPro Protein Domains.

Enrich genes with protein domain data from InterPro.
This helps assess druggability by identifying functional domains.

Use case: Identify which disease-associated proteins have druggable domains
(kinase domains, GPCRs, ion channels, etc.).
"""

from typing import Dict, Any, List
from collections import defaultdict

from .base import BasePath, PathResult


# Druggable domain types
DRUGGABLE_DOMAINS = {
    "kinase": ["kinase", "protein kinase", "tyrosine kinase", "serine/threonine kinase"],
    "gpcr": ["gpcr", "g-protein coupled receptor", "7tm", "rhodopsin"],
    "ion_channel": ["ion channel", "voltage-gated", "ligand-gated", "potassium channel", "sodium channel", "calcium channel"],
    "protease": ["protease", "peptidase", "cathepsin", "caspase"],
    "phosphatase": ["phosphatase", "protein phosphatase"],
    "nuclear_receptor": ["nuclear receptor", "hormone receptor", "steroid receptor"],
    "enzyme": ["enzyme", "oxidoreductase", "transferase", "hydrolase"],
}


class InterProPath(BasePath):
    """
    PATH 20: Enrich genes with InterPro domain data.

    Uses: genes >> ensembl >> uniprot >> interpro

    Provides:
    - Protein domain annotations
    - Druggable domain classification
    - Family and superfamily information
    """

    @property
    def name(self) -> str:
        return "interpro"

    @property
    def description(self) -> str:
        return "Protein domain analysis for disease-associated genes (InterPro)"

    def _classify_druggability(self, domain_name: str, domain_type: str) -> List[str]:
        """Classify domain into druggable categories."""
        categories = []
        name_lower = domain_name.lower()
        type_lower = domain_type.lower() if domain_type else ""
        combined = f"{name_lower} {type_lower}"

        for category, keywords in DRUGGABLE_DOMAINS.items():
            if any(kw in combined for kw in keywords):
                categories.append(category)

        return categories

    async def execute(
        self,
        disease: str,
        genes: List[str] = None,
        **kwargs
    ) -> PathResult:
        """
        Enrich genes with InterPro domain data.

        Args:
            disease: Disease name (for context)
            genes: List of gene symbols to query (from GWAS/ClinVar/GenCC)

        Returns:
            PathResult with domain data for each gene
        """
        if not genes:
            return self._create_result(
                success=True,
                data={
                    "genes_with_domains": {},
                    "druggability_summary": {},
                    "gene_count": 0
                },
                metadata={
                    "query": "No genes provided",
                    "gene_count": 0
                }
            )

        try:
            # Query InterPro via UniProt
            mapfilter = ">>ensembl[ensembl.genome==\"homo_sapiens\"]>>uniprot[uniprot.reviewed==true]>>interpro"
            interpro_result = await self.biobtree.map_query_all_pages(
                terms=genes[:30],  # Limit to avoid timeout
                mapfilter=mapfilter,
                mode="full",
                preserve_sources=True
            )

            genes_with_domains = {}
            druggable_counts = defaultdict(int)
            domain_type_counts = defaultdict(int)

            # Process results
            results_container = interpro_result.get("results", {})
            if isinstance(results_container, dict):
                results = results_container.get("results", [])
            else:
                results = results_container

            for result in results:
                source_gene = result.get("source", {}).get("keyword", "")
                targets = result.get("targets", [])

                if not source_gene or not targets:
                    continue

                domains = []
                gene_druggable_categories = set()

                for target in targets:
                    interpro_id = target.get("identifier", "")

                    # InterPro data can be in different locations
                    interpro_data = target.get("interpro", {})
                    if not interpro_data:
                        interpro_data = target.get("Attributes", {}).get("Interpro", {})

                    if not interpro_id:
                        continue

                    # InterPro uses 'names' (list) instead of 'name'
                    names = interpro_data.get("names", [])
                    domain_name = names[0] if names else interpro_data.get("short_name", target.get("name", ""))
                    domain_type = interpro_data.get("type", "")
                    parent_id = interpro_data.get("parent", "")

                    # Classify druggability
                    categories = self._classify_druggability(domain_name, domain_type)
                    gene_druggable_categories.update(categories)

                    domains.append({
                        "interpro_id": interpro_id,
                        "name": domain_name,
                        "type": domain_type,
                        "parent": parent_id,
                        "druggable_categories": categories,
                        "url": target.get("url", f"https://www.ebi.ac.uk/interpro/entry/InterPro/{interpro_id}/"),
                    })

                    if domain_type:
                        domain_type_counts[domain_type] += 1
                    for cat in categories:
                        druggable_counts[cat] += 1

                if domains:
                    genes_with_domains[source_gene] = {
                        "gene_symbol": source_gene,
                        "domains": domains,
                        "domain_count": len(domains),
                        "druggable_categories": list(gene_druggable_categories),
                        "is_druggable": len(gene_druggable_categories) > 0,
                    }

            # Druggability summary
            druggability_summary = {
                "by_category": dict(druggable_counts),
                "by_domain_type": dict(domain_type_counts),
                "total_domains": sum(g["domain_count"] for g in genes_with_domains.values()),
                "genes_with_druggable_domains": sum(1 for g in genes_with_domains.values() if g["is_druggable"]),
                "kinase_genes": [g for g, data in genes_with_domains.items() if "kinase" in data["druggable_categories"]],
                "gpcr_genes": [g for g, data in genes_with_domains.items() if "gpcr" in data["druggable_categories"]],
                "ion_channel_genes": [g for g, data in genes_with_domains.items() if "ion_channel" in data["druggable_categories"]],
            }

            return self._create_result(
                success=True,
                data={
                    "genes_with_domains": genes_with_domains,
                    "druggability_summary": druggability_summary,
                    "gene_count": len(genes_with_domains),
                    "genes_queried": len(genes),
                },
                genes=list(genes_with_domains.keys()),
                metadata={
                    "query": "genes >> ensembl >> uniprot >> interpro",
                    "gene_count": len(genes_with_domains),
                    "genes_queried": len(genes),
                    "genes_with_druggable_domains": druggability_summary["genes_with_druggable_domains"],
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "genes >> ensembl >> uniprot >> interpro"}
            )
