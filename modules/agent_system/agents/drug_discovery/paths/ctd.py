"""PATH 24: CTD (Comparative Toxicogenomics Database) Path.

Retrieves chemical-gene interactions and disease associations from CTD.
CTD provides curated data about:
- Chemical-gene/protein interactions
- Chemical-disease associations
- Gene-disease associations

Query chain: disease >> mesh >> ctd OR drug_name >> text >> ctd

Data includes:
- Gene interactions with action types (increases/decreases expression, etc.)
- Disease associations (direct evidence or inferred)
- PubMed references for each interaction
"""

from typing import Dict, Any, List, Optional
from collections import defaultdict

from .base import BasePath, PathResult


# Interaction action categories for summarization
INTERACTION_CATEGORIES = {
    'expression': ['increases^expression', 'decreases^expression', 'affects^expression'],
    'activity': ['increases^activity', 'decreases^activity', 'affects^activity'],
    'binding': ['affects^binding', 'binds'],
    'metabolism': ['affects^metabolic processing', 'increases^metabolic processing', 'decreases^metabolic processing'],
    'transport': ['affects^transport', 'increases^transport', 'decreases^transport'],
    'secretion': ['increases^secretion', 'decreases^secretion', 'affects^secretion'],
    'response': ['affects^response to substance'],
}


def categorize_interaction(actions: List[str]) -> str:
    """Categorize interaction based on action types."""
    if not actions:
        return 'unknown'

    actions_lower = [a.lower() for a in actions]

    for category, keywords in INTERACTION_CATEGORIES.items():
        for keyword in keywords:
            if any(keyword in a for a in actions_lower):
                return category

    return 'other'


def extract_effect_direction(actions: List[str]) -> str:
    """Extract whether chemical increases, decreases, or affects target."""
    if not actions:
        return 'unknown'

    actions_str = ' '.join(actions).lower()

    if 'increases' in actions_str:
        return 'increases'
    elif 'decreases' in actions_str:
        return 'decreases'
    elif 'affects' in actions_str:
        return 'affects'
    else:
        return 'unknown'


class CTDPath(BasePath):
    """
    PATH 24: CTD Chemical-Gene-Disease Interactions.

    Retrieves curated interactions between chemicals and genes,
    plus disease associations from the Comparative Toxicogenomics Database.

    Useful for:
    - Understanding drug mechanisms (what genes does a drug affect?)
    - Finding toxicological effects (adverse gene expression changes)
    - Disease connection (which diseases are linked to a chemical?)
    - Literature evidence (PubMed citations for each interaction)
    """

    @property
    def name(self) -> str:
        return "ctd"

    @property
    def description(self) -> str:
        return "CTD chemical-gene interactions and disease associations"

    async def _get_ctd_by_mesh(self, mesh_id: str) -> Optional[Dict[str, Any]]:
        """Get CTD data by MeSH ID."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[mesh_id],
                mapfilter="ctd",
                mode="full"
            )

            for r in result.get('results', {}).get('results', []):
                attr = r.get('Attributes', {}).get('Ctd', {})
                if attr:
                    return attr
            return None
        except Exception:
            return None

    async def _search_ctd_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Search CTD by chemical name via text search."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[name],
                mapfilter="text>>ctd",
                mode="full"
            )

            results = []
            for r in result.get('results', {}).get('results', []):
                for t in r.get('targets', []):
                    attr = t.get('ctd', {})
                    if attr:
                        results.append(attr)
            return results
        except Exception:
            return []

    async def execute(
        self,
        disease: str,
        drugs: List[Dict] = None,
        mesh_ids: List[str] = None,
        max_interactions: int = 100,
        include_inferred: bool = True,
        organisms: List[str] = None,
        **kwargs
    ) -> PathResult:
        """
        Get CTD data for drugs or chemicals.

        Args:
            disease: Disease name (for context)
            drugs: List of drug dicts with 'mesh_id' or 'name'
            mesh_ids: Direct MeSH IDs to query
            max_interactions: Limit gene interactions per chemical
            include_inferred: Include disease associations inferred via genes
            organisms: Filter to specific organisms (e.g., ['Homo sapiens'])

        Returns:
            PathResult with CTD chemical-gene-disease data
        """
        # Collect query terms
        query_terms = []

        if mesh_ids:
            for mid in mesh_ids:
                query_terms.append(('mesh', mid))

        if drugs:
            for drug in drugs:
                if drug.get('mesh_id'):
                    query_terms.append(('mesh', drug['mesh_id']))
                elif drug.get('name'):
                    query_terms.append(('name', drug['name']))

        if not query_terms:
            return self._create_result(
                success=True,
                data={"chemicals": [], "note": "No drugs or MeSH IDs provided"},
                metadata={"query": "ctd"}
            )

        try:
            chemicals = []
            all_gene_interactions = []
            all_disease_associations = []
            genes_affected = defaultdict(list)  # gene -> list of chemicals affecting it

            for query_type, query_value in query_terms[:20]:  # Limit to 20 queries
                ctd_data = None

                if query_type == 'mesh':
                    ctd_data = await self._get_ctd_by_mesh(query_value)
                else:
                    results = await self._search_ctd_by_name(query_value)
                    if results:
                        ctd_data = results[0]

                if not ctd_data:
                    continue

                chemical_id = ctd_data.get('chemical_id', '')
                chemical_name = ctd_data.get('chemical_name', '')

                # Process gene interactions
                gene_interactions = ctd_data.get('gene_interactions', [])

                # Filter by organism if specified
                if organisms:
                    gene_interactions = [
                        gi for gi in gene_interactions
                        if gi.get('organism') in organisms
                    ]

                # Limit interactions
                gene_interactions = gene_interactions[:max_interactions]

                # Categorize interactions
                interaction_summary = defaultdict(int)
                effect_summary = defaultdict(int)

                for gi in gene_interactions:
                    gene = gi.get('gene_symbol', '')
                    actions = gi.get('interaction_actions', [])

                    category = categorize_interaction(actions)
                    direction = extract_effect_direction(actions)

                    interaction_summary[category] += 1
                    effect_summary[direction] += 1

                    if gene:
                        genes_affected[gene].append({
                            'chemical': chemical_name,
                            'chemical_id': chemical_id,
                            'actions': actions,
                            'organism': gi.get('organism', ''),
                        })

                    all_gene_interactions.append({
                        'chemical': chemical_name,
                        'chemical_id': chemical_id,
                        **gi
                    })

                # Process disease associations
                disease_assocs = ctd_data.get('disease_associations', [])

                # Filter to direct evidence only if requested
                if not include_inferred:
                    disease_assocs = [
                        da for da in disease_assocs
                        if da.get('direct_evidence')
                    ]

                for da in disease_assocs:
                    all_disease_associations.append({
                        'chemical': chemical_name,
                        'chemical_id': chemical_id,
                        **da
                    })

                chemicals.append({
                    'chemical_id': chemical_id,
                    'chemical_name': chemical_name,
                    'cas_rn': ctd_data.get('cas_rn', ''),
                    'pubchem_cid': ctd_data.get('pubchem_cid', ''),
                    'inchi_key': ctd_data.get('inchi_key', ''),
                    'definition': ctd_data.get('definition', ''),
                    'gene_interaction_count': len(gene_interactions),
                    'disease_association_count': len(disease_assocs),
                    'interaction_categories': dict(interaction_summary),
                    'effect_directions': dict(effect_summary),
                    'top_genes': list(set(
                        gi.get('gene_symbol') for gi in gene_interactions[:20]
                        if gi.get('gene_symbol')
                    )),
                })

            # Build summary
            unique_genes = set()
            unique_diseases = set()

            for gi in all_gene_interactions:
                if gi.get('gene_symbol'):
                    unique_genes.add(gi['gene_symbol'])

            for da in all_disease_associations:
                if da.get('disease_name'):
                    unique_diseases.add(da['disease_name'])

            # Find shared targets (genes affected by multiple chemicals)
            shared_targets = {
                gene: chems for gene, chems in genes_affected.items()
                if len(chems) > 1
            }

            return self._create_result(
                success=True,
                data={
                    "chemicals": chemicals,
                    "gene_interactions": all_gene_interactions[:500],  # Limit output
                    "disease_associations": all_disease_associations[:200],
                    "genes_affected": dict(genes_affected),
                    "shared_targets": shared_targets,
                    "summary": {
                        "chemicals_found": len(chemicals),
                        "total_gene_interactions": len(all_gene_interactions),
                        "total_disease_associations": len(all_disease_associations),
                        "unique_genes": len(unique_genes),
                        "unique_diseases": len(unique_diseases),
                        "shared_target_count": len(shared_targets),
                    },
                    "note": f"CTD data for {disease} related chemicals"
                },
                genes=list(unique_genes),
                metadata={
                    "query": "ctd chemical-gene-disease",
                    "chemicals_queried": len(query_terms),
                    "max_interactions": max_interactions,
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "ctd"}
            )
