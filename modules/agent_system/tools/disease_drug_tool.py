"""Specialized Disease Drug Discovery Tool.

This tool runs multiple BioBTree queries internally and returns
consolidated, filtered results for disease-to-drug queries.

Integrates with Qdrant for similarity search:
- ESM-2 protein embeddings (573K proteins)
- Morgan fingerprint compound similarity (30.8M patent compounds)
"""

import asyncio
from typing import Optional, List, Dict, Any

from .base import Tool, ToolResult
from ..llm.base import ToolDefinition
from ..integrations.biobtree_client import BioBTreeClient
from ..integrations.qdrant_client import BioYodaQdrantClient


class DiseaseDrugDiscoveryTool(Tool):
    """
    Specialized tool for comprehensive disease-to-drug discovery.

    Runs multiple query paths internally:
    - PATH 1: Direct ChEMBL indications (disease >> efo >> chembl_molecule)
    - PATH 2: GWAS genetic associations (disease >> efo >> gwas >> ensembl)
    - PATH 3: ClinVar variants (disease >> mondo >> clinvar >> ensembl)
    - PATH 4: Reactome pathways (disease >> efo >> reactome >> ensembl)
    - PATH 5: UniProt disease associations (disease >> efo >> uniprot)
    - PATH 6: PubChem FDA-approved drugs
    - PATH 7: Reactome pathway context
    - PATH 8: Similar proteins via ESM-2 embeddings (Qdrant)
    - PATH 9: Similar compounds via Morgan fingerprints (Qdrant)

    Returns consolidated results with proper indication-phase filtering.
    """

    def __init__(self, client: BioBTreeClient, qdrant_client: BioYodaQdrantClient = None):
        """
        Initialize Disease Drug Discovery tool.

        Args:
            client: BioBTree client instance
            qdrant_client: Optional Qdrant client for similarity search
        """
        super().__init__(
            name="disease_drug_discovery",
            description=(
                "Find drugs for a disease using multiple evidence paths. "
                "Returns: (1) Drugs with direct disease indications (filtered by approval phase), "
                "(2) Drugs targeting genes from GWAS, ClinVar variants, Reactome pathways, and UniProt, "
                "(3) Optionally: similar proteins (ESM-2) and similar compounds (Morgan fingerprints). "
                "Use this for questions like 'What drugs are available for glioblastoma?'"
            )
        )
        self.client = client
        self.qdrant = qdrant_client

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
                    },
                    "include_pubchem": {
                        "type": "boolean",
                        "description": (
                            "Include FDA-approved drugs from PubChem targeting disease-associated genes (default: true)."
                        ),
                        "default": True
                    },
                    "include_similar_proteins": {
                        "type": "boolean",
                        "description": (
                            "Find proteins similar to disease targets using ESM-2 embeddings. "
                            "Searches 573K SwissProt proteins. (default: false)"
                        ),
                        "default": False
                    },
                    "include_similar_compounds": {
                        "type": "boolean",
                        "description": (
                            "Find compounds similar to discovered drugs using Morgan fingerprints. "
                            "Searches 30.8M patent compounds. (default: false)"
                        ),
                        "default": False
                    },
                    "similarity_limit": {
                        "type": "integer",
                        "description": (
                            "Number of similar proteins/compounds to return per query (default: 5)."
                        ),
                        "default": 5
                    }
                },
                "required": ["disease"]
            }
        )

    async def _paginated_map_query(
        self,
        terms: List[str],
        mapfilter: str,
        mode: str = "full",
        max_pages: int = 10,
        preserve_sources: bool = False
    ) -> Dict[str, Any]:
        """
        Execute a map query with pagination to get ALL results.

        Args:
            terms: List of input terms
            mapfilter: BioBTree mapfilter string
            mode: Query mode ("full" or "lite")
            max_pages: Maximum pages to fetch (safety limit)
            preserve_sources: If True, preserve source-to-target mapping (for multi-term queries)

        Returns:
            Combined result with all targets from all pages
        """
        page_token = None

        if preserve_sources:
            # Preserve source-to-target mapping (each source has its own targets)
            targets_by_source = {}  # source_id -> list of targets

            for _ in range(max_pages):
                result = await self.client.map_query(
                    terms=terms,
                    mapfilter=mapfilter,
                    mode=mode,
                    page=page_token
                )

                results_data = result.get("results", {})
                results_list = results_data.get("results", [])

                for r in results_list:
                    source = r.get("source", {})
                    source_id = source.get("keyword") or source.get("identifier", "unknown")
                    if source_id not in targets_by_source:
                        targets_by_source[source_id] = {"source": source, "targets": []}
                    targets_by_source[source_id]["targets"].extend(r.get("targets", []))

                nextpage = results_data.get("nextpage", "")
                if nextpage and nextpage != page_token:
                    page_token = nextpage
                else:
                    break

            # Rebuild results list preserving source structure
            combined_results = [
                {"source": data["source"], "targets": data["targets"]}
                for data in targets_by_source.values()
            ]
            return {"results": {"results": combined_results}}

        else:
            # Flatten all targets (for single-term queries like disease -> drugs)
            all_targets = []

            for _ in range(max_pages):
                result = await self.client.map_query(
                    terms=terms,
                    mapfilter=mapfilter,
                    mode=mode,
                    page=page_token
                )

                results_data = result.get("results", {})
                results_list = results_data.get("results", [])
                for r in results_list:
                    all_targets.extend(r.get("targets", []))

                nextpage = results_data.get("nextpage", "")
                if nextpage and nextpage != page_token:
                    page_token = nextpage
                else:
                    break

            return {"results": {"results": [{"targets": all_targets}]}}

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
            # Use pagination to get ALL drugs (BEVACIZUMAB etc. may be on page 2+)
            mapfilter = ">>efo>>chembl_molecule"
            result = await self._paginated_map_query([disease], mapfilter, mode="full")

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
            # Use pagination to get ALL associated genes
            mapfilter = ">>efo>>gwas>>ensembl[ensembl.genome==\"homo_sapiens\"]"
            result = await self._paginated_map_query([disease], mapfilter, mode="full")

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
            # Use pagination to get ALL variant-associated genes
            mapfilter = ">>mondo>>clinvar>>ensembl[ensembl.genome==\"homo_sapiens\"]"
            result = await self._paginated_map_query([disease], mapfilter, mode="full")

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
            # Use pagination to get ALL pathway-associated genes
            mapfilter = ">>efo>>reactome>>ensembl[ensembl.genome==\"homo_sapiens\"]"
            result = await self._paginated_map_query([disease], mapfilter, mode="full")

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
            # Use pagination to get ALL disease-associated proteins
            mapfilter = ">>efo>>uniprot[uniprot.reviewed==true]"
            result = await self._paginated_map_query([disease], mapfilter, mode="full")

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
            # Use pagination to get ALL drugs (some genes have many drug targets)
            mapfilter = (
                ">>ensembl[ensembl.genome==\"homo_sapiens\"]"
                ">>uniprot[uniprot.reviewed==true]"
                ">>chembl_target_component>>chembl_target"
                ">>chembl_assay>>chembl_activity>>chembl_molecule"
            )
            result = await self._paginated_map_query(
                genes, mapfilter, mode="full", preserve_sources=True
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
            # Use pagination to get ALL drugs
            mapfilter = (
                ">>uniprot[uniprot.reviewed==true]"
                ">>chembl_target_component>>chembl_target"
                ">>chembl_assay>>chembl_activity>>chembl_molecule"
            )
            result = await self._paginated_map_query(
                proteins, mapfilter, mode="full", preserve_sources=True
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

    async def _query_genes_to_reactome_pathways(self, genes: List[str]) -> Dict[str, Any]:
        """
        Get Reactome pathways for disease-associated genes.

        Provides pathway context for the genes found via GWAS/ClinVar.

        Args:
            genes: List of gene symbols

        Returns:
            Dict with pathway mappings per gene
        """
        if not genes:
            return {"success": True, "data": {"results": {"results": []}}, "genes": []}

        try:
            # Query: genes >> ensembl >> reactome
            # Use pagination to get ALL pathways (genes can be in many pathways)
            mapfilter = (
                ">>ensembl[ensembl.genome==\"homo_sapiens\"]"
                ">>reactome"
            )
            result = await self._paginated_map_query(
                genes, mapfilter, mode="full", preserve_sources=True
            )

            return {
                "success": True,
                "data": result,
                "genes": genes,
                "query": f"{','.join(genes[:5])}... >> ensembl >> reactome"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "genes": genes
            }

    async def _query_genes_to_pubchem_drugs(self, genes: List[str], source: str = "pubchem") -> Dict[str, Any]:
        """
        Map genes to FDA-approved PubChem compounds via bioactivity data.

        PATH 6: genes >> ensembl >> uniprot >> pubchem_activity >> pubchem[pubchem.is_fda_approved==true]

        Args:
            genes: List of gene symbols
            source: Source identifier for tracking

        Returns:
            Dict with FDA-approved PubChem drug mappings for genes
        """
        if not genes:
            return {"success": True, "data": {"results": {"results": []}}, "genes": [], "source": source}

        try:
            # Query: genes >> ensembl >> uniprot >> pubchem_activity >> pubchem (FDA approved only)
            # Use pagination to get ALL FDA drugs
            mapfilter = (
                ">>ensembl[ensembl.genome==\"homo_sapiens\"]"
                ">>uniprot[uniprot.reviewed==true]"
                ">>pubchem_activity"
                ">>pubchem[pubchem.is_fda_approved==true]"
            )
            result = await self._paginated_map_query(
                genes, mapfilter, mode="full", preserve_sources=True
            )

            return {
                "success": True,
                "data": result,
                "genes": genes,
                "source": source,
                "query": f"{','.join(genes[:5])}... >> ensembl >> uniprot >> pubchem_activity >> pubchem[fda_approved]"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "genes": genes,
                "source": source
            }

    def _get_best_drug_name(self, alt_names: List[str], fallback: str = None) -> str:
        """
        Select the best drug name from altNames list.

        Prefers common/trade names over IUPAC chemical names.

        Args:
            alt_names: List of alternative names from ChEMBL
            fallback: Fallback name if no good name found

        Returns:
            Best drug name
        """
        if not alt_names:
            return fallback

        # Score each name - lower is better
        def name_score(name: str) -> int:
            if not name or len(name) < 2:
                return 1000

            score = 0

            # Penalize IUPAC-like names (contain brackets, complex patterns)
            if any(c in name for c in ['{', '}', '[', ']']):
                score += 100
            if name.count('(') > 1 or name.count('-') > 3:
                score += 50

            # Penalize very long names (likely IUPAC)
            if len(name) > 50:
                score += 80
            elif len(name) > 30:
                score += 30

            # Penalize names starting with numbers or special chars
            if name[0].isdigit() or name[0] in '({[':
                score += 40

            # Prefer simple alphanumeric names
            special_chars = sum(1 for c in name if not c.isalnum() and c not in ' -')
            score += special_chars * 5

            # Prefer shorter names
            score += len(name) // 10

            return score

        # Sort by score and return best
        scored = [(name, name_score(name)) for name in alt_names if name]
        if scored:
            scored.sort(key=lambda x: x[1])
            return scored[0][0]

        return fallback

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

        # Sort for consistent results across runs
        return sorted(list(genes))[:max_genes]

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

        # Sort by accession for consistent results
        return sorted(proteins.values(), key=lambda p: p["accession"])

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

                # Get drug name (prefer common names over IUPAC)
                alt_names = drug_info.get("altNames", [])
                drug_name = self._get_best_drug_name(alt_names, fallback=drug_id)

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

                # Get drug name (prefer common names over IUPAC)
                drug_name = None
                if drug_info:
                    alt_names = drug_info.get("altNames", [])
                    drug_name = self._get_best_drug_name(alt_names, fallback=drug_id)

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

    def _extract_pathways_from_results(self, result: Dict) -> Dict[str, List[Dict]]:
        """
        Extract Reactome pathways grouped by gene.

        Args:
            result: BioBTree query result from genes >> ensembl >> reactome

        Returns:
            Dict mapping gene symbols to their pathway lists
        """
        pathways_by_gene = {}

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            # Get gene symbol from source
            source = r.get("source", {})
            gene_symbol = source.get("keyword") or source.get("identifier", "Unknown")

            # Clean up gene symbol
            if gene_symbol.startswith("ENSG"):
                ensembl_data = source.get("ensembl", {})
                if not ensembl_data:
                    attrs = source.get("Attributes", {})
                    ensembl_data = attrs.get("Ensembl", {}) or attrs.get("ensembl", {})
                if ensembl_data:
                    gene_symbol = ensembl_data.get("symbol") or gene_symbol

            for target in r.get("targets", []):
                pathway_id = target.get("identifier", "")

                # Get Reactome data
                reactome_data = target.get("reactome", {})
                if not reactome_data:
                    attrs = target.get("Attributes", {})
                    reactome_data = attrs.get("Reactome", {}) or attrs.get("reactome", {})

                pathway_name = reactome_data.get("name", "") if reactome_data else ""
                is_disease = reactome_data.get("is_disease_pathway", False) if reactome_data else False

                pathway_entry = {
                    "id": pathway_id,
                    "name": pathway_name,
                    "is_disease_pathway": is_disease
                }

                if gene_symbol not in pathways_by_gene:
                    pathways_by_gene[gene_symbol] = []

                # Avoid duplicates
                if pathway_id not in [p["id"] for p in pathways_by_gene[gene_symbol]]:
                    pathways_by_gene[gene_symbol].append(pathway_entry)

        # Sort pathways by name
        for gene in pathways_by_gene:
            pathways_by_gene[gene].sort(key=lambda p: p.get("name", "").lower())

        return pathways_by_gene

    def _extract_pubchem_drugs_from_results(
        self,
        result: Dict,
        evidence_type: str = "pubchem_fda"
    ) -> Dict[str, List[Dict]]:
        """
        Extract PubChem FDA-approved drugs grouped by target gene.

        Args:
            result: BioBTree query result from genes >> ... >> pubchem
            evidence_type: Type of evidence for tracking

        Returns:
            Dict mapping gene symbols to their PubChem drug lists
        """
        drugs_by_gene = {}

        results_data = result.get("data", {}).get("results", {})
        results_list = results_data.get("results", [])

        for r in results_list:
            # Get gene symbol from source
            source = r.get("source", {})
            gene_symbol = source.get("keyword") or source.get("identifier", "Unknown")

            # Clean up gene symbol
            if gene_symbol.startswith("ENSG"):
                ensembl_data = source.get("ensembl", {})
                if not ensembl_data:
                    attrs = source.get("Attributes", {})
                    ensembl_data = attrs.get("Ensembl", {}) or attrs.get("ensembl", {})
                if ensembl_data:
                    gene_symbol = ensembl_data.get("symbol") or gene_symbol

            for target in r.get("targets", []):
                drug_id = target.get("identifier", "")  # PubChem CID

                # Get PubChem data
                pubchem_data = target.get("pubchem", {})
                if not pubchem_data:
                    attrs = target.get("Attributes", {})
                    pubchem_data = attrs.get("Pubchem", {}) or attrs.get("pubchem", {})

                # Get drug name (title or first synonym)
                drug_name = None
                if pubchem_data:
                    drug_name = pubchem_data.get("title")
                    if not drug_name:
                        synonyms = pubchem_data.get("synonyms", [])
                        if synonyms and isinstance(synonyms, list):
                            drug_name = synonyms[0]

                # Get molecular properties
                molecular_formula = pubchem_data.get("molecular_formula", "") if pubchem_data else ""
                molecular_weight = pubchem_data.get("molecular_weight") if pubchem_data else None
                is_fda_approved = pubchem_data.get("is_fda_approved", False) if pubchem_data else False

                drug_entry = {
                    "id": f"CID:{drug_id}" if drug_id and not drug_id.startswith("CID") else drug_id,
                    "cid": drug_id,
                    "name": drug_name or drug_id,
                    "molecular_formula": molecular_formula,
                    "molecular_weight": molecular_weight,
                    "is_fda_approved": is_fda_approved,
                    "evidence": evidence_type,
                    "source": "pubchem"
                }

                if gene_symbol not in drugs_by_gene:
                    drugs_by_gene[gene_symbol] = []

                # Avoid duplicates within same gene
                if drug_id not in [d["cid"] for d in drugs_by_gene[gene_symbol]]:
                    drugs_by_gene[gene_symbol].append(drug_entry)

        # Sort drugs within each gene by name
        for gene in drugs_by_gene:
            drugs_by_gene[gene].sort(key=lambda d: d.get("name", "").lower())

        return drugs_by_gene

    async def _find_similar_proteins(
        self,
        protein_ids: List[str],
        limit: int = 5
    ) -> Dict[str, List[Dict]]:
        """
        PATH 8: Find proteins similar to disease-associated targets using ESM-2 embeddings.

        Args:
            protein_ids: List of UniProt accession IDs
            limit: Number of similar proteins per query

        Returns:
            Dict mapping source protein ID to list of similar proteins
        """
        if not self.qdrant or not protein_ids:
            return {}

        similar_by_protein = {}

        for protein_id in protein_ids[:10]:  # Limit to 10 query proteins
            try:
                similar = await self.qdrant.search_proteins_by_id(
                    protein_id=protein_id,
                    limit=limit,
                    include_self=False
                )

                if similar:
                    # Enrich with BioBTree annotations
                    enriched = []
                    for p in similar:
                        pid = p.get("protein_id")
                        entry = {
                            "protein_id": pid,
                            "similarity_score": round(p.get("score", 0), 4),
                            "source": "esm2_embedding"
                        }

                        # Try to get gene name from BioBTree
                        try:
                            await self.client.connect()
                            result = await self.client.map_query(
                                terms=[pid],
                                mapfilter=">>uniprot",
                                mode="full"
                            )
                            results_list = result.get("results", {}).get("results", [])
                            if results_list:
                                source = results_list[0].get("source", {})
                                uniprot = source.get("uniprot", {})
                                entry["gene_name"] = uniprot.get("geneName") or uniprot.get("gene_name")
                                names = uniprot.get("names", [])
                                if names:
                                    entry["protein_name"] = names[0]
                        except Exception:
                            pass

                        enriched.append(entry)

                    similar_by_protein[protein_id] = enriched

            except Exception:
                continue

        return similar_by_protein

    async def _find_similar_compounds(
        self,
        drugs: List[Dict],
        limit: int = 5
    ) -> Dict[str, List[Dict]]:
        """
        PATH 9: Find compounds similar to discovered drugs using Morgan fingerprints.

        Args:
            drugs: List of drug dicts (must have 'smiles' or 'id' that can be resolved)
            limit: Number of similar compounds per query

        Returns:
            Dict mapping source drug ID to list of similar compounds
        """
        if not self.qdrant or not drugs:
            return {}

        # Import fingerprint generation
        try:
            from .compound_similarity_tool import smiles_to_fingerprint
        except ImportError:
            return {}

        similar_by_drug = {}

        for drug in drugs[:10]:  # Limit to 10 query drugs
            drug_id = drug.get("id", "")
            smiles = drug.get("smiles")

            # Try to get SMILES if not present
            if not smiles and drug_id:
                try:
                    await self.client.connect()
                    # Try ChEMBL lookup
                    result = await self.client.search([drug_id], dataset="chembl_molecule")
                    results = result.get("results", {}).get("results", [])
                    if results:
                        chembl = results[0].get("chembl", {}).get("molecule", {})
                        smiles = chembl.get("smiles")
                except Exception:
                    pass

            if not smiles:
                continue

            # Generate fingerprint
            fingerprint = smiles_to_fingerprint(smiles)
            if not fingerprint:
                continue

            try:
                similar = await self.qdrant.search_similar_compounds(
                    query_vector=fingerprint,
                    limit=limit + 1,  # Extra to filter out exact match
                    score_threshold=0.5
                )

                # Filter out exact match and format
                enriched = []
                for c in similar:
                    if c.get("smiles") == smiles:
                        continue
                    if len(enriched) >= limit:
                        break

                    enriched.append({
                        "surechembl_id": c.get("surechembl_id"),
                        "smiles": c.get("smiles"),
                        "molecular_weight": c.get("molecular_weight"),
                        "similarity_score": round(c.get("score", 0), 3),
                        "source": "morgan_fingerprint"
                    })

                if enriched:
                    similar_by_drug[drug_id] = {
                        "query_smiles": smiles,
                        "similar_compounds": enriched
                    }

            except Exception:
                continue

        return similar_by_drug

    async def execute(
        self,
        disease: str,
        min_indication_phase: int = 3,
        include_gwas: bool = True,
        include_clinvar: bool = True,
        include_reactome: bool = True,
        include_uniprot: bool = True,
        include_pubchem: bool = True,
        include_similar_proteins: bool = False,
        include_similar_compounds: bool = False,
        similarity_limit: int = 5,
        **kwargs
    ) -> ToolResult:
        """
        Execute comprehensive disease drug discovery using multiple evidence paths.

        Uses two-step approach for gene-based sources:
        1. Get genes/proteins from each source (GWAS, ClinVar, Reactome, UniProt)
        2. Map those genes/proteins to drugs via ChEMBL
        3. Optionally find similar proteins (ESM-2) and compounds (Morgan FP)

        Args:
            disease: Disease name or ID
            min_indication_phase: Minimum phase for direct indications (default: 3)
            include_gwas: Include GWAS-based drug targets (default: True)
            include_clinvar: Include ClinVar variant-based targets (default: True)
            include_reactome: Include Reactome pathway-based targets (default: True)
            include_uniprot: Include UniProt disease-associated proteins (default: True)
            include_pubchem: Include PubChem FDA-approved drugs (default: True)
            include_similar_proteins: Find similar proteins via ESM-2 (default: False)
            include_similar_compounds: Find similar compounds via Morgan FP (default: False)
            similarity_limit: Number of similar items per query (default: 5)
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
            # PHASE 4: Query PubChem and Reactome in parallel
            # ========================================
            # Collect all unique genes from all sources
            all_genes = set()
            for source_genes in gene_sources.values():
                all_genes.update(source_genes)
            all_genes_list = sorted(list(all_genes))[:50]  # Limit to 50 genes

            pubchem_data = None
            reactome_data = None

            if all_genes_list:
                # Run PubChem and Reactome queries in parallel
                phase4_tasks = []
                phase4_labels = []

                if include_pubchem:
                    phase4_tasks.append(self._query_genes_to_pubchem_drugs(all_genes_list, source="pubchem"))
                    phase4_labels.append("pubchem")

                # Always query Reactome for pathway context
                phase4_tasks.append(self._query_genes_to_reactome_pathways(all_genes_list))
                phase4_labels.append("reactome_pathways")

                if phase4_tasks:
                    phase4_results = await asyncio.gather(*phase4_tasks)

                    for label, result in zip(phase4_labels, phase4_results):
                        if label == "pubchem" and result.get("success"):
                            pubchem_drugs = self._extract_pubchem_drugs_from_results(
                                result,
                                evidence_type="pubchem_fda"
                            )
                            if pubchem_drugs:
                                pubchem_data = {
                                    "genes": list(pubchem_drugs.keys()),
                                    "drugs_by_gene": pubchem_drugs,
                                    "gene_count": len(pubchem_drugs),
                                    "drug_count": sum(len(d) for d in pubchem_drugs.values()),
                                    "note": "FDA-approved drugs from PubChem targeting disease-associated genes"
                                }
                        elif label == "reactome_pathways" and result.get("success"):
                            pathways_by_gene = self._extract_pathways_from_results(result)
                            if pathways_by_gene:
                                reactome_data = {
                                    "genes": list(pathways_by_gene.keys()),
                                    "pathways_by_gene": pathways_by_gene,
                                    "gene_count": len(pathways_by_gene),
                                    "pathway_count": sum(len(p) for p in pathways_by_gene.values()),
                                    "note": "Reactome pathways for disease-associated genes"
                                }

            # ========================================
            # PHASE 5: Similarity search (optional)
            # ========================================
            similar_proteins_data = None
            similar_compounds_data = None

            if self.qdrant and (include_similar_proteins or include_similar_compounds):
                phase5_tasks = []
                phase5_labels = []

                # PATH 8: Find similar proteins to disease targets
                if include_similar_proteins:
                    # Collect UniProt IDs from UniProt targets
                    protein_ids = []
                    if protein_sources.get("uniprot"):
                        protein_ids = [p["accession"] for p in protein_sources["uniprot"][:10]]

                    # Also try to get proteins from genes via BioBTree
                    if not protein_ids and all_genes_list:
                        try:
                            await self.client.connect()
                            result = await self.client.map_query(
                                terms=all_genes_list[:5],
                                mapfilter=">>ensembl>>uniprot[uniprot.reviewed==true]",
                                mode="lite"
                            )
                            mappings = result.get("results_lite", {}).get("mappings", [])
                            for m in mappings:
                                for t in m.get("targets", []):
                                    if t.get("d") == "uniprot":
                                        protein_ids.append(t.get("id"))
                                        if len(protein_ids) >= 10:
                                            break
                                if len(protein_ids) >= 10:
                                    break
                        except Exception:
                            pass

                    if protein_ids:
                        phase5_tasks.append(self._find_similar_proteins(protein_ids, similarity_limit))
                        phase5_labels.append("similar_proteins")

                # PATH 9: Find similar compounds to discovered drugs
                if include_similar_compounds and direct_drugs:
                    # Use top direct indication drugs
                    phase5_tasks.append(self._find_similar_compounds(direct_drugs[:10], similarity_limit))
                    phase5_labels.append("similar_compounds")

                if phase5_tasks:
                    phase5_results = await asyncio.gather(*phase5_tasks)

                    for label, result in zip(phase5_labels, phase5_results):
                        if label == "similar_proteins" and result:
                            similar_proteins_data = {
                                "query_proteins": list(result.keys()),
                                "similar_by_protein": result,
                                "query_count": len(result),
                                "total_similar": sum(len(v) for v in result.values()),
                                "method": "ESM-2 embedding similarity (1280-dim)",
                                "database": "SwissProt (573K proteins)"
                            }
                        elif label == "similar_compounds" and result:
                            similar_compounds_data = {
                                "query_drugs": list(result.keys()),
                                "similar_by_drug": result,
                                "query_count": len(result),
                                "total_similar": sum(len(v.get("similar_compounds", [])) for v in result.values()),
                                "method": "Morgan fingerprint similarity (2048-bit)",
                                "database": "SureChEMBL patents (30.8M compounds)"
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

            # Add PubChem results
            pubchem_drug_count = 0
            if pubchem_data:
                response_data["pubchem_targets"] = pubchem_data
                pubchem_drug_count = pubchem_data["drug_count"]
                queries_run.append("pubchem_fda_drugs")
            elif include_pubchem:
                response_data["pubchem_targets"] = {
                    "genes": [],
                    "drugs_by_gene": {},
                    "gene_count": 0,
                    "drug_count": 0,
                    "note": "FDA-approved drugs from PubChem (no results)"
                }
                queries_run.append("pubchem_fda_drugs")

            # Add Reactome pathway results
            reactome_pathway_count = 0
            if reactome_data:
                response_data["reactome_pathways"] = reactome_data
                reactome_pathway_count = reactome_data["pathway_count"]
                queries_run.append("reactome_pathways")
            else:
                response_data["reactome_pathways"] = {
                    "genes": [],
                    "pathways_by_gene": {},
                    "gene_count": 0,
                    "pathway_count": 0,
                    "note": "Reactome pathways (no results)"
                }

            # Add similarity search results
            similar_proteins_count = 0
            similar_compounds_count = 0

            if similar_proteins_data:
                response_data["similar_proteins"] = similar_proteins_data
                similar_proteins_count = similar_proteins_data["total_similar"]
                queries_run.append("similar_proteins")

            if similar_compounds_data:
                response_data["similar_compounds"] = similar_compounds_data
                similar_compounds_count = similar_compounds_data["total_similar"]
                queries_run.append("similar_compounds")

            # Add summary
            sources_with_results = list(drugs_by_source.keys())
            if pubchem_data:
                sources_with_results.append("pubchem")
            if reactome_data:
                sources_with_results.append("reactome_pathways")
            if similar_proteins_data:
                sources_with_results.append("similar_proteins")
            if similar_compounds_data:
                sources_with_results.append("similar_compounds")

            response_data["summary"] = {
                "direct_indication_drugs": len(direct_drugs),
                "total_target_genes": total_genes,
                "total_gene_based_drugs": total_gene_drugs,
                "pubchem_fda_drugs": pubchem_drug_count,
                "reactome_pathways": reactome_pathway_count,
                "similar_proteins": similar_proteins_count,
                "similar_compounds": similar_compounds_count,
                "sources_queried": task_labels + (["pubchem"] if include_pubchem else []) + ["reactome_pathways"],
                "sources_with_results": sources_with_results,
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
                        f"{data['drug_count']} ChEMBL drugs from {data['gene_count']} {source.upper()} genes"
                    )

            # Add PubChem to summary
            if pubchem_data:
                summary_parts.append(
                    f"{pubchem_data['drug_count']} FDA-approved PubChem drugs from {pubchem_data['gene_count']} genes"
                )

            # Add Reactome to summary
            if reactome_data:
                summary_parts.append(
                    f"{reactome_data['pathway_count']} Reactome pathways for {reactome_data['gene_count']} genes"
                )

            # Add similarity search to summary
            if similar_proteins_data:
                summary_parts.append(
                    f"{similar_proteins_data['total_similar']} similar proteins (ESM-2) for {similar_proteins_data['query_count']} targets"
                )
            if similar_compounds_data:
                summary_parts.append(
                    f"{similar_compounds_data['total_similar']} similar compounds (Morgan FP) for {similar_compounds_data['query_count']} drugs"
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
                        "uniprot": include_uniprot,
                        "pubchem": include_pubchem,
                        "similar_proteins": include_similar_proteins,
                        "similar_compounds": include_similar_compounds
                    },
                    "similarity_limit": similarity_limit,
                    "summary": summary_text
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"Disease drug discovery error: {str(e)}"
            )
