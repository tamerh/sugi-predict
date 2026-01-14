"""PATH 6: PubChem Drug Data.

Two complementary approaches:
- PATH 6a: Enrich ChEMBL drugs with PubChem data via InChI key matching
- PATH 6b: Find FDA compounds via target bioactivity (Uniprot >> pubchem_activity >> pubchem)

New fields available (Jan 2026):
- pharmacological_actions: Drug mechanism/class (e.g., "ACE Inhibitors", "Statins")
- compound_type: Classification (drug, literature, patent, bioactive, biologic)
- Drug-likeness: xlogp, hydrogen_bond_donors/acceptors, tpsa, rotatable_bonds
- External IDs: unii (FDA), dtxsid (EPA toxicity), nsc_ids (NCI)
- Cross-refs: PubMed literature count, Patent count
"""

from typing import Dict, Any, List, Optional
import re

from .base import BasePath, PathResult


def compute_lipinski_violations(
    mw: float,
    hbd: int,
    hba: int,
    logp: float
) -> Dict[str, Any]:
    """
    Compute Lipinski's Rule of Five violations for oral drug-likeness.

    Rule of Five thresholds:
    - Molecular Weight ≤ 500 Da
    - Hydrogen Bond Donors ≤ 5
    - Hydrogen Bond Acceptors ≤ 10
    - LogP ≤ 5

    Returns dict with violations count and details.
    """
    violations = []

    if mw and mw > 500:
        violations.append(f"MW={mw:.1f}>500")
    if hbd and hbd > 5:
        violations.append(f"HBD={hbd}>5")
    if hba and hba > 10:
        violations.append(f"HBA={hba}>10")
    if logp and logp > 5:
        violations.append(f"LogP={logp:.1f}>5")

    return {
        "violations": len(violations),
        "details": violations,
        "drug_like": len(violations) <= 1  # 0-1 violations is acceptable
    }


class PubChemEnrichmentPath(BasePath):
    """
    PATH 6a: Enrich ChEMBL drugs with PubChem data via InChI key.

    Takes drugs from ChEMBL (PATH 1) and finds their PubChem equivalents
    to get additional data: FDA approval status, synonyms/trade names,
    drug class (via MeSH pharmacological_actions), therapeutic scope, etc.
    """

    @property
    def name(self) -> str:
        return "pubchem_enrichment"

    @property
    def description(self) -> str:
        return "Enrich ChEMBL drugs with PubChem + MeSH data (FDA status, drug class, synonyms)"

    async def _get_mesh_data(self, pubchem_cid: str) -> Dict[str, Any]:
        """Get MeSH descriptor data for a PubChem compound."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[pubchem_cid],
                mapfilter=">>pubchem>>mesh",
                mode="full"
            )

            # Extract MeSH data from targets (full mode returns in targets)
            targets = result.get('targets', [])
            for t in targets:
                mesh = t.get('mesh', {})
                if mesh:
                    return {
                        'mesh_id': mesh.get('descriptor_ui', ''),
                        'mesh_name': mesh.get('descriptor_name', ''),
                        'drug_class': mesh.get('pharmacological_actions', []),
                        'trade_names': mesh.get('entry_terms', []),
                        'therapeutic_scope': mesh.get('scope_note', ''),
                    }
            return {}
        except Exception:
            return {}

    async def _get_literature_count(self, pubchem_cid: str) -> int:
        """Get count of PubMed literature references for a compound."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[pubchem_cid],
                mapfilter=">>pubchem>>pubmed",
                mode="lite"
            )
            return len(result.get('targets', []))
        except Exception:
            return 0

    async def _get_patent_count(self, pubchem_cid: str) -> int:
        """Get count of patents referencing a compound."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[pubchem_cid],
                mapfilter=">>pubchem>>patent",
                mode="lite"
            )
            return len(result.get('targets', []))
        except Exception:
            return 0

    async def execute(self, disease: str, drugs: List[Dict] = None, **kwargs) -> PathResult:
        """
        Enrich ChEMBL drugs with PubChem data via InChI key matching.

        Args:
            disease: Disease name (for metadata)
            drugs: List of drug dicts from ChEMBL with 'chembl_id' and optionally 'inchi_key'

        Returns:
            PathResult with enriched drug data
        """
        if not drugs:
            return self._create_result(
                success=True,
                data={"enriched_drugs": [], "note": "No drugs provided for enrichment"},
                metadata={"query": "pubchem_enrichment"}
            )

        try:
            # Step 1: Get InChI keys for drugs that don't have them
            drugs_needing_inchi = [d for d in drugs if not d.get('inchi_key')]
            chembl_ids = [d.get('chembl_id') for d in drugs_needing_inchi if d.get('chembl_id')]

            inchi_map = {}
            if chembl_ids:
                # Query ChEMBL for InChI keys
                result = await self.biobtree.map_query_all_pages(
                    terms=chembl_ids,
                    mapfilter=">>chembl_molecule",
                    mode="full",
                    preserve_sources=True
                )

                for mapping in result.get('results', {}).get('results', []):
                    source = mapping.get('source', {})
                    chembl_id = source.get('identifier', '')
                    chembl_attr = source.get('chembl', {})
                    mol = chembl_attr.get('molecule', {})
                    inchi_key = mol.get('inchiKey', '')
                    if inchi_key:
                        inchi_map[chembl_id] = inchi_key

            # Step 2: Collect all InChI keys
            all_inchi_keys = []
            drug_by_inchi = {}

            for drug in drugs:
                inchi_key = drug.get('inchi_key') or inchi_map.get(drug.get('chembl_id', ''))
                if inchi_key:
                    all_inchi_keys.append(inchi_key)
                    drug_by_inchi[inchi_key] = drug

            if not all_inchi_keys:
                return self._create_result(
                    success=True,
                    data={
                        "enriched_drugs": [],
                        "drugs_queried": len(drugs),
                        "drugs_with_inchi": 0,
                        "note": "No InChI keys found for drugs"
                    },
                    metadata={"query": "pubchem_enrichment"}
                )

            # Step 3: Search PubChem by InChI keys and enrich with MeSH
            enriched_drugs = []
            pubchem_data = {}
            drugs_with_mesh = 0

            for inchi_key in all_inchi_keys:
                result = await self.biobtree.search(
                    terms=[inchi_key],
                    dataset='pubchem'
                )
                results = result.get('results', {}).get('results', [])

                if results:
                    pc = results[0]
                    pc_attr = pc.get('pubchem', {})
                    drug = drug_by_inchi.get(inchi_key, {})
                    pubchem_cid = pc.get('identifier', '')

                    # Extract drug-likeness properties
                    mw = pc_attr.get('molecular_weight')
                    hbd = pc_attr.get('hydrogen_bond_donors')
                    hba = pc_attr.get('hydrogen_bond_acceptors')
                    logp = pc_attr.get('xlogp')

                    # Compute Lipinski Rule of 5
                    lipinski = compute_lipinski_violations(mw, hbd, hba, logp)

                    enriched = {
                        # Core identifiers
                        'chembl_id': drug.get('chembl_id', ''),
                        'name': drug.get('name', ''),
                        'inchi_key': inchi_key,
                        'pubchem_cid': pubchem_cid,

                        # Classification
                        'fda_approved': pc_attr.get('is_fda_approved', False),
                        'compound_type': pc_attr.get('compound_type', ''),
                        'pharmacological_actions': pc_attr.get('pharmacological_actions', []),

                        # Names and synonyms
                        'title': pc_attr.get('title', ''),
                        'synonyms': pc_attr.get('synonyms', [])[:10],
                        'drug_names': pc_attr.get('drug_names', []),

                        # Flags
                        'has_patents': pc_attr.get('has_patents', False),
                        'has_literature': pc_attr.get('has_literature', False),

                        # Molecular properties
                        'molecular_weight': mw,
                        'molecular_formula': pc_attr.get('molecular_formula', ''),
                        'smiles': pc_attr.get('smiles', ''),

                        # Drug-likeness (Lipinski Rule of 5)
                        'xlogp': logp,
                        'hydrogen_bond_donors': hbd,
                        'hydrogen_bond_acceptors': hba,
                        'rotatable_bonds': pc_attr.get('rotatable_bonds'),
                        'tpsa': pc_attr.get('tpsa'),
                        'lipinski_violations': lipinski['violations'],
                        'drug_like': lipinski['drug_like'],

                        # External database IDs
                        'unii': pc_attr.get('unii', ''),  # FDA UNII
                        'dtxsid': pc_attr.get('dtxsid', ''),  # EPA toxicity
                        'nsc_ids': pc_attr.get('nsc_ids', []),  # NCI compound IDs

                        # MeSH terms from PubChem directly
                        'mesh_terms': pc_attr.get('mesh_terms', []),
                    }

                    # Step 4: Get MeSH data for drug class and better synonyms
                    if pubchem_cid:
                        mesh_data = await self._get_mesh_data(pubchem_cid)
                        if mesh_data:
                            drugs_with_mesh += 1
                            enriched['mesh_id'] = mesh_data.get('mesh_id', '')
                            enriched['mesh_name'] = mesh_data.get('mesh_name', '')
                            # Merge drug_class from MeSH if pharmacological_actions empty
                            if not enriched['pharmacological_actions']:
                                enriched['drug_class'] = mesh_data.get('drug_class', [])
                            else:
                                enriched['drug_class'] = enriched['pharmacological_actions']
                            enriched['trade_names'] = mesh_data.get('trade_names', [])[:10]
                            enriched['therapeutic_scope'] = mesh_data.get('therapeutic_scope', '')

                        # Get literature and patent counts (only for FDA drugs to save API calls)
                        if enriched['fda_approved']:
                            enriched['literature_count'] = await self._get_literature_count(pubchem_cid)
                            enriched['patent_count'] = await self._get_patent_count(pubchem_cid)

                    enriched_drugs.append(enriched)
                    pubchem_data[drug.get('chembl_id', inchi_key)] = enriched

            # Compute summary statistics
            fda_count = sum(1 for d in enriched_drugs if d.get('fda_approved'))
            drug_like_count = sum(1 for d in enriched_drugs if d.get('drug_like'))
            with_pharm_actions = sum(1 for d in enriched_drugs if d.get('pharmacological_actions'))

            return self._create_result(
                success=True,
                data={
                    "enriched_drugs": enriched_drugs,
                    "pubchem_by_chembl": pubchem_data,
                    "drugs_queried": len(drugs),
                    "drugs_with_inchi": len(all_inchi_keys),
                    "drugs_found_in_pubchem": len(enriched_drugs),
                    "drugs_with_mesh": drugs_with_mesh,
                    "fda_approved_count": fda_count,
                    "drug_like_count": drug_like_count,
                    "with_pharmacological_actions": with_pharm_actions,
                    "note": f"PubChem + MeSH enrichment for {disease} drugs"
                },
                drugs=enriched_drugs,
                metadata={
                    "query": "chembl_drugs >> inchi_key >> pubchem >> mesh",
                    "drugs_queried": len(drugs),
                    "drugs_enriched": len(enriched_drugs),
                    "drugs_with_mesh": drugs_with_mesh,
                    "fda_approved": fda_count,
                    "drug_like": drug_like_count,
                    "with_pharm_actions": with_pharm_actions
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "pubchem_enrichment"}
            )


class PubChemActivityPath(BasePath):
    """
    PATH 6b: Find FDA compounds via target bioactivity.

    Uses disease-associated genes/proteins to find FDA-approved compounds
    in PubChem that have bioactivity data against those targets.
    Path: genes >> ensembl >> uniprot >> pubchem_activity >> pubchem[fda]
    """

    @property
    def name(self) -> str:
        return "pubchem_activity"

    @property
    def description(self) -> str:
        return "FDA compounds from PubChem with bioactivity on disease targets"

    def _clean_gene_names(self, genes: List[str]) -> List[str]:
        """
        Clean gene names from GWAS format (e.g., 'GENE1 - GENE2' -> ['GENE1', 'GENE2']).
        """
        cleaned = []
        for gene in genes:
            if not gene:
                continue
            # Split on ' - ' for intergenic regions
            if ' - ' in gene:
                parts = gene.split(' - ')
                for part in parts:
                    # Clean up each part
                    part = part.strip()
                    # Skip non-gene entries (LINC, LOC, etc. are fine)
                    if part and not part.startswith('nan'):
                        cleaned.append(part)
            elif ', ' in gene:
                # Handle comma-separated genes
                parts = gene.split(', ')
                for part in parts:
                    part = part.strip()
                    if part and not part.startswith('nan'):
                        cleaned.append(part)
            else:
                gene = gene.strip()
                if gene and not gene.startswith('nan'):
                    cleaned.append(gene)

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for g in cleaned:
            if g not in seen:
                seen.add(g)
                unique.append(g)

        return unique

    async def _get_uniprot_ids(self, genes: List[str]) -> List[str]:
        """Convert gene names to Uniprot IDs via ensembl."""
        if not genes:
            return []

        uniprot_ids = []

        # Query genes to Uniprot via ensembl (genes can be gene names or Ensembl IDs)
        result = await self.biobtree.map_query_all_pages(
            terms=genes[:50],  # Limit to avoid timeout
            mapfilter=">>ensembl>>uniprot[uniprot.reviewed==true]",
            mode="lite"
        )

        # Lite mode returns targets directly in result['targets']
        for target in result.get('targets', []):
            uniprot_id = target.get('id', '')
            if uniprot_id and uniprot_id not in uniprot_ids:
                uniprot_ids.append(uniprot_id)

        return uniprot_ids

    async def execute(
        self,
        disease: str,
        genes: List[str] = None,
        uniprot_ids: List[str] = None,
        **kwargs
    ) -> PathResult:
        """
        Find FDA compounds with bioactivity on disease targets.

        Args:
            disease: Disease name
            genes: List of gene names (will be converted to Uniprot IDs)
            uniprot_ids: Direct Uniprot IDs (if available)

        Returns:
            PathResult with FDA PubChem compounds
        """
        try:
            # Get Uniprot IDs
            all_uniprot_ids = list(uniprot_ids) if uniprot_ids else []

            if genes:
                # Clean gene names (handle GWAS format)
                cleaned_genes = self._clean_gene_names(genes)

                if cleaned_genes:
                    # Convert genes to Uniprot IDs
                    gene_uniprots = await self._get_uniprot_ids(cleaned_genes)
                    all_uniprot_ids.extend(gene_uniprots)

            # Deduplicate
            all_uniprot_ids = list(set(all_uniprot_ids))

            if not all_uniprot_ids:
                return self._create_result(
                    success=True,
                    data={
                        "compounds": [],
                        "targets_queried": 0,
                        "note": "No Uniprot IDs available"
                    },
                    metadata={"query": "uniprot >> pubchem_activity >> pubchem"}
                )

            # Query PubChem via bioactivity
            result = await self.biobtree.map_query_all_pages(
                terms=all_uniprot_ids[:30],  # Limit to avoid timeout
                mapfilter=">>uniprot>>pubchem_activity>>pubchem[pubchem.is_fda_approved==true]",
                mode="full",
                preserve_sources=True
            )

            # Extract compounds grouped by target
            compounds_by_target = {}
            all_compounds = {}

            for mapping in result.get('results', {}).get('results', []):
                source = mapping.get('source', {})
                target_id = source.get('identifier', '')

                for target in mapping.get('targets', []):
                    cid = target.get('identifier', '')
                    if not cid:
                        continue

                    pc = target.get('pubchem', {})

                    if cid not in all_compounds:
                        # Extract drug-likeness properties
                        mw = pc.get('molecular_weight')
                        hbd = pc.get('hydrogen_bond_donors')
                        hba = pc.get('hydrogen_bond_acceptors')
                        logp = pc.get('xlogp')
                        lipinski = compute_lipinski_violations(mw, hbd, hba, logp)

                        all_compounds[cid] = {
                            'pubchem_cid': cid,
                            'title': pc.get('title', ''),
                            'synonyms': pc.get('synonyms', [])[:5],
                            'fda_approved': pc.get('is_fda_approved', False),
                            'compound_type': pc.get('compound_type', ''),
                            'pharmacological_actions': pc.get('pharmacological_actions', []),
                            'smiles': pc.get('smiles', ''),
                            'molecular_weight': mw,
                            'molecular_formula': pc.get('molecular_formula', ''),
                            'xlogp': logp,
                            'hydrogen_bond_donors': hbd,
                            'hydrogen_bond_acceptors': hba,
                            'tpsa': pc.get('tpsa'),
                            'lipinski_violations': lipinski['violations'],
                            'drug_like': lipinski['drug_like'],
                            'mesh_terms': pc.get('mesh_terms', []),
                            'unii': pc.get('unii', ''),
                            'targets': []
                        }

                    if target_id and target_id not in all_compounds[cid]['targets']:
                        all_compounds[cid]['targets'].append(target_id)

                    # Track by target
                    if target_id not in compounds_by_target:
                        compounds_by_target[target_id] = []
                    if cid not in [c['pubchem_cid'] for c in compounds_by_target[target_id]]:
                        compounds_by_target[target_id].append(all_compounds[cid])

            compounds_list = list(all_compounds.values())

            return self._create_result(
                success=True,
                data={
                    "compounds": compounds_list,
                    "compounds_by_target": compounds_by_target,
                    "targets_queried": len(all_uniprot_ids),
                    "targets_with_compounds": len(compounds_by_target),
                    "total_compounds": len(compounds_list),
                    "note": f"FDA PubChem compounds with bioactivity on {disease} targets"
                },
                drugs=compounds_list,
                genes=list(compounds_by_target.keys()),
                metadata={
                    "query": "uniprot >> pubchem_activity >> pubchem[fda]",
                    "targets_queried": len(all_uniprot_ids),
                    "compounds_found": len(compounds_list)
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "uniprot >> pubchem_activity >> pubchem"}
            )


# Keep old class name for backward compatibility
class PubChemPath(PubChemEnrichmentPath):
    """Alias for PubChemEnrichmentPath for backward compatibility."""
    pass
