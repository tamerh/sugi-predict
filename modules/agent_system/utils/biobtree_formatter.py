"""
BioBTree result formatting utilities.

Provides functions to filter and format BioBTree query results for better
presentation to LLMs and users.
"""

from typing import Dict, List, Optional


# Ensembl ID prefix to species mapping
SPECIES_MAP = {
    'ENSG': 'Human',
    'ENSMUSG': 'Mouse',
    'ENSRNOG': 'Rat',
    'ENSDARG': 'Zebrafish',
    'ENSGALG': 'Chicken',
    'ENSCAFG': 'Dog',
    'ENSBTAG': 'Cow',
    'ENSSSCG': 'Pig',
}


def get_species_from_ensembl(ensembl_id: str) -> str:
    """
    Detect species from Ensembl ID prefix.

    Args:
        ensembl_id: Ensembl identifier (e.g., "ENSG00000141510")

    Returns:
        Species name or "Unknown"
    """
    for prefix, species in SPECIES_MAP.items():
        if ensembl_id.startswith(prefix):
            return species
    return "Unknown"


def extract_canonical_protein(targets: List[Dict]) -> Optional[Dict]:
    """
    Extract the canonical/reviewed protein from a list of UniProt targets.

    Args:
        targets: List of target dictionaries from BioBTree response

    Returns:
        Canonical protein dict or None if not found
    """
    for target in targets:
        # Check if this is a reviewed UniProt entry
        if target.get('dataset_name') == 'uniprot':
            # gRPC response uses lowercase keys
            uniprot_data = target.get('uniprot')
            if uniprot_data and uniprot_data.get('reviewed', False):
                return {
                    'identifier': target['identifier'],
                    'name': uniprot_data.get('names', ['Unknown'])[0],
                    'alternative_names': uniprot_data.get('alternative_names', []),
                    'sequence_mass': uniprot_data.get('sequence', {}).get('mass'),
                    'url': target.get('url', ''),
                    'reviewed': True
                }
    return None


def filter_canonical_proteins(
    biobtree_response: Dict,
    species_filter: Optional[str] = None,
    human_only: bool = False
) -> List[Dict]:
    """
    Filter BioBTree mapping results to canonical/reviewed proteins only.

    Args:
        biobtree_response: Raw BioBTree API response
        species_filter: Optional species to filter for (e.g., "Human")
        human_only: If True, return only human results

    Returns:
        List of filtered results with canonical proteins

    Example:
        >>> results = filter_canonical_proteins(response, human_only=True)
        >>> for r in results:
        ...     print(f"{r['gene']} -> {r['protein']['identifier']}")
        TP53 -> P04637
        BRCA1 -> P38398
    """
    if species_filter and human_only:
        raise ValueError("Cannot specify both species_filter and human_only")

    if human_only:
        species_filter = "Human"

    results_list = biobtree_response.get('results', {}).get('results', [])

    filtered = []
    for result in results_list:
        source = result.get('source', {})
        targets = result.get('targets', [])

        # Get species from Ensembl ID
        ensembl_id = source.get('identifier', '')
        species = get_species_from_ensembl(ensembl_id)

        # Apply species filter
        if species_filter and species != species_filter:
            continue

        # Extract canonical protein
        canonical = extract_canonical_protein(targets)

        if canonical:
            filtered.append({
                'gene': source.get('keyword', 'Unknown'),
                'ensembl_id': ensembl_id,
                'species': species,
                'protein': canonical,
                'total_targets': len(targets)
            })

    return filtered


def format_biobtree_results(
    biobtree_response: Dict,
    human_only: bool = False,
    show_all_species: bool = True
) -> str:
    """
    Format BioBTree results into human-readable text.

    Args:
        biobtree_response: Raw BioBTree API response
        human_only: If True, show only human results
        show_all_species: If True, show all species; otherwise prioritize human

    Returns:
        Formatted string suitable for LLM response

    Example output:
        TP53 (Human):
          Ensembl: ENSG00000141510
          UniProt: P04637 - Cellular tumor antigen p53

        BRCA1 (Human):
          Ensembl: ENSG00000012048
          UniProt: P38398 - Breast cancer type 1 susceptibility protein
    """
    filtered = filter_canonical_proteins(
        biobtree_response,
        human_only=human_only
    )

    if not filtered:
        return "No canonical proteins found."

    # Group by gene
    by_gene = {}
    for item in filtered:
        gene = item['gene']
        if gene not in by_gene:
            by_gene[gene] = []
        by_gene[gene].append(item)

    lines = []
    for gene, items in by_gene.items():
        # If not showing all species, prioritize human
        if not show_all_species:
            human_items = [i for i in items if i['species'] == 'Human']
            if human_items:
                items = human_items[:1]  # Just the first human result
            else:
                items = items[:1]  # Just the first result

        for item in items:
            lines.append(f"{gene} ({item['species']}):")
            lines.append(f"  Ensembl: {item['ensembl_id']}")
            protein = item['protein']
            lines.append(f"  UniProt: {protein['identifier']} - {protein['name']}")
            if item['total_targets'] > 1:
                lines.append(f"  (Note: {item['total_targets']} total isoforms/variants)")
            lines.append("")

    return "\n".join(lines).strip()
