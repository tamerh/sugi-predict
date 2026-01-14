"""PATH 23: PubChem Bioactivity Data.

Retrieves detailed bioactivity measurements for drugs including:
- IC50, Ki, Kd, EC50, AC50 values with units
- Target proteins (UniProt IDs)
- Assay metadata (source, type, hit rate)
- Activity outcomes (Active, Inactive)

Query chain: drugs >> pubchem >> pubchem_activity >> pubchem_assay

Future: BAO (BioAssay Ontology) annotations for assay classification
when BAO dataset is loaded in BioBTree.
"""

from typing import Dict, Any, List, Optional
from collections import defaultdict

from .base import BasePath, PathResult


# Activity types ranked by relevance for drug discovery
ACTIVITY_TYPE_PRIORITY = {
    'ic50': 1,   # Half maximal inhibitory concentration
    'ki': 2,     # Inhibition constant
    'kd': 3,     # Dissociation constant
    'ec50': 4,   # Half maximal effective concentration
    'ac50': 5,   # Half maximal activity concentration
    'ed50': 6,   # Median effective dose
    'gi50': 7,   # Growth inhibition 50%
}


def parse_activity_value(value: float, unit: str) -> Dict[str, Any]:
    """
    Parse activity value and normalize to nM for comparison.

    Returns dict with original value, unit, and normalized nM value.
    """
    if value is None or value == 0:
        return {'value': None, 'unit': unit, 'value_nm': None}

    # Normalize to nM
    unit_lower = (unit or '').lower().strip()
    value_nm = None

    if unit_lower in ('nm', 'nanomolar'):
        value_nm = value
    elif unit_lower in ('um', 'micromolar', 'µm'):
        value_nm = value * 1000
    elif unit_lower in ('pm', 'picomolar'):
        value_nm = value / 1000
    elif unit_lower in ('mm', 'millimolar'):
        value_nm = value * 1000000
    elif unit_lower == 'm':
        value_nm = value * 1e9

    return {
        'value': value,
        'unit': unit,
        'value_nm': value_nm
    }


def categorize_potency(value_nm: float) -> str:
    """
    Categorize compound potency based on nM value.

    Categories:
    - Ultra-potent: < 1 nM
    - Very potent: 1-10 nM
    - Potent: 10-100 nM
    - Moderate: 100 nM - 1 µM
    - Weak: 1-10 µM
    - Very weak: > 10 µM
    """
    if value_nm is None:
        return 'unknown'
    if value_nm < 1:
        return 'ultra_potent'
    elif value_nm < 10:
        return 'very_potent'
    elif value_nm < 100:
        return 'potent'
    elif value_nm < 1000:
        return 'moderate'
    elif value_nm < 10000:
        return 'weak'
    else:
        return 'very_weak'


class BioactivityPath(BasePath):
    """
    PATH 23: PubChem Bioactivity Data.

    Retrieves detailed bioactivity measurements for drugs including
    IC50, Ki, Kd values, target proteins, and assay metadata.

    Useful for:
    - Target validation (what proteins does a drug bind?)
    - Potency ranking (which drugs are most potent?)
    - Off-target analysis (unexpected protein interactions)
    - Data source attribution (BindingDB, ChEMBL, screening centers)
    """

    @property
    def name(self) -> str:
        return "bioactivity"

    @property
    def description(self) -> str:
        return "PubChem bioactivity data (IC50, Ki, targets, assay details)"

    async def _get_assay_details(self, aid: str) -> Dict[str, Any]:
        """Get assay metadata for an activity."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[aid],
                mapfilter=">>pubchem_assay",
                mode="full"
            )

            for t in result.get('targets', []):
                attr = t.get('pubchem_assay', {})
                if attr:
                    return {
                        'aid': attr.get('aid', ''),
                        'name': attr.get('name', ''),
                        'source': attr.get('source_name', ''),
                        'outcome_type': attr.get('outcome_type', ''),
                        'substance_type': attr.get('substance_type', ''),
                        'bioassay_types': attr.get('bioassay_types', []),
                        'tested_cids': attr.get('tested_cids', 0),
                        'active_cids': attr.get('active_cids', 0),
                        'hit_rate': attr.get('hit_rate', 0),
                        'uniprot_ids': attr.get('uniprot_ids', []),
                    }
            return {}
        except Exception:
            return {}

    async def _get_activities_for_compound(self, cid: str) -> List[Dict[str, Any]]:
        """Get all bioactivity measurements for a compound."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[cid],
                mapfilter=">>pubchem>>pubchem_activity",
                mode="full"
            )

            activities = []
            for r in result.get('results', {}).get('results', []):
                for t in r.get('targets', []):
                    attr = t.get('pubchem_activity', {})
                    if attr:
                        # Parse activity value
                        parsed = parse_activity_value(
                            attr.get('value'),
                            attr.get('unit', '')
                        )

                        activity = {
                            'activity_id': attr.get('activity_id', ''),
                            'cid': cid,
                            'aid': attr.get('aid', ''),
                            'activity_type': (attr.get('activity_type', '') or '').lower(),
                            'activity_outcome': attr.get('activity_outcome', ''),
                            'value': parsed['value'],
                            'unit': parsed['unit'],
                            'value_nm': parsed['value_nm'],
                            'potency_category': categorize_potency(parsed['value_nm']),
                            'qualifier': attr.get('qualifier', ''),
                            'protein_accession': attr.get('protein_accession', ''),
                            'gene_id': attr.get('gene_id', ''),
                            'target_taxid': attr.get('target_taxid', 0),
                            'pmid': attr.get('pmid', ''),
                        }
                        activities.append(activity)

            return activities
        except Exception as e:
            return []

    async def execute(
        self,
        disease: str,
        drugs: List[Dict] = None,
        include_assay_details: bool = True,
        min_potency_nm: float = None,
        activity_types: List[str] = None,
        **kwargs
    ) -> PathResult:
        """
        Get bioactivity data for drugs.

        Args:
            disease: Disease name (for context)
            drugs: List of drug dicts with 'pubchem_cid' or 'chembl_id'
            include_assay_details: Fetch assay metadata (default: True)
            min_potency_nm: Filter to activities more potent than this (in nM)
            activity_types: Filter to specific types (e.g., ['ic50', 'ki'])

        Returns:
            PathResult with bioactivity data grouped by drug and target
        """
        if not drugs:
            return self._create_result(
                success=True,
                data={"activities": [], "note": "No drugs provided"},
                metadata={"query": "bioactivity"}
            )

        try:
            # Collect PubChem CIDs
            cids = []
            cid_to_drug = {}
            for drug in drugs:
                cid = drug.get('pubchem_cid') or drug.get('cid')
                if cid:
                    cids.append(str(cid))
                    cid_to_drug[str(cid)] = drug

            if not cids:
                return self._create_result(
                    success=True,
                    data={
                        "activities": [],
                        "drugs_queried": len(drugs),
                        "drugs_with_cid": 0,
                        "note": "No PubChem CIDs found in drugs"
                    },
                    metadata={"query": "bioactivity"}
                )

            # Limit to avoid timeout
            cids = cids[:30]

            # Collect all activities
            all_activities = []
            activities_by_drug = {}
            activities_by_target = defaultdict(list)
            assay_cache = {}

            for cid in cids:
                activities = await self._get_activities_for_compound(cid)

                # Filter by activity type if specified
                if activity_types:
                    activity_types_lower = [t.lower() for t in activity_types]
                    activities = [a for a in activities if a['activity_type'] in activity_types_lower]

                # Filter by potency if specified
                if min_potency_nm is not None:
                    activities = [a for a in activities if a['value_nm'] is not None and a['value_nm'] <= min_potency_nm]

                # Get assay details for unique AIDs
                if include_assay_details:
                    unique_aids = set(a['aid'] for a in activities if a['aid'])
                    for aid in unique_aids:
                        if aid not in assay_cache:
                            assay_cache[aid] = await self._get_assay_details(aid)

                    # Attach assay details to activities
                    for activity in activities:
                        aid = activity['aid']
                        if aid in assay_cache:
                            activity['assay'] = assay_cache[aid]

                # Organize by drug and target
                drug_info = cid_to_drug.get(cid, {})
                drug_name = drug_info.get('name') or drug_info.get('title') or f"CID:{cid}"

                activities_by_drug[cid] = {
                    'cid': cid,
                    'drug_name': drug_name,
                    'chembl_id': drug_info.get('chembl_id', ''),
                    'activities': activities,
                    'activity_count': len(activities),
                    'active_count': sum(1 for a in activities if a['activity_outcome'] == 'Active'),
                    'targets': list(set(a['protein_accession'] for a in activities if a['protein_accession'])),
                }

                # Group by target protein
                for activity in activities:
                    target = activity.get('protein_accession')
                    if target:
                        activities_by_target[target].append({
                            'cid': cid,
                            'drug_name': drug_name,
                            **activity
                        })

                all_activities.extend(activities)

            # Find best (most potent) activities per drug
            best_activities = []
            for cid, drug_data in activities_by_drug.items():
                # Sort by potency (lowest nM first)
                potent_activities = [a for a in drug_data['activities'] if a['value_nm'] is not None]
                if potent_activities:
                    potent_activities.sort(key=lambda x: x['value_nm'])
                    best = potent_activities[0]
                    best_activities.append({
                        'cid': cid,
                        'drug_name': drug_data['drug_name'],
                        'best_activity_type': best['activity_type'],
                        'best_value': best['value'],
                        'best_unit': best['unit'],
                        'best_value_nm': best['value_nm'],
                        'potency_category': best['potency_category'],
                        'target': best['protein_accession'],
                    })

            # Sort best activities by potency
            best_activities.sort(key=lambda x: x['best_value_nm'] if x['best_value_nm'] else float('inf'))

            # Compute summary statistics
            total_activities = len(all_activities)
            active_count = sum(1 for a in all_activities if a['activity_outcome'] == 'Active')
            unique_targets = len(activities_by_target)
            unique_assays = len(assay_cache)

            # Potency distribution
            potency_dist = defaultdict(int)
            for a in all_activities:
                potency_dist[a['potency_category']] += 1

            # Data sources
            sources = defaultdict(int)
            for assay in assay_cache.values():
                source = assay.get('source', 'Unknown')
                if source:
                    sources[source] += 1

            return self._create_result(
                success=True,
                data={
                    "activities_by_drug": activities_by_drug,
                    "activities_by_target": dict(activities_by_target),
                    "best_activities": best_activities,
                    "summary": {
                        "drugs_queried": len(drugs),
                        "drugs_with_cid": len(cids),
                        "drugs_with_activities": len([d for d in activities_by_drug.values() if d['activity_count'] > 0]),
                        "total_activities": total_activities,
                        "active_count": active_count,
                        "unique_targets": unique_targets,
                        "unique_assays": unique_assays,
                        "potency_distribution": dict(potency_dist),
                        "data_sources": dict(sources),
                    },
                    "note": f"Bioactivity data for {disease} drugs"
                },
                metadata={
                    "query": "pubchem >> pubchem_activity >> pubchem_assay",
                    "drugs_queried": len(drugs),
                    "activities_found": total_activities,
                    "unique_targets": unique_targets,
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "bioactivity"}
            )
