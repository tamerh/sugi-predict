"""PATH 3: ClinVar Variant Associations.

Query drugs targeting genes with disease-associated variants from ClinVar.
Path: disease >> mondo >> clinvar >> ensembl >> drugs
"""

from typing import Dict, Any, List

from .base import BasePath, PathResult
from ..extractors.gene_extractor import GeneExtractor
from ..extractors.drug_extractor import DrugExtractor


class ClinVarPath(BasePath):
    """
    PATH 3: Query drugs via ClinVar variant associations.

    Uses MONDO disease ontology for ClinVar linkage.
    Two-step query:
    1. disease >> mondo >> clinvar >> ensembl (get genes)
    2. genes >> ensembl >> uniprot >> chembl_molecule (get drugs)
    """

    @property
    def name(self) -> str:
        return "clinvar"

    @property
    def description(self) -> str:
        return "Drugs targeting genes with disease-associated variants (ClinVar)"

    async def execute(self, disease: str, max_genes: int = 50, **kwargs) -> PathResult:
        """
        Execute ClinVar path query.

        Args:
            disease: Disease name or ID
            max_genes: Maximum genes to process (default: 50)

        Returns:
            PathResult with drugs targeting ClinVar-associated genes
        """
        try:
            # Step 1: Get genes with disease-associated variants via ClinVar
            mapfilter = ">>mondo>>clinvar>>ensembl[ensembl.genome==\"homo_sapiens\"]"
            gene_result = await self.biobtree.map_query_all_pages(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            # Wrap flat result for extractor
            wrapped_gene_result = {"results": {"results": [{"targets": gene_result.get("targets", [])}]}}

            # Extract genes
            gene_extractor = GeneExtractor()
            genes = gene_extractor.extract_genes(
                {"data": wrapped_gene_result},
                max_genes=max_genes
            )

            if not genes:
                return self._create_result(
                    success=True,
                    data={"genes": [], "drugs_by_gene": {}},
                    genes=[],
                    metadata={
                        "query": f"{disease} >> mondo >> clinvar >> ensembl",
                        "gene_count": 0,
                        "drug_count": 0
                    }
                )

            # Step 2: Map genes to drugs via ChEMBL (preserve_sources to track gene->drug)
            drug_mapfilter = (
                ">>ensembl[ensembl.genome==\"homo_sapiens\"]"
                ">>uniprot[uniprot.reviewed==true]"
                ">>chembl_target_component>>chembl_target"
                ">>chembl_assay>>chembl_activity>>chembl_molecule"
            )
            drug_result = await self.biobtree.map_query_all_pages(
                terms=genes,
                mapfilter=drug_mapfilter,
                mode="full",
                preserve_sources=True  # Keep gene->drug mapping
            )

            # Extract drugs grouped by gene (preserve_sources returns {"results": {"results": [...]}})
            drug_extractor = DrugExtractor()
            drugs_by_gene = drug_extractor.extract_from_gene_results(
                {"data": drug_result},
                evidence_type="clinvar_association"
            )

            # Flatten for drug list
            all_drugs = []
            seen_drug_ids = set()
            for gene_drugs in drugs_by_gene.values():
                for drug in gene_drugs:
                    if drug["id"] not in seen_drug_ids:
                        all_drugs.append(drug)
                        seen_drug_ids.add(drug["id"])

            return self._create_result(
                success=True,
                data={
                    "genes": list(drugs_by_gene.keys()),
                    "drugs_by_gene": drugs_by_gene,
                    "gene_count": len(drugs_by_gene),
                    "drug_count": len(all_drugs)
                },
                drugs=all_drugs,
                genes=genes,
                metadata={
                    "query": f"{disease} >> mondo >> clinvar >> ensembl >> ... >> chembl_molecule",
                    "gene_count": len(genes),
                    "drug_count": len(all_drugs)
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": f"{disease} >> mondo >> clinvar >> ensembl"}
            )
