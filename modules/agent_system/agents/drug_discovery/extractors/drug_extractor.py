"""Drug Extraction from BioBTree Results.

Extract drugs from:
- Direct indication query results
- Gene-to-drug query results
"""

from typing import List, Dict, Any
import re

from ..utils.drug_names import get_best_drug_name


# Common medical term synonyms for matching
TERM_SYNONYMS = {
    "cancer": ["carcinoma", "tumor", "tumour", "neoplasm", "malignancy"],
    "carcinoma": ["cancer", "tumor", "tumour", "neoplasm", "malignancy"],
    "disease": ["disorder", "syndrome"],
    "disorder": ["disease", "syndrome"],
}


def normalize_disease_terms(text: str) -> str:
    """Normalize disease terms for better matching."""
    text = text.lower()
    # Replace common synonyms
    text = text.replace("carcinoma", "cancer")
    text = text.replace("tumour", "tumor")
    text = text.replace("neoplasm", "cancer")
    text = text.replace("malignancy", "cancer")
    return text


def disease_matches(disease: str, indication: str) -> bool:
    """
    Check if disease name matches indication with synonym support.

    Args:
        disease: User's disease search term
        indication: EFO indication name

    Returns:
        True if they match (considering synonyms)
    """
    disease_norm = normalize_disease_terms(disease)
    indication_norm = normalize_disease_terms(indication)

    # Direct substring match after normalization
    if disease_norm in indication_norm or indication_norm in disease_norm:
        return True

    # Word overlap matching (at least 2 significant words must match)
    disease_words = set(re.findall(r'\b[a-z]{3,}\b', disease_norm))
    indication_words = set(re.findall(r'\b[a-z]{3,}\b', indication_norm))

    # Remove common words
    common_words = {'cell', 'type', 'stage', 'grade', 'the', 'and', 'with'}
    disease_words -= common_words
    indication_words -= common_words

    overlap = disease_words & indication_words
    if len(overlap) >= 2:
        return True

    return False


class DrugExtractor:
    """Extract drugs from BioBTree query results."""

    def extract_from_indication_results(
        self,
        result: Dict,
        disease: str,
        min_phase: int
    ) -> List[Dict]:
        """
        Extract and filter drugs from direct indication query results.

        Filters by indication-specific phase, not drug-level phase.

        Args:
            result: BioBTree query result
            disease: Disease name for matching indications
            min_phase: Minimum indication phase to include

        Returns:
            List of drug dicts with indication-specific info
        """
        drugs = []
        seen_ids = set()

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            for target in r.get("targets", []):
                drug_id = target.get("identifier", "")
                if drug_id in seen_ids:
                    continue

                # Get ChEMBL molecule data
                chembl_data = target.get("chembl", {})
                if not chembl_data:
                    attrs = target.get("Attributes", {})
                    chembl_data = attrs.get("Chembl", {}) or attrs.get("chembl", {})

                drug_info = chembl_data.get("molecule", {})
                if not drug_info:
                    continue

                # Get drug name (prefer common names over IUPAC)
                alt_names = drug_info.get("altNames", [])
                drug_name = get_best_drug_name(alt_names, fallback=drug_id)

                # Get indications and find disease-specific phase
                indications = drug_info.get("indications", [])
                indication_phase = None
                indication_name = None

                for ind in indications:
                    ind_name = ind.get("efoName", "")
                    ind_phase = ind.get("highestDevelopmentPhase")

                    # Check if this indication matches the disease (with synonym support)
                    if disease_matches(disease, ind_name):
                        indication_phase = ind_phase
                        indication_name = ind_name
                        break

                # Filter by indication-specific phase
                if indication_phase is None or indication_phase < min_phase:
                    continue

                # Get mechanism
                mechanism = drug_info.get("mechanism", {})
                mechanism_desc = ""
                if mechanism:
                    mechanism_desc = mechanism.get("desc", "") or mechanism.get("action", "")

                drugs.append({
                    "id": drug_id,
                    "name": drug_name or drug_id,
                    "alt_names": alt_names,  # Store all names for trial matching
                    "indication_phase": indication_phase,
                    "indication_name": indication_name,
                    "drug_phase": drug_info.get("highestDevelopmentPhase"),
                    "mechanism": mechanism_desc,
                    "type": drug_info.get("type", ""),
                    "smiles": drug_info.get("smiles"),  # For compound similarity
                    "inchi_key": drug_info.get("inchiKey"),  # For patent matching
                    "evidence": "direct_indication"
                })
                seen_ids.add(drug_id)

        # Sort by indication phase (highest first)
        drugs.sort(key=lambda d: -(d.get("indication_phase") or 0))

        return drugs

    def extract_from_gene_results(
        self,
        result: Dict,
        evidence_type: str = "gene_association"
    ) -> Dict[str, List[Dict]]:
        """
        Extract drugs grouped by target gene from gene-to-drug query results.

        Args:
            result: BioBTree query result from genes >> ... >> chembl_molecule
            evidence_type: Type of evidence (gwas, clinvar, reactome, uniprot)

        Returns:
            Dict mapping gene symbols to their drug lists
        """
        drugs_by_gene = {}

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            # Get gene symbol from source (this is the gene we queried)
            source = r.get("source", {})
            gene_symbol = source.get("keyword") or source.get("identifier", "Unknown")

            # Clean up gene symbol (remove ENSG prefix if present)
            if gene_symbol.startswith("ENSG"):
                # Try to get from attributes
                ensembl_data = source.get("ensembl", {})
                if not ensembl_data:
                    attrs = source.get("Attributes", {})
                    ensembl_data = attrs.get("Ensembl", {}) or attrs.get("ensembl", {})
                if ensembl_data:
                    gene_symbol = ensembl_data.get("symbol") or gene_symbol

            for target in r.get("targets", []):
                drug_id = target.get("identifier", "")

                # Get ChEMBL molecule data
                chembl_data = target.get("chembl", {})
                if not chembl_data:
                    attrs = target.get("Attributes", {})
                    chembl_data = attrs.get("Chembl", {}) or attrs.get("chembl", {})

                drug_info = chembl_data.get("molecule", {})

                # Get drug name (prefer common names over IUPAC)
                drug_name = None
                if drug_info:
                    alt_names = drug_info.get("altNames", [])
                    drug_name = get_best_drug_name(alt_names, fallback=drug_id)

                drug_phase = drug_info.get("highestDevelopmentPhase") if drug_info else None

                # Get mechanism
                mechanism = ""
                if drug_info:
                    mech = drug_info.get("mechanism", {})
                    if mech:
                        mechanism = mech.get("desc", "") or mech.get("action", "")

                drug_entry = {
                    "id": drug_id,
                    "name": drug_name or drug_id,
                    "drug_phase": drug_phase,
                    "mechanism": mechanism,
                    "evidence": evidence_type
                }

                if gene_symbol not in drugs_by_gene:
                    drugs_by_gene[gene_symbol] = []

                # Avoid duplicates within same gene
                if drug_id not in [d["id"] for d in drugs_by_gene[gene_symbol]]:
                    drugs_by_gene[gene_symbol].append(drug_entry)

        # Sort drugs within each gene by phase (highest first)
        for gene in drugs_by_gene:
            drugs_by_gene[gene].sort(
                key=lambda d: -(d.get("drug_phase") or 0)
            )

        return drugs_by_gene
