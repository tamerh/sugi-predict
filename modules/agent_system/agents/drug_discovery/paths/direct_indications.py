"""PATH 1: Direct Disease Indications.

Query drugs with direct disease indications from ChEMBL.
Path: disease >> efo >> chembl_molecule
"""

from typing import Dict, Any

from .base import BasePath, PathResult
from ..extractors.drug_extractor import DrugExtractor


class DirectIndicationsPath(BasePath):
    """
    PATH 1: Query drugs with direct disease indications.

    This is the most direct evidence path - drugs that have been specifically
    developed or approved for the queried disease.
    """

    @property
    def name(self) -> str:
        return "direct_indications"

    @property
    def description(self) -> str:
        return "Drugs with direct disease indications from ChEMBL"

    async def execute(self, disease: str, min_phase: int = 3, **kwargs) -> PathResult:
        """
        Execute direct indications query.

        Args:
            disease: Disease name or ID
            min_phase: Minimum indication phase (default: 3 = Phase 3+)

        Returns:
            PathResult with drugs that have direct indications for this disease
        """
        try:
            # Query: disease >> efo >> chembl_molecule (using client pagination)
            mapfilter = ">>efo>>chembl_molecule"
            result = await self.biobtree.map_query_all_pages(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            # Wrap flat result in expected structure for extractor
            # Client returns: {"targets": [...], "total_count": ...}
            # Extractor expects: {"data": {"results": {"results": [{"targets": [...]}]}}}
            wrapped_result = {"results": {"results": [{"targets": result.get("targets", [])}]}}

            # Extract drugs
            extractor = DrugExtractor()
            drugs = extractor.extract_from_indication_results(
                {"data": wrapped_result},
                disease,
                min_phase
            )

            return self._create_result(
                success=True,
                data=wrapped_result,
                drugs=drugs,
                metadata={
                    "query": f"{disease} >> efo >> chembl_molecule",
                    "min_phase_filter": min_phase,
                    "drug_count": len(drugs),
                    "pages_fetched": result.get("pages_fetched", 1)
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": f"{disease} >> efo >> chembl_molecule"}
            )
