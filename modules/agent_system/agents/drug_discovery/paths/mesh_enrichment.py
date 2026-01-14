"""PATH 21: MeSH Drug Classification.

Enrich drugs with MeSH pharmacological actions for mechanism of action.
Path: chembl_molecule >> pubchem >> mesh

Use case: Classify drugs by their mechanism of action and therapeutic category
for competitive landscape analysis.
"""

from typing import Dict, Any, List
from collections import defaultdict

from .base import BasePath, PathResult


class MeSHEnrichmentPath(BasePath):
    """
    PATH 21: Enrich drugs with MeSH classification data.

    Uses: drugs >> chembl_molecule >> pubchem >> mesh

    Provides:
    - Pharmacological actions (mechanism of action)
    - Therapeutic categories
    - Drug classification hierarchy
    """

    @property
    def name(self) -> str:
        return "mesh_enrichment"

    @property
    def description(self) -> str:
        return "Drug classification and mechanism of action from MeSH"

    async def execute(
        self,
        disease: str,
        drugs: List[Dict] = None,
        **kwargs
    ) -> PathResult:
        """
        Enrich drugs with MeSH classification data.

        Args:
            disease: Disease name (for context)
            drugs: List of drug dicts with 'id' (ChEMBL ID) and 'name'

        Returns:
            PathResult with MeSH classification for each drug
        """
        if not drugs:
            return self._create_result(
                success=True,
                data={
                    "drugs_with_mesh": {},
                    "mechanism_summary": {},
                    "drug_count": 0
                },
                metadata={
                    "query": "No drugs provided",
                    "drug_count": 0
                }
            )

        try:
            # Get drug names for PubChem lookup
            drug_names = []
            drug_id_to_name = {}
            for drug in drugs[:50]:  # Limit to avoid timeout
                name = drug.get("name", "").strip()
                if name:
                    drug_names.append(name)
                    drug_id_to_name[drug.get("id", "")] = name

            if not drug_names:
                return self._create_result(
                    success=True,
                    data={
                        "drugs_with_mesh": {},
                        "mechanism_summary": {},
                        "drug_count": 0
                    },
                    metadata={
                        "query": "No drug names available",
                        "drug_count": 0
                    }
                )

            # Query MeSH via PubChem
            # Drug name >> pubchem >> mesh
            mapfilter = ">>pubchem>>mesh"
            mesh_result = await self.biobtree.map_query_all_pages(
                terms=drug_names,
                mapfilter=mapfilter,
                mode="full",
                preserve_sources=True
            )

            drugs_with_mesh = {}
            mechanism_counts = defaultdict(int)
            therapeutic_counts = defaultdict(int)

            # Process results
            results_container = mesh_result.get("results", {})
            if isinstance(results_container, dict):
                results = results_container.get("results", [])
            else:
                results = results_container

            for result in results:
                source_drug = result.get("source", {}).get("keyword", "")
                targets = result.get("targets", [])

                if not source_drug or not targets:
                    continue

                mesh_terms = []
                pharmacological_actions = []
                therapeutic_categories = []

                for target in targets:
                    mesh_id = target.get("identifier", "")

                    # MeSH data can be in different locations
                    mesh_data = target.get("mesh", {})
                    if not mesh_data:
                        mesh_data = target.get("Attributes", {}).get("Mesh", {})

                    if not mesh_id:
                        continue

                    term_name = mesh_data.get("name", target.get("name", ""))
                    tree_numbers = mesh_data.get("tree_numbers", [])
                    pharm_actions = mesh_data.get("pharmacological_actions", [])

                    # Extract pharmacological actions
                    if pharm_actions:
                        for action in pharm_actions:
                            if isinstance(action, dict):
                                action_name = action.get("name", "")
                            else:
                                action_name = str(action)
                            if action_name:
                                pharmacological_actions.append(action_name)
                                mechanism_counts[action_name] += 1

                    # Determine therapeutic category from tree numbers
                    # D tree = Drugs, G = Phenomena, A = Anatomy
                    for tree_num in tree_numbers if tree_numbers else []:
                        if tree_num.startswith("D"):
                            # Drug category
                            category = self._get_drug_category(tree_num, term_name)
                            if category:
                                therapeutic_categories.append(category)
                                therapeutic_counts[category] += 1

                    mesh_terms.append({
                        "mesh_id": mesh_id,
                        "name": term_name,
                        "tree_numbers": tree_numbers,
                        "pharmacological_actions": pharm_actions,
                        "url": f"https://meshb.nlm.nih.gov/record/ui?ui={mesh_id}",
                    })

                if mesh_terms:
                    drugs_with_mesh[source_drug] = {
                        "drug_name": source_drug,
                        "mesh_terms": mesh_terms,
                        "mesh_count": len(mesh_terms),
                        "pharmacological_actions": list(set(pharmacological_actions)),
                        "therapeutic_categories": list(set(therapeutic_categories)),
                    }

            # Mechanism summary
            mechanism_summary = {
                "by_mechanism": dict(mechanism_counts),
                "by_therapeutic_category": dict(therapeutic_counts),
                "total_drugs_classified": len(drugs_with_mesh),
                "drugs_with_mechanism": sum(1 for d in drugs_with_mesh.values() if d["pharmacological_actions"]),
                "top_mechanisms": sorted(mechanism_counts.items(), key=lambda x: x[1], reverse=True)[:10],
            }

            return self._create_result(
                success=True,
                data={
                    "drugs_with_mesh": drugs_with_mesh,
                    "mechanism_summary": mechanism_summary,
                    "drug_count": len(drugs_with_mesh),
                    "drugs_queried": len(drug_names),
                },
                drugs=drugs,
                metadata={
                    "query": "drugs >> pubchem >> mesh",
                    "drug_count": len(drugs_with_mesh),
                    "drugs_queried": len(drug_names),
                    "drugs_with_mechanism": mechanism_summary["drugs_with_mechanism"],
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "drugs >> pubchem >> mesh"}
            )

    def _get_drug_category(self, tree_number: str, term_name: str) -> str:
        """Extract drug category from MeSH tree number."""
        # MeSH D tree categories
        # D01 = Inorganic Chemicals
        # D02 = Organic Chemicals
        # D03 = Heterocyclic Compounds
        # D27 = Chemical Actions and Uses
        # D27.505 = Pharmacologic Actions

        if tree_number.startswith("D27.505"):
            # This is a pharmacological action, use term name
            return term_name

        # Map top-level categories
        category_map = {
            "D01": "Inorganic Chemicals",
            "D02": "Organic Chemicals",
            "D03": "Heterocyclic Compounds",
            "D04": "Polycyclic Compounds",
            "D05": "Macromolecular Substances",
            "D06": "Hormones",
            "D08": "Enzymes and Coenzymes",
            "D09": "Carbohydrates",
            "D10": "Lipids",
            "D12": "Amino Acids and Proteins",
            "D13": "Nucleic Acids",
            "D20": "Complex Mixtures",
            "D23": "Biological Factors",
            "D26": "Pharmaceutical Preparations",
            "D27": "Chemical Actions and Uses",
        }

        # Get top-level category
        prefix = tree_number[:3]
        return category_map.get(prefix, term_name)
