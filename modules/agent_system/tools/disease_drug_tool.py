"""Specialized Disease Drug Discovery Tool.

This tool runs multiple BioBTree queries internally and returns
consolidated, filtered results for disease-to-drug queries.
"""

import asyncio
from typing import Optional, List, Dict, Any

from .base import Tool, ToolResult
from ..llm.base import ToolDefinition
from ..integrations.biobtree_client import BioBTreeClient


class DiseaseDrugDiscoveryTool(Tool):
    """
    Specialized tool for comprehensive disease-to-drug discovery.

    Runs multiple query paths internally:
    - PATH 1: Direct ChEMBL indications (disease >> efo >> chembl_molecule)
    - PATH 2: GWAS genetic associations (disease >> efo >> gwas >> ensembl)
    - PATH 3: ClinVar variants (disease >> mondo >> clinvar >> ensembl)
    - PATH 4: Reactome pathways (disease >> efo >> reactome >> ensembl)
    - PATH 5: UniProt disease associations (disease >> efo >> uniprot)

    Returns consolidated results with proper indication-phase filtering.
    """

    def __init__(self, client: BioBTreeClient):
        """
        Initialize Disease Drug Discovery tool.

        Args:
            client: BioBTree client instance
        """
        super().__init__(
            name="disease_drug_discovery",
            description=(
                "Find drugs for a disease using multiple evidence paths. "
                "Returns: (1) Drugs with direct disease indications (filtered by approval phase), "
                "(2) Drugs targeting genes from GWAS, ClinVar variants, Reactome pathways, and UniProt. "
                "Use this for questions like 'What drugs are available for glioblastoma?'"
            )
        )
        self.client = client

    def get_definition(self) -> ToolDefinition:
        """Get tool definition for LLM function calling."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "disease": {
                        "type": "string",
                        "description": (
                            "Disease name to search for (e.g., 'glioblastoma', 'type 2 diabetes', "
                            "'breast cancer'). Can also use disease IDs like 'EFO:0000519'."
                        )
                    },
                    "min_indication_phase": {
                        "type": "integer",
                        "description": (
                            "Minimum clinical phase for direct indications (default: 3). "
                            "Phase 4 = Approved, Phase 3 = Late-stage trials, Phase 2 = Mid-stage, "
                            "Phase 1 = Early trials. Set to 0 to include all."
                        ),
                        "default": 3
                    },
                    "include_gwas": {
                        "type": "boolean",
                        "description": (
                            "Include drugs targeting GWAS-associated genes (default: true)."
                        ),
                        "default": True
                    },
                    "include_clinvar": {
                        "type": "boolean",
                        "description": (
                            "Include drugs targeting genes with disease-associated variants from ClinVar (default: true)."
                        ),
                        "default": True
                    },
                    "include_reactome": {
                        "type": "boolean",
                        "description": (
                            "Include drugs targeting genes in disease-related Reactome pathways (default: true)."
                        ),
                        "default": True
                    },
                    "include_uniprot": {
                        "type": "boolean",
                        "description": (
                            "Include drugs targeting proteins annotated with the disease in UniProt (default: true)."
                        ),
                        "default": True
                    }
                },
                "required": ["disease"]
            }
        )

    async def _query_direct_indications(self, disease: str) -> Dict[str, Any]:
        """
        PATH 1: Query drugs with direct disease indications.

        Args:
            disease: Disease name or ID

        Returns:
            Dict with drugs and their indication-level phases
        """
        try:
            # Query: disease >> efo >> chembl_molecule (full mode for indication data)
            mapfilter = ">>efo>>chembl_molecule"
            result = await self.client.map_query(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            return {
                "success": True,
                "data": result,
                "query": f"{disease} >> efo >> chembl_molecule"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "query": f"{disease} >> efo >> chembl_molecule"
            }

    async def _query_gwas_genes(self, disease: str) -> Dict[str, Any]:
        """
        GWAS Step 1: Get genes associated with disease via GWAS.

        Args:
            disease: Disease name or ID

        Returns:
            Dict with GWAS-associated genes
        """
        try:
            # Query: disease >> efo >> gwas >> ensembl (get genes)
            mapfilter = ">>efo>>gwas>>ensembl[ensembl.genome==\"homo_sapiens\"]"
            result = await self.client.map_query(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            return {
                "success": True,
                "data": result,
                "query": f"{disease} >> efo >> gwas >> ensembl"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "query": f"{disease} >> efo >> gwas >> ensembl"
            }

    async def _query_clinvar_genes(self, disease: str) -> Dict[str, Any]:
        """
        PATH 3: Get genes with disease-associated variants from ClinVar.

        Uses MONDO disease ontology for ClinVar linkage.

        Args:
            disease: Disease name or ID

        Returns:
            Dict with ClinVar-associated genes
        """
        try:
            # Query: disease >> mondo >> clinvar >> ensembl (via MONDO ontology)
            mapfilter = ">>mondo>>clinvar>>ensembl[ensembl.genome==\"homo_sapiens\"]"
            result = await self.client.map_query(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            return {
                "success": True,
                "data": result,
                "source": "clinvar",
                "query": f"{disease} >> mondo >> clinvar >> ensembl"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "source": "clinvar",
                "query": f"{disease} >> mondo >> clinvar >> ensembl"
            }

    async def _query_reactome_genes(self, disease: str) -> Dict[str, Any]:
        """
        PATH 4: Get genes from disease-related Reactome pathways.

        Args:
            disease: Disease name or ID

        Returns:
            Dict with Reactome pathway-associated genes
        """
        try:
            # Query: disease >> efo >> reactome >> ensembl (get genes in pathways)
            mapfilter = ">>efo>>reactome>>ensembl[ensembl.genome==\"homo_sapiens\"]"
            result = await self.client.map_query(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            return {
                "success": True,
                "data": result,
                "source": "reactome",
                "query": f"{disease} >> efo >> reactome >> ensembl"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "source": "reactome",
                "query": f"{disease} >> efo >> reactome >> ensembl"
            }

    async def _query_uniprot_proteins(self, disease: str) -> Dict[str, Any]:
        """
        PATH 5: Get proteins directly annotated with disease from UniProt.

        Args:
            disease: Disease name or ID

        Returns:
            Dict with UniProt disease-associated proteins
        """
        try:
            # Query: disease >> efo >> uniprot (get proteins with disease annotation)
            mapfilter = ">>efo>>uniprot[uniprot.reviewed==true]"
            result = await self.client.map_query(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            return {
                "success": True,
                "data": result,
                "source": "uniprot",
                "query": f"{disease} >> efo >> uniprot"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "source": "uniprot",
                "query": f"{disease} >> efo >> uniprot"
            }

    async def _query_genes_to_drugs(self, genes: List[str], source: str = "unknown") -> Dict[str, Any]:
        """
        Map genes to drugs via ChEMBL.

        Args:
            genes: List of gene symbols
            source: Source of genes (gwas, clinvar, reactome)

        Returns:
            Dict with drug mappings for genes
        """
        if not genes:
            return {"success": True, "data": {"results": {"results": []}}, "genes": [], "source": source}

        try:
            # Query: genes >> ensembl >> uniprot >> ... >> chembl_molecule
            mapfilter = (
                ">>ensembl[ensembl.genome==\"homo_sapiens\"]"
                ">>uniprot[uniprot.reviewed==true]"
                ">>chembl_target_component>>chembl_target"
                ">>chembl_assay>>chembl_activity>>chembl_molecule"
            )
            result = await self.client.map_query(
                terms=genes,
                mapfilter=mapfilter,
                mode="full"
            )

            return {
                "success": True,
                "data": result,
                "genes": genes,
                "source": source,
                "query": f"{','.join(genes[:5])}... >> ensembl >> ... >> chembl_molecule"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "genes": genes,
                "source": source
            }

    async def _query_proteins_to_drugs(self, proteins: List[str]) -> Dict[str, Any]:
        """
        Map UniProt proteins to drugs via ChEMBL.

        Args:
            proteins: List of UniProt accession IDs

        Returns:
            Dict with drug mappings for proteins
        """
        if not proteins:
            return {"success": True, "data": {"results": {"results": []}}, "proteins": [], "source": "uniprot"}

        try:
            # Query: proteins >> uniprot >> chembl_target_component >> ... >> chembl_molecule
            mapfilter = (
                ">>uniprot[uniprot.reviewed==true]"
                ">>chembl_target_component>>chembl_target"
                ">>chembl_assay>>chembl_activity>>chembl_molecule"
            )
            result = await self.client.map_query(
                terms=proteins,
                mapfilter=mapfilter,
                mode="full"
            )

            return {
                "success": True,
                "data": result,
                "proteins": proteins,
                "source": "uniprot",
                "query": f"{','.join(proteins[:5])}... >> uniprot >> ... >> chembl_molecule"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "proteins": proteins,
                "source": "uniprot"
            }

    def _extract_genes_from_result(self, result: Dict, max_genes: int = 50) -> List[str]:
        """
        Extract unique gene symbols from query results (GWAS, ClinVar, Reactome).

        Args:
            result: BioBTree query result with ensembl targets
            max_genes: Maximum number of genes to return

        Returns:
            List of unique gene symbols
        """
        genes = set()

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            for target in r.get("targets", []):
                # Get gene symbol from ensembl data
                ensembl_data = target.get("ensembl", {})
                if not ensembl_data:
                    attrs = target.get("Attributes", {})
                    ensembl_data = attrs.get("Ensembl", {}) or attrs.get("ensembl", {})

                # Try to get gene symbol
                gene_symbol = None
                if ensembl_data:
                    gene_symbol = ensembl_data.get("symbol") or ensembl_data.get("name")

                # Fallback to identifier
                if not gene_symbol:
                    identifier = target.get("identifier", "")
                    # If it looks like a gene symbol (short, uppercase)
                    if identifier and len(identifier) < 15 and not identifier.startswith("ENSG"):
                        gene_symbol = identifier

                if gene_symbol:
                    genes.add(gene_symbol)

        return list(genes)[:max_genes]

    def _extract_proteins_from_result(self, result: Dict, max_proteins: int = 50) -> List[Dict]:
        """
        Extract unique proteins from UniProt query results.

        Args:
            result: BioBTree query result with UniProt targets
            max_proteins: Maximum number of proteins to return

        Returns:
            List of dicts with protein info (accession, gene_name)
        """
        proteins = {}  # Use dict to track by accession

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            for target in r.get("targets", []):
                accession = target.get("identifier", "")
                if not accession or accession in proteins:
                    continue

                # Get UniProt data for gene name
                uniprot_data = target.get("uniprot", {})
                if not uniprot_data:
                    attrs = target.get("Attributes", {})
                    uniprot_data = attrs.get("Uniprot", {}) or attrs.get("uniprot", {})

                gene_name = None
                if uniprot_data:
                    gene_name = uniprot_data.get("geneName") or uniprot_data.get("gene_name")

                proteins[accession] = {
                    "accession": accession,
                    "gene_name": gene_name
                }

                if len(proteins) >= max_proteins:
                    break

        return list(proteins.values())

    def _extract_drugs_from_indication_results(
        self,
        result: Dict,
        disease: str,
        min_phase: int
    ) -> List[Dict]:
        """
        Extract and filter drugs from direct indication query results.

        Filters by indication-specific phase, not drug-level phase.

        Args:
            result: BioBTree query result
            disease: Disease name for matching indications
            min_phase: Minimum indication phase to include

        Returns:
            List of drug dicts with indication-specific info
        """
        drugs = []
        seen_ids = set()

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        disease_lower = disease.lower()

        for r in results_list:
            for target in r.get("targets", []):
                drug_id = target.get("identifier", "")
                if drug_id in seen_ids:
                    continue

                # Get ChEMBL molecule data
                chembl_data = target.get("chembl", {})
                if not chembl_data:
                    attrs = target.get("Attributes", {})
                    chembl_data = attrs.get("Chembl", {}) or attrs.get("chembl", {})

                drug_info = chembl_data.get("molecule", {})
                if not drug_info:
                    continue

                # Get drug name
                drug_name = None
                alt_names = drug_info.get("altNames", [])
                if alt_names and isinstance(alt_names, list):
                    for name in alt_names:
                        if name and len(name) > 2:
                            drug_name = name
                            break

                # Get indications and find disease-specific phase
                indications = drug_info.get("indications", [])
                indication_phase = None
                indication_name = None

                for ind in indications:
                    ind_name = ind.get("efoName", "")
                    ind_phase = ind.get("highestDevelopmentPhase")

                    # Check if this indication matches the disease
                    if disease_lower in ind_name.lower():
                        indication_phase = ind_phase
                        indication_name = ind_name
                        break

                # Filter by indication-specific phase
                if indication_phase is None or indication_phase < min_phase:
                    continue

                # Get mechanism
                mechanism = drug_info.get("mechanism", {})
                mechanism_desc = ""
                if mechanism:
                    mechanism_desc = mechanism.get("desc", "") or mechanism.get("action", "")

                drugs.append({
                    "id": drug_id,
                    "name": drug_name or drug_id,
                    "indication_phase": indication_phase,
                    "indication_name": indication_name,
                    "drug_phase": drug_info.get("highestDevelopmentPhase"),
                    "mechanism": mechanism_desc,
                    "type": drug_info.get("type", ""),
                    "evidence": "direct_indication"
                })
                seen_ids.add(drug_id)

        # Sort by indication phase (highest first)
        drugs.sort(key=lambda d: -(d.get("indication_phase") or 0))

        return drugs

    def _extract_drugs_from_gene_results(
        self,
        result: Dict,
        evidence_type: str = "gene_association"
    ) -> Dict[str, List[Dict]]:
        """
        Extract drugs grouped by target gene from gene-to-drug query results.

        Args:
            result: BioBTree query result from genes >> ... >> chembl_molecule
            evidence_type: Type of evidence (gwas, clinvar, reactome, uniprot)

        Returns:
            Dict mapping gene symbols to their drug lists
        """
        drugs_by_gene = {}

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            # Get gene symbol from source (this is the gene we queried)
            source = r.get("source", {})
            gene_symbol = source.get("keyword") or source.get("identifier", "Unknown")

            # Clean up gene symbol (remove ENSG prefix if present)
            if gene_symbol.startswith("ENSG"):
                # Try to get from attributes
                ensembl_data = source.get("ensembl", {})
                if not ensembl_data:
                    attrs = source.get("Attributes", {})
                    ensembl_data = attrs.get("Ensembl", {}) or attrs.get("ensembl", {})
                if ensembl_data:
                    gene_symbol = ensembl_data.get("symbol") or gene_symbol

            for target in r.get("targets", []):
                drug_id = target.get("identifier", "")

                # Get ChEMBL molecule data
                chembl_data = target.get("chembl", {})
                if not chembl_data:
                    attrs = target.get("Attributes", {})
                    chembl_data = attrs.get("Chembl", {}) or attrs.get("chembl", {})

                drug_info = chembl_data.get("molecule", {})

                # Get drug name
                drug_name = None
                if drug_info:
                    alt_names = drug_info.get("altNames", [])
                    if alt_names and isinstance(alt_names, list):
                        for name in alt_names:
                            if name and len(name) > 2:
                                drug_name = name
                                break

                drug_phase = drug_info.get("highestDevelopmentPhase") if drug_info else None

                # Get mechanism
                mechanism = ""
                if drug_info:
                    mech = drug_info.get("mechanism", {})
                    if mech:
                        mechanism = mech.get("desc", "") or mech.get("action", "")

                drug_entry = {
                    "id": drug_id,
                    "name": drug_name or drug_id,
                    "drug_phase": drug_phase,
                    "mechanism": mechanism,
                    "evidence": evidence_type
                }

                if gene_symbol not in drugs_by_gene:
                    drugs_by_gene[gene_symbol] = []

                # Avoid duplicates within same gene
                if drug_id not in [d["id"] for d in drugs_by_gene[gene_symbol]]:
                    drugs_by_gene[gene_symbol].append(drug_entry)

        # Sort drugs within each gene by phase (highest first)
        for gene in drugs_by_gene:
            drugs_by_gene[gene].sort(
                key=lambda d: -(d.get("drug_phase") or 0)
            )

        return drugs_by_gene

    async def execute(
        self,
        disease: str,
        min_indication_phase: int = 3,
        include_gwas: bool = True,
        include_clinvar: bool = True,
        include_reactome: bool = True,
        include_uniprot: bool = True,
        **kwargs
    ) -> ToolResult:
        """
        Execute comprehensive disease drug discovery using multiple evidence paths.

        Uses two-step approach for gene-based sources:
        1. Get genes/proteins from each source (GWAS, ClinVar, Reactome, UniProt)
        2. Map those genes/proteins to drugs via ChEMBL

        Args:
            disease: Disease name or ID
            min_indication_phase: Minimum phase for direct indications (default: 3)
            include_gwas: Include GWAS-based drug targets (default: True)
            include_clinvar: Include ClinVar variant-based targets (default: True)
            include_reactome: Include Reactome pathway-based targets (default: True)
            include_uniprot: Include UniProt disease-associated proteins (default: True)
            **kwargs: Additional parameters

        Returns:
            Tool result with consolidated drug discovery results from all paths
        """
        try:
            # ========================================
            # PHASE 1: Run all initial queries in parallel
            # ========================================
            phase1_tasks = [self._query_direct_indications(disease)]
            task_labels = ["direct_indications"]

            if include_gwas:
                phase1_tasks.append(self._query_gwas_genes(disease))
                task_labels.append("gwas")
            if include_clinvar:
                phase1_tasks.append(self._query_clinvar_genes(disease))
                task_labels.append("clinvar")
            if include_reactome:
                phase1_tasks.append(self._query_reactome_genes(disease))
                task_labels.append("reactome")
            if include_uniprot:
                phase1_tasks.append(self._query_uniprot_proteins(disease))
                task_labels.append("uniprot")

            phase1_results = await asyncio.gather(*phase1_tasks)

            # Map results by label
            results_by_source = dict(zip(task_labels, phase1_results))

            # ========================================
            # Process direct indication results
            # ========================================
            direct_drugs = []
            indication_result = results_by_source.get("direct_indications", {})
            if indication_result.get("success"):
                direct_drugs = self._extract_drugs_from_indication_results(
                    indication_result,
                    disease,
                    min_indication_phase
                )

            # ========================================
            # PHASE 2: Extract genes/proteins and map to drugs
            # ========================================
            gene_sources = {}  # Store genes by source
            protein_sources = {}  # Store proteins by source

            # Extract genes from each source
            for source in ["gwas", "clinvar", "reactome"]:
                result = results_by_source.get(source, {})
                if result.get("success"):
                    genes = self._extract_genes_from_result(result)
                    if genes:
                        gene_sources[source] = genes

            # Extract proteins from UniProt
            uniprot_result = results_by_source.get("uniprot", {})
            if uniprot_result.get("success"):
                proteins = self._extract_proteins_from_result(uniprot_result)
                if proteins:
                    protein_sources["uniprot"] = proteins

            # ========================================
            # PHASE 3: Map genes and proteins to drugs
            # ========================================
            phase3_tasks = []
            phase3_labels = []

            # Create tasks for each gene source
            for source, genes in gene_sources.items():
                phase3_tasks.append(self._query_genes_to_drugs(genes, source))
                phase3_labels.append(source)

            # Create task for UniProt proteins
            if protein_sources.get("uniprot"):
                protein_accessions = [p["accession"] for p in protein_sources["uniprot"]]
                phase3_tasks.append(self._query_proteins_to_drugs(protein_accessions))
                phase3_labels.append("uniprot")

            # Run all gene/protein to drug queries in parallel
            drugs_by_source = {}
            if phase3_tasks:
                phase3_results = await asyncio.gather(*phase3_tasks)

                for label, result in zip(phase3_labels, phase3_results):
                    if result.get("success"):
                        drugs_by_gene = self._extract_drugs_from_gene_results(result, f"{label}_association")
                        if drugs_by_gene:
                            drugs_by_source[label] = {
                                "genes": list(drugs_by_gene.keys()),
                                "drugs_by_gene": drugs_by_gene,
                                "gene_count": len(drugs_by_gene),
                                "drug_count": sum(len(d) for d in drugs_by_gene.values())
                            }

            # ========================================
            # Build response
            # ========================================
            response_data = {
                "disease": disease,
                "direct_indications": {
                    "drugs": direct_drugs,
                    "count": len(direct_drugs),
                    "min_phase_filter": min_indication_phase,
                    "note": f"Drugs with Phase {min_indication_phase}+ specifically for {disease}"
                }
            }

            # Add each source's results
            source_descriptions = {
                "gwas": "Drugs targeting genes genetically associated via GWAS",
                "clinvar": "Drugs targeting genes with disease-associated variants (ClinVar)",
                "reactome": "Drugs targeting genes in disease-related pathways (Reactome)",
                "uniprot": "Drugs targeting proteins annotated with disease (UniProt)"
            }

            total_gene_drugs = 0
            total_genes = 0
            queries_run = ["direct_indications"]

            for source in ["gwas", "clinvar", "reactome", "uniprot"]:
                if source in drugs_by_source:
                    source_data = drugs_by_source[source]
                    response_data[f"{source}_targets"] = {
                        "genes": source_data["genes"],
                        "drugs_by_gene": source_data["drugs_by_gene"],
                        "gene_count": source_data["gene_count"],
                        "drug_count": source_data["drug_count"],
                        "note": source_descriptions.get(source, "")
                    }
                    total_gene_drugs += source_data["drug_count"]
                    total_genes += source_data["gene_count"]
                    queries_run.extend([f"{source}_genes", f"{source}_to_drugs"])
                elif source in task_labels:
                    # Source was queried but returned no results
                    response_data[f"{source}_targets"] = {
                        "genes": [],
                        "drugs_by_gene": {},
                        "gene_count": 0,
                        "drug_count": 0,
                        "note": source_descriptions.get(source, "")
                    }
                    queries_run.append(f"{source}_genes")

            # Add summary
            response_data["summary"] = {
                "direct_indication_drugs": len(direct_drugs),
                "total_target_genes": total_genes,
                "total_gene_based_drugs": total_gene_drugs,
                "sources_queried": task_labels,
                "sources_with_results": list(drugs_by_source.keys()),
                "queries_run": queries_run
            }

            # Build human-readable summary
            summary_parts = [
                f"Found {len(direct_drugs)} drugs with direct {disease} indications (Phase {min_indication_phase}+)"
            ]

            for source in ["gwas", "clinvar", "reactome", "uniprot"]:
                if source in drugs_by_source:
                    data = drugs_by_source[source]
                    summary_parts.append(
                        f"{data['drug_count']} drugs from {data['gene_count']} {source.upper()} genes"
                    )

            summary_text = ", ".join(summary_parts)

            return ToolResult(
                success=True,
                data=response_data,
                metadata={
                    "disease": disease,
                    "min_indication_phase": min_indication_phase,
                    "sources_enabled": {
                        "gwas": include_gwas,
                        "clinvar": include_clinvar,
                        "reactome": include_reactome,
                        "uniprot": include_uniprot
                    },
                    "summary": summary_text
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"Disease drug discovery error: {str(e)}"
            )
