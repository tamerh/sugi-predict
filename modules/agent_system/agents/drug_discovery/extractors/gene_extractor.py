"""Gene Extraction from BioBTree Results.

Extract genes from:
- GWAS association results
- ClinVar variant results
- Reactome pathway results
"""

from typing import List, Dict, Any


class GeneExtractor:
    """Extract genes from BioBTree query results."""

    def extract_genes(self, result: Dict, max_genes: int = 50) -> List[str]:
        """
        Extract unique gene symbols from query results (GWAS, ClinVar, Reactome).

        Args:
            result: BioBTree query result with ensembl targets
            max_genes: Maximum number of genes to return

        Returns:
            List of unique gene symbols
        """
        genes = set()

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            for target in r.get("targets", []):
                # Get gene symbol from ensembl data
                ensembl_data = target.get("ensembl", {})
                if not ensembl_data:
                    attrs = target.get("Attributes", {})
                    ensembl_data = attrs.get("Ensembl", {}) or attrs.get("ensembl", {})

                # Try to get gene symbol
                gene_symbol = None
                if ensembl_data:
                    gene_symbol = ensembl_data.get("symbol") or ensembl_data.get("name")

                # Fallback to identifier
                if not gene_symbol:
                    identifier = target.get("identifier", "")
                    # If it looks like a gene symbol (short, uppercase)
                    if identifier and len(identifier) < 15 and not identifier.startswith("ENSG"):
                        gene_symbol = identifier

                if gene_symbol:
                    genes.add(gene_symbol)

        # Sort for consistent results across runs
        return sorted(list(genes))[:max_genes]

    def extract_proteins(self, result: Dict, max_proteins: int = 50) -> List[Dict]:
        """
        Extract unique proteins from UniProt query results.

        Args:
            result: BioBTree query result with UniProt targets
            max_proteins: Maximum number of proteins to return

        Returns:
            List of dicts with protein info (accession, gene_name)
        """
        proteins = {}  # Use dict to track by accession

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            for target in r.get("targets", []):
                accession = target.get("identifier", "")
                if not accession or accession in proteins:
                    continue

                # Get UniProt data for gene name
                uniprot_data = target.get("uniprot", {})
                if not uniprot_data:
                    attrs = target.get("Attributes", {})
                    uniprot_data = attrs.get("Uniprot", {}) or attrs.get("uniprot", {})

                gene_name = None
                if uniprot_data:
                    gene_name = uniprot_data.get("geneName") or uniprot_data.get("gene_name")

                proteins[accession] = {
                    "accession": accession,
                    "gene_name": gene_name
                }

                if len(proteins) >= max_proteins:
                    break

        # Sort by accession for consistent results
        return sorted(proteins.values(), key=lambda p: p["accession"])
