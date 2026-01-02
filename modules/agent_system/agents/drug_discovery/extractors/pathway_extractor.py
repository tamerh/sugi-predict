"""Reactome Pathway Extraction from BioBTree Results.

Extract biological pathways from Reactome data via BioBTree.
"""

from typing import List, Dict, Any


class PathwayExtractor:
    """Extract Reactome pathways from BioBTree query results."""

    def extract_pathways(self, result: Dict) -> Dict[str, List[Dict]]:
        """
        Extract Reactome pathways grouped by gene.

        Args:
            result: BioBTree query result from genes >> ensembl >> reactome

        Returns:
            Dict mapping gene symbols to their pathway lists
        """
        pathways_by_gene = {}

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            # Get gene symbol from source
            source = r.get("source", {})
            gene_symbol = source.get("keyword") or source.get("identifier", "Unknown")

            # Clean up gene symbol
            if gene_symbol.startswith("ENSG"):
                ensembl_data = source.get("ensembl", {})
                if not ensembl_data:
                    attrs = source.get("Attributes", {})
                    ensembl_data = attrs.get("Ensembl", {}) or attrs.get("ensembl", {})
                if ensembl_data:
                    gene_symbol = ensembl_data.get("symbol") or gene_symbol

            for target in r.get("targets", []):
                pathway_id = target.get("identifier", "")

                # Get Reactome data
                reactome_data = target.get("reactome", {})
                if not reactome_data:
                    attrs = target.get("Attributes", {})
                    reactome_data = attrs.get("Reactome", {}) or attrs.get("reactome", {})

                pathway_name = reactome_data.get("name", "") if reactome_data else ""
                is_disease = reactome_data.get("is_disease_pathway", False) if reactome_data else False

                pathway_entry = {
                    "id": pathway_id,
                    "name": pathway_name,
                    "is_disease_pathway": is_disease
                }

                if gene_symbol not in pathways_by_gene:
                    pathways_by_gene[gene_symbol] = []

                # Avoid duplicates
                if pathway_id not in [p["id"] for p in pathways_by_gene[gene_symbol]]:
                    pathways_by_gene[gene_symbol].append(pathway_entry)

        # Sort pathways by name
        for gene in pathways_by_gene:
            pathways_by_gene[gene].sort(key=lambda p: p.get("name", "").lower())

        return pathways_by_gene
