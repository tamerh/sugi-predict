"""PATH 2: GWAS Genetic Associations.

Query drugs targeting genes genetically associated with disease via GWAS.
Path: disease >> efo >> gwas >> ensembl >> drugs

Also fetches GWAS study metadata (PubMed IDs, authors, titles) for evidence attribution.
"""

from typing import Dict, Any, List

from .base import BasePath, PathResult
from ..extractors.gene_extractor import GeneExtractor
from ..extractors.drug_extractor import DrugExtractor


class GWASPath(BasePath):
    """
    PATH 2: Query drugs via GWAS genetic associations.

    Two-step query:
    1. disease >> efo >> gwas >> ensembl (get genes)
    2. genes >> ensembl >> uniprot >> chembl_molecule (get drugs)

    Also fetches GWAS study metadata for evidence sourcing.
    """

    @property
    def name(self) -> str:
        return "gwas"

    @property
    def description(self) -> str:
        return "Drugs targeting genes genetically associated via GWAS"

    async def _get_gwas_studies(self, disease: str) -> List[Dict[str, Any]]:
        """
        Fetch GWAS study metadata for a disease.

        Returns list of studies with PubMed IDs, titles, authors, etc.
        """
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[disease],
                mapfilter=">>efo>>gwas_study",
                mode="full"
            )

            studies = []
            seen_pubmed = set()

            for t in result.get('targets', []):
                gs = t.get('gwas_study', {})
                pubmed_id = gs.get('pubmed_id', '')

                # Deduplicate by PubMed ID
                if pubmed_id and pubmed_id not in seen_pubmed:
                    seen_pubmed.add(pubmed_id)
                    studies.append({
                        'study_id': t.get('identifier', ''),
                        'pubmed_id': pubmed_id,
                        'title': gs.get('study', ''),
                        'first_author': gs.get('first_author', ''),
                        'publication_date': gs.get('publication_date', ''),
                        'disease_trait': gs.get('disease_trait', ''),
                        'association_count': gs.get('association_count', 0),
                        'reported_genes': gs.get('reported_genes', []),
                        'mapped_genes': gs.get('mapped_genes', []),
                    })

            # Sort by association count (most associations first)
            studies.sort(key=lambda x: x.get('association_count', 0), reverse=True)
            return studies

        except Exception:
            return []

    async def execute(self, disease: str, max_genes: int = 50, **kwargs) -> PathResult:
        """
        Execute GWAS path query.

        Args:
            disease: Disease name or ID
            max_genes: Maximum genes to process (default: 50)

        Returns:
            PathResult with drugs targeting GWAS-associated genes
        """
        try:
            # Step 0: Get GWAS study metadata (PubMed IDs, titles, authors)
            gwas_studies = await self._get_gwas_studies(disease)

            # Step 1: Get genes associated with disease via GWAS
            mapfilter = ">>efo>>gwas>>ensembl[ensembl.genome==\"homo_sapiens\"]"
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
                    data={
                        "genes": [],
                        "drugs_by_gene": {},
                        "gwas_studies": gwas_studies,
                        "study_count": len(gwas_studies),
                    },
                    genes=[],
                    metadata={
                        "query": f"{disease} >> efo >> gwas >> ensembl",
                        "gene_count": 0,
                        "drug_count": 0,
                        "study_count": len(gwas_studies)
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
                evidence_type="gwas_association"
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
                    "drug_count": len(all_drugs),
                    "gwas_studies": gwas_studies,
                    "study_count": len(gwas_studies),
                    "total_associations": sum(s.get('association_count', 0) for s in gwas_studies),
                },
                drugs=all_drugs,
                genes=genes,
                metadata={
                    "query": f"{disease} >> efo >> gwas >> ensembl >> ... >> chembl_molecule",
                    "gene_count": len(genes),
                    "drug_count": len(all_drugs),
                    "study_count": len(gwas_studies)
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": f"{disease} >> efo >> gwas >> ensembl"}
            )
