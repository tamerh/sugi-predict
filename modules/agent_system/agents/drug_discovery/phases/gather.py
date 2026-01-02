"""Phase 2: Data Gathering.

Orchestrates parallel execution of all data gathering paths.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from ..paths import (
    BasePath,
    PathResult,
    DirectIndicationsPath,
    GWASPath,
    ClinVarPath,
    PubChemEnrichmentPath,
    PubChemActivityPath,
    ReactomePath,
    ClinicalTrialsPath,
    PatentsPath,
    BindingDBPath,
    AntibodyPath,
)


@dataclass
class GatherOptions:
    """Options for data gathering phase."""
    min_indication_phase: int = 3
    include_gwas: bool = True
    include_clinvar: bool = True
    include_reactome: bool = True
    include_uniprot: bool = True
    include_pubchem: bool = True
    include_clinical_trials: bool = True
    include_patents: bool = False
    include_bindingdb: bool = True
    include_antibodies: bool = True
    include_similar_proteins: bool = False
    include_similar_compounds: bool = False
    max_genes: int = 50
    max_drugs_for_enrichment: int = 50


@dataclass
class GatherResult:
    """Result from the data gathering phase."""
    disease: str
    direct_indications: PathResult
    gwas: Optional[PathResult] = None
    clinvar: Optional[PathResult] = None
    pubchem_enrichment: Optional[PathResult] = None  # PATH 6a: ChEMBL drugs enriched with PubChem
    pubchem_activity: Optional[PathResult] = None    # PATH 6b: FDA compounds via target activity
    reactome: Optional[PathResult] = None
    clinical_trials: Optional[PathResult] = None
    patents: Optional[PathResult] = None
    bindingdb: Optional[PathResult] = None
    antibodies: Optional[PathResult] = None
    all_genes: List[str] = field(default_factory=list)
    all_drugs: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for response building."""
        result = {
            "disease": self.disease,
            "direct_indications": {
                "drugs": self.direct_indications.drugs,
                "count": len(self.direct_indications.drugs),
                "min_phase_filter": self.direct_indications.metadata.get("min_phase_filter", 3),
                "note": f"Drugs with Phase 3+ specifically for {self.disease}"
            }
        }

        # Add GWAS results
        if self.gwas and self.gwas.success:
            result["gwas_targets"] = self.gwas.data
            result["gwas_targets"]["note"] = "Drugs targeting genes genetically associated via GWAS"

        # Add ClinVar results
        if self.clinvar and self.clinvar.success:
            result["clinvar_targets"] = self.clinvar.data
            result["clinvar_targets"]["note"] = "Drugs targeting genes with disease-associated variants (ClinVar)"

        # Add PubChem enrichment results (PATH 6a)
        if self.pubchem_enrichment and self.pubchem_enrichment.success:
            result["pubchem_enrichment"] = self.pubchem_enrichment.data
            result["pubchem_enrichment"]["note"] = "ChEMBL drugs enriched with PubChem data (FDA status, synonyms)"

        # Add PubChem activity results (PATH 6b)
        if self.pubchem_activity and self.pubchem_activity.success:
            result["pubchem_activity"] = self.pubchem_activity.data
            result["pubchem_activity"]["note"] = "FDA compounds with bioactivity on disease-associated targets"

        # Add Reactome results
        if self.reactome and self.reactome.success:
            result["reactome_pathways"] = self.reactome.data

        # Add Clinical Trials results
        if self.clinical_trials and self.clinical_trials.success:
            result["clinical_trials"] = self.clinical_trials.data

        # Add Patents results
        if self.patents and self.patents.success:
            result["patents"] = self.patents.data

        # Add BindingDB results
        if self.bindingdb and self.bindingdb.success:
            result["bindingdb"] = self.bindingdb.data

        # Add Antibodies results
        if self.antibodies and self.antibodies.success:
            result["antibodies"] = self.antibodies.data

        # Add summary
        result["summary"] = self._build_summary()

        return result

    def _build_summary(self) -> Dict[str, Any]:
        """Build summary statistics."""
        summary = {
            "direct_indication_drugs": len(self.direct_indications.drugs),
            "total_genes": len(self.all_genes),
            "total_drugs": len(self.all_drugs),
        }

        if self.gwas and self.gwas.success:
            summary["gwas_genes"] = self.gwas.data.get("gene_count", 0)
            summary["gwas_drugs"] = self.gwas.data.get("drug_count", 0)
            summary["gwas_studies"] = self.gwas.data.get("study_count", 0)

        if self.clinvar and self.clinvar.success:
            summary["clinvar_genes"] = self.clinvar.data.get("gene_count", 0)
            summary["clinvar_drugs"] = self.clinvar.data.get("drug_count", 0)

        if self.pubchem_enrichment and self.pubchem_enrichment.success:
            summary["pubchem_enriched_drugs"] = self.pubchem_enrichment.data.get("drugs_found_in_pubchem", 0)
            summary["pubchem_fda_approved"] = self.pubchem_enrichment.data.get("fda_approved_count", 0)

        if self.pubchem_activity and self.pubchem_activity.success:
            summary["pubchem_fda_compounds"] = self.pubchem_activity.data.get("total_compounds", 0)
            summary["pubchem_targets_with_compounds"] = self.pubchem_activity.data.get("targets_with_compounds", 0)

        if self.reactome and self.reactome.success:
            summary["reactome_pathways"] = self.reactome.data.get("pathway_count", 0)

        if self.clinical_trials and self.clinical_trials.success:
            summary["clinical_trials"] = self.clinical_trials.data.get("count", 0)
            summary["recruiting_trials"] = self.clinical_trials.data.get("recruiting_count", 0)

        if self.patents and self.patents.success:
            summary["patents"] = self.patents.data.get("count", 0)
            summary["molecules_with_patents"] = self.patents.data.get("molecules_with_patents", 0)

        if self.bindingdb and self.bindingdb.success:
            summary["drugs_with_binding_data"] = self.bindingdb.data.get("drugs_with_data", 0)

        if self.antibodies and self.antibodies.success:
            summary["therapeutic_antibodies"] = self.antibodies.data.get("count", 0)

        return summary


class GatherPhase:
    """
    Phase 2: Gather data from all paths in parallel.

    Orchestrates the execution of multiple data gathering paths:
    - PATH 1: Direct indications (always runs first)
    - PATH 2: GWAS (parallel with PATH 3)
    - PATH 3: ClinVar (parallel with PATH 2)
    - PATH 6a: PubChem enrichment (after drugs collected - enriches via InChI key)
    - PATH 6b: PubChem activity (after genes collected - FDA compounds via target bioactivity)
    - PATH 7: Reactome (after genes collected)
    - PATH 11: Clinical Trials (parallel with PATH 1)
    - PATH 12: Patents (after drugs collected)
    - PATH 13: BindingDB (after drugs collected)
    - PATH 14: Therapeutic Antibodies (parallel with PATH 1)
    """

    def __init__(self, biobtree, qdrant=None):
        """
        Initialize GatherPhase with clients.

        Args:
            biobtree: BioBTree client for database queries
            qdrant: Optional Qdrant client for vector search
        """
        self.biobtree = biobtree
        self.qdrant = qdrant

    async def execute(self, disease: str, options: GatherOptions = None) -> GatherResult:
        """
        Run all enabled paths in parallel where possible.

        Execution order:
        1. Phase 1: Direct indications + Clinical trials + GWAS + ClinVar (parallel)
        2. Phase 2: PubChem + Reactome using collected genes (parallel)
        3. Phase 3: Patents using collected drugs (if enabled)

        Args:
            disease: Disease name or ID to query
            options: Gather options (defaults to standard options)

        Returns:
            GatherResult with data from all paths
        """
        if options is None:
            options = GatherOptions()

        # ========================================
        # Phase 1: Run initial queries in parallel
        # ========================================
        phase1_paths = []
        phase1_labels = []

        # Direct indications (always runs)
        direct_path = DirectIndicationsPath(self.biobtree)
        phase1_paths.append(direct_path.execute(disease, min_phase=options.min_indication_phase))
        phase1_labels.append("direct_indications")

        # Clinical trials
        if options.include_clinical_trials:
            clinical_path = ClinicalTrialsPath(self.biobtree)
            phase1_paths.append(clinical_path.execute(disease))
            phase1_labels.append("clinical_trials")

        # GWAS
        if options.include_gwas:
            gwas_path = GWASPath(self.biobtree)
            phase1_paths.append(gwas_path.execute(disease, max_genes=options.max_genes))
            phase1_labels.append("gwas")

        # ClinVar
        if options.include_clinvar:
            clinvar_path = ClinVarPath(self.biobtree)
            phase1_paths.append(clinvar_path.execute(disease, max_genes=options.max_genes))
            phase1_labels.append("clinvar")

        # Therapeutic Antibodies
        if options.include_antibodies:
            antibody_path = AntibodyPath(self.biobtree)
            phase1_paths.append(antibody_path.execute(disease))
            phase1_labels.append("antibodies")

        # Execute phase 1 in parallel
        phase1_results = await asyncio.gather(*phase1_paths, return_exceptions=True)

        # Map results by label
        results_by_label = {}
        for label, result in zip(phase1_labels, phase1_results):
            if isinstance(result, Exception):
                results_by_label[label] = PathResult(
                    path_name=label,
                    success=False,
                    data={},
                    error=str(result)
                )
            else:
                results_by_label[label] = result

        # Extract direct indications result
        direct_result = results_by_label.get("direct_indications")

        # Collect all genes from GWAS and ClinVar
        all_genes = set()
        gwas_result = results_by_label.get("gwas")
        clinvar_result = results_by_label.get("clinvar")

        if gwas_result and gwas_result.success:
            all_genes.update(gwas_result.genes)
        if clinvar_result and clinvar_result.success:
            all_genes.update(clinvar_result.genes)

        all_genes_list = sorted(list(all_genes))[:options.max_genes]

        # ========================================
        # Phase 2: Run gene-dependent queries
        # ========================================
        phase2_paths = []
        phase2_labels = []

        # PubChem Activity PATH 6b (needs genes - finds FDA compounds via target bioactivity)
        if options.include_pubchem and all_genes_list:
            pubchem_activity_path = PubChemActivityPath(self.biobtree)
            phase2_paths.append(pubchem_activity_path.execute(disease, genes=all_genes_list))
            phase2_labels.append("pubchem_activity")

        # Reactome (needs genes)
        if all_genes_list:
            reactome_path = ReactomePath(self.biobtree)
            phase2_paths.append(reactome_path.execute(disease, genes=all_genes_list))
            phase2_labels.append("reactome")

        pubchem_activity_result = None
        reactome_result = None

        if phase2_paths:
            phase2_results = await asyncio.gather(*phase2_paths, return_exceptions=True)
            for label, result in zip(phase2_labels, phase2_results):
                if isinstance(result, Exception):
                    continue
                if label == "pubchem_activity":
                    pubchem_activity_result = result
                elif label == "reactome":
                    reactome_result = result

        # ========================================
        # Phase 3: Run drug-dependent queries (in parallel)
        # ========================================
        phase3_paths = []
        phase3_labels = []

        # PubChem Enrichment PATH 6a (needs drugs - enriches ChEMBL drugs with PubChem data)
        if options.include_pubchem and direct_result and direct_result.drugs:
            pubchem_enrichment_path = PubChemEnrichmentPath(self.biobtree)
            phase3_paths.append(pubchem_enrichment_path.execute(
                disease,
                drugs=direct_result.drugs[:options.max_drugs_for_enrichment]
            ))
            phase3_labels.append("pubchem_enrichment")

        # Patents (needs drugs)
        if options.include_patents and direct_result and direct_result.drugs:
            patents_path = PatentsPath(self.biobtree)
            phase3_paths.append(patents_path.execute(
                disease,
                drugs=direct_result.drugs[:options.max_drugs_for_enrichment]
            ))
            phase3_labels.append("patents")

        # BindingDB (needs drugs)
        if options.include_bindingdb and direct_result and direct_result.drugs:
            bindingdb_path = BindingDBPath(self.biobtree)
            phase3_paths.append(bindingdb_path.execute(
                disease,
                drugs=direct_result.drugs[:options.max_drugs_for_enrichment]
            ))
            phase3_labels.append("bindingdb")

        pubchem_enrichment_result = None
        patents_result = None
        bindingdb_result = None

        if phase3_paths:
            phase3_results = await asyncio.gather(*phase3_paths, return_exceptions=True)
            for label, result in zip(phase3_labels, phase3_results):
                if isinstance(result, Exception):
                    continue
                if label == "pubchem_enrichment":
                    pubchem_enrichment_result = result
                elif label == "patents":
                    patents_result = result
                elif label == "bindingdb":
                    bindingdb_result = result

        # ========================================
        # Collect all unique drugs
        # ========================================
        all_drugs = []
        seen_drug_ids = set()

        # From direct indications
        if direct_result and direct_result.drugs:
            for drug in direct_result.drugs:
                if drug["id"] not in seen_drug_ids:
                    all_drugs.append(drug)
                    seen_drug_ids.add(drug["id"])

        # From GWAS
        if gwas_result and gwas_result.drugs:
            for drug in gwas_result.drugs:
                if drug["id"] not in seen_drug_ids:
                    all_drugs.append(drug)
                    seen_drug_ids.add(drug["id"])

        # From ClinVar
        if clinvar_result and clinvar_result.drugs:
            for drug in clinvar_result.drugs:
                if drug["id"] not in seen_drug_ids:
                    all_drugs.append(drug)
                    seen_drug_ids.add(drug["id"])

        # From PubChem Activity (uses PubChem CID as key)
        if pubchem_activity_result and pubchem_activity_result.drugs:
            for drug in pubchem_activity_result.drugs:
                drug_key = drug.get("pubchem_cid") or drug.get("cid") or drug.get("id", "")
                if drug_key and drug_key not in seen_drug_ids:
                    all_drugs.append(drug)
                    seen_drug_ids.add(drug_key)

        # From PubChem Enrichment (adds FDA status to ChEMBL drugs, uses ChEMBL ID as key)
        if pubchem_enrichment_result and pubchem_enrichment_result.drugs:
            for drug in pubchem_enrichment_result.drugs:
                drug_key = drug.get("chembl_id") or drug.get("id", "")
                # Note: These drugs are already in all_drugs from direct_indications,
                # but we can update them with PubChem enrichment data
                if drug_key and drug_key not in seen_drug_ids:
                    all_drugs.append(drug)
                    seen_drug_ids.add(drug_key)

        # ========================================
        # Build result
        # ========================================
        return GatherResult(
            disease=disease,
            direct_indications=direct_result,
            gwas=gwas_result,
            clinvar=clinvar_result,
            pubchem_enrichment=pubchem_enrichment_result,
            pubchem_activity=pubchem_activity_result,
            reactome=reactome_result,
            clinical_trials=results_by_label.get("clinical_trials"),
            patents=patents_result,
            bindingdb=bindingdb_result,
            antibodies=results_by_label.get("antibodies"),
            all_genes=all_genes_list,
            all_drugs=all_drugs,
            metadata={
                "options": {
                    "min_indication_phase": options.min_indication_phase,
                    "include_gwas": options.include_gwas,
                    "include_clinvar": options.include_clinvar,
                    "include_pubchem": options.include_pubchem,
                    "include_clinical_trials": options.include_clinical_trials,
                    "include_patents": options.include_patents,
                    "include_bindingdb": options.include_bindingdb,
                    "include_antibodies": options.include_antibodies,
                }
            }
        )
