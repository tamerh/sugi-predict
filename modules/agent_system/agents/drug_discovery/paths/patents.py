"""PATH 12: Patent Discovery.

Query patents linked to drugs via BioBTree direct mapping.
Uses: chembl_molecule >> patent_compound >> patent
"""

from typing import Dict, Any, List

from .base import BasePath, PathResult


class PatentsPath(BasePath):
    """
    PATH 12: Query patents linked to drugs via BioBTree.

    Uses direct gRPC mapping chain:
        chembl_molecule >> patent_compound >> patent

    Returns patent details including title, country, publication date,
    and Google Patents URL.
    """

    @property
    def name(self) -> str:
        return "patents"

    @property
    def description(self) -> str:
        return "Patents linked to drugs (SureChEMBL via BioBTree)"

    async def execute(
        self,
        disease: str,
        drugs: List[Dict] = None,
        max_molecules: int = 20,
        **kwargs
    ) -> PathResult:
        """
        Execute patent query via BioBTree mapping.

        Args:
            disease: Disease name (for metadata)
            drugs: List of drug dicts with 'id' (ChEMBL ID)
            max_molecules: Maximum molecules to process

        Returns:
            PathResult with patents linked to drugs
        """
        if not drugs:
            return self._create_result(
                success=True,
                data={"patents": [], "by_molecule": {}},
                metadata={
                    "query": "chembl_molecule >> patent_compound >> patent",
                    "note": "No drugs provided"
                }
            )

        try:
            # Extract ChEMBL IDs from drugs
            chembl_ids = []
            id_to_drug = {}
            for mol in drugs[:max_molecules]:
                mol_id = mol.get("id", "")
                if mol_id and mol_id.startswith("CHEMBL"):
                    chembl_ids.append(mol_id)
                    id_to_drug[mol_id] = mol

            if not chembl_ids:
                return self._create_result(
                    success=True,
                    data={"patents": [], "by_molecule": {}},
                    metadata={
                        "query": "chembl_molecule >> patent_compound >> patent",
                        "note": "No valid ChEMBL IDs found"
                    }
                )

            # Query BioBTree with all ChEMBL IDs at once (preserve source mapping)
            result = await self.biobtree.map_query_all_pages(
                terms=chembl_ids,
                mapfilter=">>chembl_molecule>>patent_compound>>patent",
                mode="full",
                preserve_sources=True
            )

            # Process results
            patents_by_molecule = {}
            all_patents = []
            seen_patent_ids = set()

            results_list = result.get("results", {}).get("results", [])

            for r in results_list:
                source = r.get("source", {})
                mol_id = source.get("identifier", "")
                targets = r.get("targets", [])

                if not targets:
                    continue

                mol_patents = []
                drug_info = id_to_drug.get(mol_id, {})
                mol_name = drug_info.get("name", mol_id)

                for target in targets:
                    patent_id = target.get("identifier", "")
                    if not patent_id or patent_id in seen_patent_ids:
                        continue

                    # Extract patent details
                    patent_data = target.get("patent", {})
                    patent_entry = {
                        "patent_id": patent_id,
                        "title": patent_data.get("title", ""),
                        "country": patent_data.get("country", ""),
                        "publication_date": patent_data.get("publication_date", ""),
                        "family_id": patent_data.get("family_id", ""),
                        "url": target.get("url", f"https://patents.google.com/patent/{patent_id}"),
                        "source_chembl_id": mol_id
                    }

                    mol_patents.append(patent_entry)
                    all_patents.append(patent_entry)
                    seen_patent_ids.add(patent_id)

                if mol_patents:
                    patents_by_molecule[mol_id] = {
                        "molecule_name": mol_name,
                        "chembl_id": mol_id,
                        "patents": mol_patents,
                        "patent_count": len(mol_patents)
                    }

            # Group patents by country
            country_counts = {}
            for patent in all_patents:
                country = patent.get("country", "UNKNOWN")
                country_counts[country] = country_counts.get(country, 0) + 1

            return self._create_result(
                success=True,
                data={
                    "patents": all_patents,
                    "count": len(all_patents),
                    "by_country": country_counts,
                    "by_molecule": patents_by_molecule,
                    "molecules_with_patents": len(patents_by_molecule),
                    "molecules_queried": len(chembl_ids),
                    "note": f"Patents linked to {disease} drugs via BioBTree"
                },
                metadata={
                    "query": "chembl_molecule >> patent_compound >> patent",
                    "molecules_queried": len(chembl_ids),
                    "patent_count": len(all_patents),
                    "molecules_with_patents": len(patents_by_molecule),
                    "timing_ms": result.get("_client_timing_ms", 0)
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "chembl_molecule >> patent_compound >> patent"}
            )
