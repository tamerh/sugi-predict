"""PATH 13: BindingDB Binding Data.

Query binding affinity data from BindingDB for drugs.
Path: drugs >> chembl_molecule >> bindingdb
"""

from typing import Dict, Any, List

from .base import BasePath, PathResult


class BindingDBPath(BasePath):
    """
    PATH 13: Query BindingDB binding data for drugs.

    Uses BioBTree mapping:
        chembl_molecule >> bindingdb

    Returns BindingDB IDs and URLs for drugs, which can be used
    to access detailed binding affinity data (Ki, Kd, IC50).
    """

    @property
    def name(self) -> str:
        return "bindingdb"

    @property
    def description(self) -> str:
        return "BindingDB binding data for drugs"

    async def execute(
        self,
        disease: str,
        drugs: List[Dict] = None,
        max_drugs: int = 50,
        **kwargs
    ) -> PathResult:
        """
        Execute BindingDB query for drugs.

        Args:
            disease: Disease name (for metadata)
            drugs: List of drug dicts with 'id' (ChEMBL ID)
            max_drugs: Maximum drugs to process

        Returns:
            PathResult with BindingDB data for drugs
        """
        if not drugs:
            return self._create_result(
                success=True,
                data={"drugs_with_binding_data": [], "binding_by_drug": {}},
                metadata={
                    "query": "chembl_molecule >> bindingdb",
                    "note": "No drugs provided"
                }
            )

        try:
            # Extract ChEMBL IDs
            chembl_ids = []
            id_to_drug = {}
            for drug in drugs[:max_drugs]:
                drug_id = drug.get("id", "")
                if drug_id and drug_id.startswith("CHEMBL"):
                    chembl_ids.append(drug_id)
                    id_to_drug[drug_id] = drug

            if not chembl_ids:
                return self._create_result(
                    success=True,
                    data={"drugs_with_binding_data": [], "binding_by_drug": {}},
                    metadata={
                        "query": "chembl_molecule >> bindingdb",
                        "note": "No valid ChEMBL IDs found"
                    }
                )

            # Query BioBTree
            result = await self.biobtree.map_query_all_pages(
                terms=chembl_ids,
                mapfilter=">>chembl_molecule>>bindingdb",
                mode="full",
                preserve_sources=True
            )

            # Process results
            binding_by_drug = {}
            drugs_with_data = []

            results_list = result.get("results", {}).get("results", [])

            for r in results_list:
                source = r.get("source", {})
                drug_id = source.get("identifier", "")
                targets = r.get("targets", [])

                if not targets:
                    continue

                drug_info = id_to_drug.get(drug_id, {})
                drug_name = drug_info.get("name", drug_id)

                binding_entries = []
                for target in targets:
                    bindingdb_id = target.get("identifier", "")
                    url = target.get("url", "")
                    bd_data = target.get("bindingdb", {})

                    entry = {
                        "bindingdb_id": bindingdb_id,
                        "url": url or f"https://www.bindingdb.org/bind/chemsearch/marvin/MolStructure.jsp?monession={bindingdb_id}",
                        "target": bd_data.get("target"),
                        "ki": bd_data.get("ki"),
                        "kd": bd_data.get("kd"),
                        "ic50": bd_data.get("ic50"),
                        "ec50": bd_data.get("ec50"),
                    }
                    binding_entries.append(entry)

                if binding_entries:
                    binding_by_drug[drug_id] = {
                        "drug_name": drug_name,
                        "chembl_id": drug_id,
                        "binding_entries": binding_entries,
                        "entry_count": len(binding_entries)
                    }
                    drugs_with_data.append({
                        "id": drug_id,
                        "name": drug_name,
                        "bindingdb_count": len(binding_entries)
                    })

            return self._create_result(
                success=True,
                data={
                    "drugs_with_binding_data": drugs_with_data,
                    "binding_by_drug": binding_by_drug,
                    "drugs_queried": len(chembl_ids),
                    "drugs_with_data": len(drugs_with_data),
                    "note": f"BindingDB data for {disease} drugs"
                },
                metadata={
                    "query": "chembl_molecule >> bindingdb",
                    "drugs_queried": len(chembl_ids),
                    "drugs_with_data": len(drugs_with_data),
                    "timing_ms": result.get("_client_timing_ms", 0)
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "chembl_molecule >> bindingdb"}
            )
