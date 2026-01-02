"""PubChem Drug Extraction from BioBTree Results.

Extract FDA-approved drugs from PubChem data via BioBTree.
"""

from typing import List, Dict, Any


class PubChemExtractor:
    """Extract PubChem drugs from BioBTree query results."""

    def extract_drugs(
        self,
        result: Dict,
        evidence_type: str = "pubchem_fda"
    ) -> Dict[str, List[Dict]]:
        """
        Extract PubChem FDA-approved drugs grouped by target gene.

        Args:
            result: BioBTree query result from genes >> ... >> pubchem
            evidence_type: Type of evidence for tracking

        Returns:
            Dict mapping gene symbols to their PubChem drug lists
        """
        drugs_by_gene = {}

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
                drug_id = target.get("identifier", "")  # PubChem CID

                # Get PubChem data
                pubchem_data = target.get("pubchem", {})
                if not pubchem_data:
                    attrs = target.get("Attributes", {})
                    pubchem_data = attrs.get("Pubchem", {}) or attrs.get("pubchem", {})

                # Get drug name (title or first synonym)
                drug_name = None
                if pubchem_data:
                    drug_name = pubchem_data.get("title")
                    if not drug_name:
                        synonyms = pubchem_data.get("synonyms", [])
                        if synonyms and isinstance(synonyms, list):
                            drug_name = synonyms[0]

                # Get molecular properties
                molecular_formula = pubchem_data.get("molecular_formula", "") if pubchem_data else ""
                molecular_weight = pubchem_data.get("molecular_weight") if pubchem_data else None
                is_fda_approved = pubchem_data.get("is_fda_approved", False) if pubchem_data else False

                drug_entry = {
                    "id": f"CID:{drug_id}" if drug_id and not drug_id.startswith("CID") else drug_id,
                    "cid": drug_id,
                    "name": drug_name or drug_id,
                    "molecular_formula": molecular_formula,
                    "molecular_weight": molecular_weight,
                    "is_fda_approved": is_fda_approved,
                    "evidence": evidence_type,
                    "source": "pubchem"
                }

                if gene_symbol not in drugs_by_gene:
                    drugs_by_gene[gene_symbol] = []

                # Avoid duplicates within same gene
                if drug_id not in [d["cid"] for d in drugs_by_gene[gene_symbol]]:
                    drugs_by_gene[gene_symbol].append(drug_entry)

        # Sort drugs within each gene by name
        for gene in drugs_by_gene:
            drugs_by_gene[gene].sort(key=lambda d: d.get("name", "").lower())

        return drugs_by_gene
