"""PATH 15: GenCC Expert-Curated Gene-Disease Associations.

Query drugs targeting genes with expert-curated disease associations from GenCC.
Path: disease >> mondo >> gencc >> genes >> drugs

GenCC provides higher-quality curation than GWAS/ClinVar with explicit evidence levels:
- Definitive: Highest confidence
- Strong: High confidence
- Moderate: Medium confidence
- Limited: Lower confidence
- Disputed/Refuted: Not valid
"""

from typing import Dict, Any, List

from .base import BasePath, PathResult
from ..extractors.drug_extractor import DrugExtractor


class GenCCPath(BasePath):
    """
    PATH 15: Query drugs via GenCC expert-curated gene-disease associations.

    Uses MONDO disease ontology for GenCC linkage.
    Two-step query:
    1. disease >> mondo >> gencc (get genes with evidence levels)
    2. genes >> ensembl >> uniprot >> chembl_molecule (get drugs)

    GenCC provides curated assertions from:
    - ClinGen, OMIM, Orphanet, PanelApp, Ambry Genetics, etc.
    """

    # Classification priority (higher = more confident)
    CLASSIFICATION_SCORES = {
        "Definitive": 5,
        "Strong": 4,
        "Moderate": 3,
        "Limited": 2,
        "Disputed": 1,
        "Refuted": 0,
    }

    @property
    def name(self) -> str:
        return "gencc"

    @property
    def description(self) -> str:
        return "Drugs targeting genes with expert-curated disease associations (GenCC)"

    async def execute(
        self,
        disease: str,
        max_genes: int = 50,
        min_classification: str = "Limited",
        **kwargs
    ) -> PathResult:
        """
        Execute GenCC path query.

        Args:
            disease: Disease name or MONDO ID
            max_genes: Maximum genes to process (default: 50)
            min_classification: Minimum evidence level to include (default: "Limited")
                Options: Definitive, Strong, Moderate, Limited

        Returns:
            PathResult with drugs targeting GenCC-associated genes
        """
        try:
            # Step 1: Get genes with disease associations via GenCC
            # Try EFO >> MONDO >> GenCC first (works for disease names)
            # Fall back to MONDO >> GenCC (for MONDO IDs)
            mapfilter = ">>efo>>mondo>>gencc"
            gencc_result = await self.biobtree.map_query_all_pages(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            # If no results via EFO, try direct MONDO >> GenCC (for MONDO IDs)
            targets = gencc_result.get("targets", [])
            if not targets:
                mapfilter = ">>mondo>>gencc"
                gencc_result = await self.biobtree.map_query_all_pages(
                    terms=[disease],
                    mapfilter=mapfilter,
                    mode="full"
                )

            # Extract genes from GenCC results with classification info
            genes_with_evidence = self._extract_gencc_genes(
                gencc_result.get("targets", []),
                min_classification=min_classification
            )

            if not genes_with_evidence:
                return self._create_result(
                    success=True,
                    data={
                        "genes": [],
                        "gene_evidence": {},
                        "drugs_by_gene": {},
                        "gene_count": 0,
                        "drug_count": 0,
                        "classifications": {}
                    },
                    genes=[],
                    metadata={
                        "query": f"{disease} >> mondo >> gencc",
                        "gene_count": 0,
                        "drug_count": 0,
                        "min_classification": min_classification
                    }
                )

            # Get unique gene symbols for drug lookup
            gene_symbols = list(genes_with_evidence.keys())[:max_genes]

            # Step 2: Map genes to drugs via ChEMBL
            # Use gene symbols directly with ensembl (gene symbol >> ensembl works)
            drug_mapfilter = (
                ">>ensembl[ensembl.genome==\"homo_sapiens\"]"
                ">>uniprot[uniprot.reviewed==true]"
                ">>chembl_target_component>>chembl_target"
                ">>chembl_assay>>chembl_activity>>chembl_molecule"
            )
            drug_result = await self.biobtree.map_query_all_pages(
                terms=gene_symbols,
                mapfilter=drug_mapfilter,
                mode="full",
                preserve_sources=True
            )

            # Extract drugs grouped by gene
            drug_extractor = DrugExtractor()
            drugs_by_gene = drug_extractor.extract_from_gene_results(
                {"data": drug_result},
                evidence_type="gencc_curated"
            )

            # Flatten for drug list
            all_drugs = []
            seen_drug_ids = set()
            for gene_drugs in drugs_by_gene.values():
                for drug in gene_drugs:
                    if drug["id"] not in seen_drug_ids:
                        all_drugs.append(drug)
                        seen_drug_ids.add(drug["id"])

            # Count classifications
            classification_counts = {}
            for gene_data in genes_with_evidence.values():
                cls = gene_data.get("best_classification", "Unknown")
                classification_counts[cls] = classification_counts.get(cls, 0) + 1

            return self._create_result(
                success=True,
                data={
                    "genes": gene_symbols,
                    "gene_evidence": genes_with_evidence,
                    "drugs_by_gene": drugs_by_gene,
                    "gene_count": len(gene_symbols),
                    "drug_count": len(all_drugs),
                    "classifications": classification_counts
                },
                drugs=all_drugs,
                genes=gene_symbols,
                metadata={
                    "query": f"{disease} >> mondo >> gencc >> ... >> chembl_molecule",
                    "gene_count": len(gene_symbols),
                    "drug_count": len(all_drugs),
                    "min_classification": min_classification,
                    "classification_breakdown": classification_counts
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": f"{disease} >> mondo >> gencc"}
            )

    def _extract_gencc_genes(
        self,
        targets: List[Dict[str, Any]],
        min_classification: str = "Limited"
    ) -> Dict[str, Dict[str, Any]]:
        """
        Extract genes from GenCC results with evidence information.

        Args:
            targets: GenCC target results
            min_classification: Minimum classification level to include

        Returns:
            Dict mapping gene_symbol to evidence info
        """
        min_score = self.CLASSIFICATION_SCORES.get(min_classification, 0)
        genes_with_evidence = {}

        for target in targets:
            gencc = target.get("Attributes", {}).get("Gencc", {})
            if not gencc:
                # Try alternate structure
                gencc = target.get("gencc", {})

            if not gencc:
                continue

            gene_symbol = gencc.get("gene_symbol", "")
            classification = gencc.get("classification_title", "")
            classification_score = self.CLASSIFICATION_SCORES.get(classification, 0)

            # Filter by minimum classification
            if classification_score < min_score:
                continue

            if not gene_symbol:
                continue

            # Track best classification per gene (multiple submitters may curate same gene)
            if gene_symbol in genes_with_evidence:
                existing_score = self.CLASSIFICATION_SCORES.get(
                    genes_with_evidence[gene_symbol].get("best_classification", ""), 0
                )
                if classification_score > existing_score:
                    genes_with_evidence[gene_symbol]["best_classification"] = classification
                # Add submitter to list
                genes_with_evidence[gene_symbol]["submitters"].append({
                    "name": gencc.get("submitter_title", ""),
                    "classification": classification,
                    "moi": gencc.get("moi_title", ""),
                    "date": gencc.get("submitted_as_date", "")
                })
            else:
                genes_with_evidence[gene_symbol] = {
                    "gene_symbol": gene_symbol,
                    "hgnc_id": gencc.get("gene_curie", ""),
                    "disease": gencc.get("disease_title", ""),
                    "disease_id": gencc.get("disease_curie", ""),
                    "best_classification": classification,
                    "moi": gencc.get("moi_title", ""),  # Mode of inheritance
                    "submitters": [{
                        "name": gencc.get("submitter_title", ""),
                        "classification": classification,
                        "moi": gencc.get("moi_title", ""),
                        "date": gencc.get("submitted_as_date", "")
                    }]
                }

        # Sort by classification score (best first)
        sorted_genes = dict(
            sorted(
                genes_with_evidence.items(),
                key=lambda x: self.CLASSIFICATION_SCORES.get(x[1].get("best_classification", ""), 0),
                reverse=True
            )
        )

        return sorted_genes
