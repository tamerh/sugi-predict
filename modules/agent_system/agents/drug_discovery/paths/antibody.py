"""PATH 14: Therapeutic Antibodies.

Query therapeutic antibodies for disease indications.
Uses BioBTree antibody dataset (TheraSAbDab source).
"""

from typing import Dict, Any, List, Optional

from .base import BasePath, PathResult


# Common therapeutic antibodies to check for each query
# These are FDA-approved or late-stage antibodies
THERAPEUTIC_ANTIBODIES = [
    # Anti-VEGF
    "bevacizumab", "ranibizumab", "aflibercept",
    # Anti-HER2
    "trastuzumab", "pertuzumab", "ado-trastuzumab",
    # Anti-PD1/PD-L1
    "pembrolizumab", "nivolumab", "atezolizumab", "durvalumab", "avelumab",
    # Anti-CTLA4
    "ipilimumab", "tremelimumab",
    # Anti-EGFR
    "cetuximab", "panitumumab", "necitumumab",
    # Anti-CD20
    "rituximab", "obinutuzumab", "ofatumumab", "ocrelizumab",
    # Anti-CD19
    "blinatumomab",
    # Anti-CD38
    "daratumumab", "isatuximab",
    # Anti-CD52
    "alemtuzumab",
    # Anti-TNF
    "infliximab", "adalimumab", "golimumab", "certolizumab",
    # Anti-IL6
    "tocilizumab", "sarilumab", "siltuximab",
    # Anti-IL17
    "secukinumab", "ixekizumab", "brodalumab",
    # Anti-IL23
    "guselkumab", "tildrakizumab", "risankizumab",
    # Other oncology
    "ramucirumab", "olaratumab", "elotuzumab", "mogamulizumab",
    "polatuzumab", "enfortumab", "sacituzumab", "trastuzumab-deruxtecan",
]


class AntibodyPath(BasePath):
    """
    PATH 14: Query therapeutic antibodies for disease.

    Uses BioBTree antibody dataset to find therapeutic antibodies
    that have the disease in their approved/trial indications.

    Data source: TheraSAbDab (Therapeutic Structural Antibody Database)
    """

    @property
    def name(self) -> str:
        return "antibody"

    @property
    def description(self) -> str:
        return "Therapeutic antibodies for disease indications"

    async def execute(
        self,
        disease: str,
        antibody_list: List[str] = None,
        **kwargs
    ) -> PathResult:
        """
        Execute antibody query for disease.

        Args:
            disease: Disease name to match against indications
            antibody_list: Optional specific antibodies to check (defaults to common list)

        Returns:
            PathResult with therapeutic antibodies for the disease
        """
        try:
            # Use provided list or default therapeutic antibodies
            antibodies_to_check = antibody_list or THERAPEUTIC_ANTIBODIES

            # Query all antibodies at once
            result = await self.biobtree.map_query_all_pages(
                terms=antibodies_to_check,
                mapfilter=">>antibody",
                mode="full",
                preserve_sources=True
            )

            # Process results - filter by indication
            disease_lower = disease.lower()
            matching_antibodies = []

            results_list = result.get("results", {}).get("results", [])

            for r in results_list:
                source = r.get("source", {})
                ab_data = source.get("antibody", {})

                if not ab_data:
                    continue

                # Check if disease matches any indication
                indications = ab_data.get("indications", [])
                matching_indications = [
                    ind for ind in indications
                    if ind and disease_lower in ind.lower()
                ]

                if matching_indications:
                    ab_name = ab_data.get("inn_name", source.get("identifier", ""))
                    targets = ab_data.get("targets", [])

                    antibody_entry = {
                        "name": ab_name,
                        "identifier": source.get("identifier", ""),
                        "type": ab_data.get("antibody_type", ""),
                        "format": ab_data.get("format", ""),
                        "isotype": ab_data.get("isotype", ""),
                        "light_chain": ab_data.get("light_chain", ""),
                        "status": ab_data.get("status", ""),
                        "targets": targets,
                        "matching_indications": matching_indications,
                        "all_indications_count": len(indications),
                        "source": ab_data.get("source", "therasabdab"),
                    }

                    # Include sequence info if available (useful for biologics analysis)
                    if ab_data.get("heavy_chain_seq"):
                        antibody_entry["has_sequence"] = True

                    matching_antibodies.append(antibody_entry)

            # Sort by number of matching indications (more specific matches first)
            matching_antibodies.sort(
                key=lambda x: len(x.get("matching_indications", [])),
                reverse=True
            )

            # Group by target
            by_target = {}
            for ab in matching_antibodies:
                for target in ab.get("targets", ["Unknown"]):
                    if target not in by_target:
                        by_target[target] = []
                    by_target[target].append(ab["name"])

            return self._create_result(
                success=True,
                data={
                    "antibodies": matching_antibodies,
                    "count": len(matching_antibodies),
                    "by_target": by_target,
                    "disease": disease,
                    "note": f"Therapeutic antibodies with {disease} in indications"
                },
                metadata={
                    "query": "antibody (indication filter)",
                    "antibodies_checked": len(antibodies_to_check),
                    "antibodies_matched": len(matching_antibodies),
                    "timing_ms": result.get("_client_timing_ms", 0)
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "antibody"}
            )
