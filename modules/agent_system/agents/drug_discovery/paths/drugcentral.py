"""PATH 25: DrugCentral Drug-Target Interactions.

Retrieves drug-target interactions with mechanism of action (MOA) data
from DrugCentral, a comprehensive drug information resource.

Query chain: drug_name >> text >> drugcentral OR struct_id >> drugcentral

Data includes:
- Target proteins (UniProt accessions, gene symbols)
- Action types (INHIBITOR, AGONIST, ANTAGONIST, etc.)
- Activity values (Ki, IC50, etc.)
- Target classes (Enzyme, GPCR, Ion channel, etc.)
- Target development level (Tclin, Tchem, Tbio, Tdark)
"""

from typing import Dict, Any, List, Optional
from collections import defaultdict

from .base import BasePath, PathResult


# Target Development Levels (TDL) from TCRD/Pharos
TDL_DESCRIPTIONS = {
    'Tclin': 'Clinical - approved drug target',
    'Tchem': 'Chemical - has small molecule with activity < 30nM',
    'Tbio': 'Biological - has GO annotations or OMIM phenotype',
    'Tdark': 'Dark - little known about this protein',
}

# Action type categories
ACTION_CATEGORIES = {
    'inhibitors': ['INHIBITOR', 'BLOCKER', 'ANTAGONIST', 'NEGATIVE MODULATOR', 'INVERSE AGONIST'],
    'activators': ['AGONIST', 'ACTIVATOR', 'POSITIVE MODULATOR', 'PARTIAL AGONIST', 'POSITIVE ALLOSTERIC MODULATOR'],
    'binders': ['BINDER', 'LIGAND', 'SUBSTRATE', 'COFACTOR'],
    'modulators': ['MODULATOR', 'ALLOSTERIC MODULATOR'],
}


def categorize_action(action_type: str) -> str:
    """Categorize action type into broader category."""
    if not action_type:
        return 'unknown'

    action_upper = action_type.upper()

    for category, keywords in ACTION_CATEGORIES.items():
        if any(kw in action_upper for kw in keywords):
            return category

    return 'other'


def parse_activity_value(value_str: str, act_type: str) -> Dict[str, Any]:
    """Parse activity value string to numeric with interpretation."""
    if not value_str:
        return {'value': None, 'type': act_type, 'interpretation': None}

    try:
        value = float(value_str)

        # Interpret potency based on value and type
        interpretation = None
        if act_type and act_type.lower() in ('ki', 'ic50', 'kd', 'ec50'):
            if value < 10:
                interpretation = 'very_potent'
            elif value < 100:
                interpretation = 'potent'
            elif value < 1000:
                interpretation = 'moderate'
            else:
                interpretation = 'weak'

        return {
            'value': value,
            'type': act_type,
            'interpretation': interpretation
        }
    except (ValueError, TypeError):
        return {'value': None, 'type': act_type, 'interpretation': None}


class DrugCentralPath(BasePath):
    """
    PATH 25: DrugCentral Drug-Target Interactions.

    Retrieves drug-target interactions with mechanism of action (MOA) from
    DrugCentral, providing detailed pharmacological target information.

    Useful for:
    - Target identification (what proteins does a drug bind?)
    - Mechanism of action (how does the drug work?)
    - Polypharmacology (multiple targets per drug)
    - Target druggability assessment (TDL levels)
    - Off-target prediction (unexpected targets)
    """

    @property
    def name(self) -> str:
        return "drugcentral"

    @property
    def description(self) -> str:
        return "DrugCentral drug-target interactions and MOA data"

    async def _get_drugcentral_by_id(self, struct_id: str) -> Optional[Dict[str, Any]]:
        """Get DrugCentral data by struct_id."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[struct_id],
                mapfilter="drugcentral",
                mode="full"
            )

            for r in result.get('results', {}).get('results', []):
                attr = r.get('Attributes', {}).get('Drugcentral', {})
                if attr:
                    return attr
            return None
        except Exception:
            return None

    async def _search_drugcentral_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Search DrugCentral by drug name via text search."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[name],
                mapfilter="text>>drugcentral",
                mode="full"
            )

            results = []
            for r in result.get('results', {}).get('results', []):
                for t in r.get('targets', []):
                    attr = t.get('drugcentral', {})
                    if attr:
                        results.append(attr)
            return results
        except Exception:
            return []

    async def execute(
        self,
        disease: str,
        drugs: List[Dict] = None,
        struct_ids: List[str] = None,
        action_types: List[str] = None,
        target_classes: List[str] = None,
        tdl_filter: List[str] = None,
        human_only: bool = True,
        **kwargs
    ) -> PathResult:
        """
        Get DrugCentral drug-target data.

        Args:
            disease: Disease name (for context)
            drugs: List of drug dicts with 'drugcentral_id', 'struct_id', or 'name'
            struct_ids: Direct DrugCentral struct_ids to query
            action_types: Filter to specific action types (e.g., ['INHIBITOR'])
            target_classes: Filter to specific target classes (e.g., ['Enzyme'])
            tdl_filter: Filter to specific TDL levels (e.g., ['Tclin', 'Tchem'])
            human_only: Only include human targets (default: True)

        Returns:
            PathResult with drug-target interaction data
        """
        # Collect query terms
        query_terms = []

        if struct_ids:
            for sid in struct_ids:
                query_terms.append(('id', sid))

        if drugs:
            for drug in drugs:
                if drug.get('drugcentral_id') or drug.get('struct_id'):
                    sid = drug.get('drugcentral_id') or drug.get('struct_id')
                    query_terms.append(('id', str(sid)))
                elif drug.get('name'):
                    query_terms.append(('name', drug['name']))

        if not query_terms:
            return self._create_result(
                success=True,
                data={"drugs": [], "note": "No drugs or struct_ids provided"},
                metadata={"query": "drugcentral"}
            )

        try:
            drug_results = []
            all_targets = []
            targets_by_protein = defaultdict(list)  # UniProt -> list of drugs targeting it
            action_type_counts = defaultdict(int)
            target_class_counts = defaultdict(int)
            tdl_counts = defaultdict(int)

            for query_type, query_value in query_terms[:30]:  # Limit queries
                dc_data = None

                if query_type == 'id':
                    dc_data = await self._get_drugcentral_by_id(query_value)
                else:
                    results = await self._search_drugcentral_by_name(query_value)
                    if results:
                        dc_data = results[0]

                if not dc_data:
                    continue

                struct_id = dc_data.get('struct_id', '')
                drug_name = dc_data.get('drug_name', '')

                # Process targets
                targets = dc_data.get('targets', [])

                # Filter by organism
                if human_only:
                    targets = [
                        t for t in targets
                        if 'homo sapiens' in (t.get('organism', '') or '').lower()
                    ]

                # Filter by action type
                if action_types:
                    action_types_upper = [at.upper() for at in action_types]
                    targets = [
                        t for t in targets
                        if (t.get('action_type', '') or '').upper() in action_types_upper
                    ]

                # Filter by target class
                if target_classes:
                    target_classes_lower = [tc.lower() for tc in target_classes]
                    targets = [
                        t for t in targets
                        if (t.get('target_class', '') or '').lower() in target_classes_lower
                    ]

                # Filter by TDL
                if tdl_filter:
                    targets = [
                        t for t in targets
                        if t.get('tdl') in tdl_filter
                    ]

                # Process each target
                processed_targets = []
                for target in targets:
                    action_type = target.get('action_type', '')
                    target_class = target.get('target_class', '')
                    tdl = target.get('tdl', '')

                    # Parse activity value
                    activity = parse_activity_value(
                        target.get('act_value'),
                        target.get('act_type')
                    )

                    processed_target = {
                        'drug_name': drug_name,
                        'struct_id': struct_id,
                        'target_name': target.get('target_name', ''),
                        'uniprot_accession': target.get('uniprot_accession', ''),
                        'gene_symbol': target.get('gene_symbol', ''),
                        'target_class': target_class,
                        'action_type': action_type,
                        'action_category': categorize_action(action_type),
                        'has_moa': target.get('has_moa', False),
                        'moa_source': target.get('moa_source', ''),
                        'activity_value': activity['value'],
                        'activity_type': activity['type'],
                        'activity_interpretation': activity['interpretation'],
                        'tdl': tdl,
                        'tdl_description': TDL_DESCRIPTIONS.get(tdl, ''),
                        'organism': target.get('organism', ''),
                    }
                    processed_targets.append(processed_target)
                    all_targets.append(processed_target)

                    # Aggregate stats
                    if action_type:
                        action_type_counts[action_type] += 1
                    if target_class:
                        target_class_counts[target_class] += 1
                    if tdl:
                        tdl_counts[tdl] += 1

                    # Track by protein
                    uniprot = target.get('uniprot_accession')
                    if uniprot:
                        targets_by_protein[uniprot].append({
                            'drug': drug_name,
                            'struct_id': struct_id,
                            'action_type': action_type,
                        })

                drug_results.append({
                    'struct_id': struct_id,
                    'drug_name': drug_name,
                    'inn_name': dc_data.get('inn_name', ''),
                    'cas_rn': dc_data.get('cas_rn', ''),
                    'smiles': dc_data.get('smiles', ''),
                    'inchi_key': dc_data.get('inchi_key', ''),
                    'target_count': len(processed_targets),
                    'target_classes': list(set(
                        t.get('target_class') for t in processed_targets
                        if t.get('target_class')
                    )),
                    'action_types': list(set(
                        t.get('action_type') for t in processed_targets
                        if t.get('action_type')
                    )),
                    'targets': processed_targets,
                })

            # Find shared targets (proteins targeted by multiple drugs)
            shared_targets = {
                protein: drugs_list
                for protein, drugs_list in targets_by_protein.items()
                if len(drugs_list) > 1
            }

            # Summary
            unique_targets = set()
            unique_genes = set()
            for t in all_targets:
                if t.get('uniprot_accession'):
                    unique_targets.add(t['uniprot_accession'])
                if t.get('gene_symbol'):
                    unique_genes.add(t['gene_symbol'])

            return self._create_result(
                success=True,
                data={
                    "drugs": drug_results,
                    "all_targets": all_targets[:500],
                    "shared_targets": shared_targets,
                    "summary": {
                        "drugs_found": len(drug_results),
                        "total_interactions": len(all_targets),
                        "unique_targets": len(unique_targets),
                        "unique_genes": len(unique_genes),
                        "action_type_distribution": dict(action_type_counts),
                        "target_class_distribution": dict(target_class_counts),
                        "tdl_distribution": dict(tdl_counts),
                        "shared_target_count": len(shared_targets),
                    },
                    "note": f"DrugCentral data for {disease} drugs"
                },
                genes=list(unique_genes),
                metadata={
                    "query": "drugcentral drug-target",
                    "drugs_queried": len(query_terms),
                    "human_only": human_only,
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "drugcentral"}
            )
