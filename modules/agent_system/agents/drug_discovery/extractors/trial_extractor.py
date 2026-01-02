"""Clinical Trial Extraction from BioBTree Results.

Extract clinical trials from ClinicalTrials.gov data via BioBTree.
"""

from typing import List, Dict, Any, Optional


class TrialExtractor:
    """Extract clinical trials from BioBTree query results."""

    # Phase ordering for sorting (lower = higher priority)
    PHASE_ORDER = {
        "PHASE4": 0, "PHASE3": 1, "PHASE2/PHASE3": 2, "PHASE2": 3,
        "PHASE1/PHASE2": 4, "PHASE1": 5, "EARLY_PHASE1": 6, "NA": 7, "": 8
    }

    # Status ordering for sorting (lower = higher priority)
    STATUS_ORDER = {
        "RECRUITING": 0, "ENROLLING_BY_INVITATION": 1, "ACTIVE_NOT_RECRUITING": 2,
        "COMPLETED": 3, "TERMINATED": 4, "WITHDRAWN": 5, "SUSPENDED": 6,
        "NOT_YET_RECRUITING": 7, "UNKNOWN_STATUS": 8, "": 9
    }

    def extract_trials(
        self,
        result: Dict,
        phase_filter: Optional[List[str]] = None,
        status_filter: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Extract clinical trials from query results.

        Args:
            result: BioBTree query result
            phase_filter: Optional list of phases to include (e.g., ["PHASE3", "PHASE4"])
            status_filter: Optional list of statuses to include (e.g., ["RECRUITING", "COMPLETED"])

        Returns:
            List of clinical trial dicts
        """
        trials = []
        seen_ids = set()

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            for target in r.get("targets", []):
                trial_id = target.get("identifier", "")
                if trial_id in seen_ids or not trial_id.startswith("NCT"):
                    continue

                # Get clinical trial attributes
                ct_data = target.get("clinical_trials", {})
                if not ct_data:
                    attrs = target.get("Attributes", {})
                    ct_data = attrs.get("ClinicalTrials", {}) or attrs.get("clinical_trials", {})

                if not ct_data:
                    # Still add with minimal info if we have the NCT ID
                    trials.append({
                        "nct_id": trial_id,
                        "title": "",
                        "phase": "",
                        "status": "",
                        "study_type": "",
                        "conditions": [],
                        "interventions": []
                    })
                    seen_ids.add(trial_id)
                    continue

                phase = ct_data.get("phase", "")
                status = ct_data.get("overall_status", "")

                # Apply phase filter if provided
                if phase_filter and phase and phase not in phase_filter:
                    continue

                # Apply status filter if provided
                if status_filter and status and status not in status_filter:
                    continue

                # Extract interventions
                interventions = ct_data.get("interventions", [])
                intervention_names = []
                if isinstance(interventions, list):
                    for i in interventions:
                        if isinstance(i, dict):
                            name = i.get("name", "")
                            itype = i.get("type", "")
                            if name:
                                intervention_names.append(f"{name} ({itype})" if itype else name)
                        elif isinstance(i, str):
                            intervention_names.append(i)

                # Extract conditions
                conditions = ct_data.get("conditions", [])
                if not isinstance(conditions, list):
                    conditions = [conditions] if conditions else []

                trial_entry = {
                    "nct_id": trial_id,
                    "title": ct_data.get("brief_title", "") or ct_data.get("official_title", ""),
                    "phase": phase,
                    "status": status,
                    "study_type": ct_data.get("study_type", ""),
                    "conditions": conditions,
                    "interventions": intervention_names,
                    "enrollment": ct_data.get("enrollment"),
                    "start_date": ct_data.get("start_date", ""),
                    "completion_date": ct_data.get("completion_date", "")
                }

                trials.append(trial_entry)
                seen_ids.add(trial_id)

        # Sort by phase (higher phases first) and then by status (RECRUITING first)
        trials.sort(key=lambda t: (
            self.PHASE_ORDER.get(t.get("phase", ""), 8),
            self.STATUS_ORDER.get(t.get("status", ""), 9)
        ))

        return trials
