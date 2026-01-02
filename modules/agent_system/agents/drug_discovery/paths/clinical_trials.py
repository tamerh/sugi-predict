"""PATH 11: Clinical Trials.

Query clinical trials from ClinicalTrials.gov via BioBTree.
Path: disease >> clinical_trials
"""

from typing import Dict, Any, List, Optional

from .base import BasePath, PathResult
from ..extractors.trial_extractor import TrialExtractor


class ClinicalTrialsPath(BasePath):
    """
    PATH 11: Query clinical trials for a disease.

    Returns trials with phase, status, interventions, and conditions.
    """

    @property
    def name(self) -> str:
        return "clinical_trials"

    @property
    def description(self) -> str:
        return "Clinical trials from ClinicalTrials.gov"

    async def execute(
        self,
        disease: str,
        phase_filter: Optional[List[str]] = None,
        status_filter: Optional[List[str]] = None,
        **kwargs
    ) -> PathResult:
        """
        Execute clinical trials query.

        Args:
            disease: Disease name or ID
            phase_filter: Optional list of phases to include
            status_filter: Optional list of statuses to include

        Returns:
            PathResult with clinical trials
        """
        try:
            # Query: disease >> clinical_trials
            mapfilter = ">>clinical_trials"
            result = await self.biobtree.map_query_all_pages(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            # Wrap flat result for extractor
            wrapped_result = {"results": {"results": [{"targets": result.get("targets", [])}]}}

            # Extract trials
            extractor = TrialExtractor()
            trials = extractor.extract_trials(
                {"data": wrapped_result},
                phase_filter=phase_filter,
                status_filter=status_filter
            )

            # Group trials by phase and status for summary
            phase_counts = {}
            status_counts = {}
            for trial in trials:
                phase = trial.get("phase", "UNKNOWN")
                status = trial.get("status", "UNKNOWN")
                phase_counts[phase] = phase_counts.get(phase, 0) + 1
                status_counts[status] = status_counts.get(status, 0) + 1

            recruiting_count = status_counts.get("RECRUITING", 0)

            return self._create_result(
                success=True,
                data={
                    "trials": trials,
                    "count": len(trials),
                    "by_phase": phase_counts,
                    "by_status": status_counts,
                    "recruiting_count": recruiting_count,
                    "note": f"Clinical trials from ClinicalTrials.gov for {disease}"
                },
                metadata={
                    "query": f"{disease} >> clinical_trials",
                    "trial_count": len(trials),
                    "recruiting_count": recruiting_count,
                    "pages_fetched": result.get("pages_fetched", 1)
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": f"{disease} >> clinical_trials"}
            )
