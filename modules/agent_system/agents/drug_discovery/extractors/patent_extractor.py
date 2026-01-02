"""Patent Extraction from BioBTree Results.

Extract patents from SureChEMBL data via BioBTree.
"""

from typing import List, Dict, Any

from ..utils.drug_names import get_best_drug_name


class PatentExtractor:
    """Extract patents from BioBTree query results."""

    def extract_patents(self, result: Dict) -> List[Dict]:
        """
        Extract patents from query results.

        Args:
            result: BioBTree query result

        Returns:
            List of patent dicts
        """
        patents = []
        seen_ids = set()

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            for target in r.get("targets", []):
                patent_id = target.get("identifier", "")
                if patent_id in seen_ids:
                    continue

                # Get patent attributes
                patent_data = target.get("patent", {})
                if not patent_data:
                    attrs = target.get("Attributes", {})
                    patent_data = attrs.get("Patent", {}) or attrs.get("patent", {})

                if not patent_data:
                    # Still add with minimal info if we have the patent ID
                    patents.append({
                        "patent_id": patent_id,
                        "title": "",
                        "country": patent_id.split("-")[0] if "-" in patent_id else "",
                        "publication_date": "",
                        "assignees": [],
                        "family_id": ""
                    })
                    seen_ids.add(patent_id)
                    continue

                # Extract assignees
                assignees = patent_data.get("asignee", []) or patent_data.get("assignee", [])
                if not isinstance(assignees, list):
                    assignees = [assignees] if assignees else []

                patent_entry = {
                    "patent_id": patent_id,
                    "title": patent_data.get("title", ""),
                    "country": patent_data.get("country", ""),
                    "publication_date": patent_data.get("publication_date", ""),
                    "assignees": assignees,
                    "family_id": patent_data.get("family_id", "")
                }

                patents.append(patent_entry)
                seen_ids.add(patent_id)

        # Sort by publication date (most recent first)
        patents.sort(key=lambda p: p.get("publication_date", "") or "", reverse=True)

        return patents

    def extract_patent_compounds(self, result: Dict) -> Dict[str, List[Dict]]:
        """
        Extract ChEMBL compounds grouped by source patent.

        Args:
            result: BioBTree query result from patents >> patent_compound >> chembl_molecule

        Returns:
            Dict mapping patent IDs to their compound lists
        """
        compounds_by_patent = {}

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            source = r.get("source", {})
            patent_id = source.get("keyword") or source.get("identifier", "Unknown")

            for target in r.get("targets", []):
                compound_id = target.get("identifier", "")

                # Get ChEMBL molecule data
                chembl_data = target.get("chembl", {})
                if not chembl_data:
                    attrs = target.get("Attributes", {})
                    chembl_data = attrs.get("Chembl", {}) or attrs.get("chembl", {})

                drug_info = chembl_data.get("molecule", {})

                # Get compound name
                compound_name = None
                if drug_info:
                    alt_names = drug_info.get("altNames", [])
                    compound_name = get_best_drug_name(alt_names, fallback=compound_id)

                compound_phase = drug_info.get("highestDevelopmentPhase") if drug_info else None

                compound_entry = {
                    "id": compound_id,
                    "name": compound_name or compound_id,
                    "drug_phase": compound_phase,
                    "type": drug_info.get("type", "") if drug_info else "",
                    "source": "patent_compound"
                }

                if patent_id not in compounds_by_patent:
                    compounds_by_patent[patent_id] = []

                # Avoid duplicates within same patent
                if compound_id not in [c["id"] for c in compounds_by_patent[patent_id]]:
                    compounds_by_patent[patent_id].append(compound_entry)

        # Sort compounds within each patent by phase (highest first)
        for patent_id in compounds_by_patent:
            compounds_by_patent[patent_id].sort(
                key=lambda c: -(c.get("drug_phase") or 0)
            )

        return compounds_by_patent
