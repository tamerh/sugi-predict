"""PATH 22: HMDB Metabolites.

Query disease-associated metabolites from Human Metabolome Database.
Path: disease >> mesh >> hmdb

Use case: Identify metabolite biomarkers and disease-associated metabolic
pathways for drug discovery.
"""

from typing import Dict, Any, List
from collections import defaultdict

from .base import BasePath, PathResult


class HMDBPath(BasePath):
    """
    PATH 22: Query disease-associated metabolites from HMDB.

    Uses: disease >> mesh >> hmdb

    Provides:
    - Disease-associated metabolites
    - Metabolite classification
    - Associated pathways
    - Biomarker candidates
    """

    @property
    def name(self) -> str:
        return "hmdb"

    @property
    def description(self) -> str:
        return "Disease-associated metabolites from Human Metabolome Database"

    async def execute(
        self,
        disease: str,
        **kwargs
    ) -> PathResult:
        """
        Query HMDB for disease-associated metabolites.

        Args:
            disease: Disease name or ID

        Returns:
            PathResult with metabolite data
        """
        try:
            # Try direct disease >> hmdb query first via MeSH
            mapfilter = ">>mesh>>hmdb"
            hmdb_result = await self.biobtree.map_query_all_pages(
                terms=[disease],
                mapfilter=mapfilter,
                mode="full"
            )

            metabolites = []
            pathway_counts = defaultdict(int)
            biofluid_counts = defaultdict(int)
            seen_ids = set()

            targets = hmdb_result.get("targets", [])

            for target in targets:
                hmdb_id = target.get("identifier", "")
                if not hmdb_id or hmdb_id in seen_ids:
                    continue
                seen_ids.add(hmdb_id)

                # HMDB data can be in different locations
                hmdb_data = target.get("hmdb", {})
                if not hmdb_data:
                    hmdb_data = target.get("Attributes", {}).get("Hmdb", {})

                name = hmdb_data.get("name", target.get("name", ""))
                chemical_formula = hmdb_data.get("chemical_formula", "")
                avg_molecular_weight = hmdb_data.get("average_molecular_weight", "")
                smiles = hmdb_data.get("smiles", "")
                inchikey = hmdb_data.get("inchikey", "")

                # Pathways
                pathways = hmdb_data.get("pathways", [])
                for pathway in pathways:
                    if isinstance(pathway, dict):
                        pathway_name = pathway.get("name", "")
                    else:
                        pathway_name = str(pathway)
                    if pathway_name:
                        pathway_counts[pathway_name] += 1

                # Biofluids (where metabolite is found)
                biofluids = hmdb_data.get("biofluids", [])
                for biofluid in biofluids:
                    if biofluid:
                        biofluid_counts[biofluid] += 1

                # Disease associations
                diseases = hmdb_data.get("diseases", [])

                metabolites.append({
                    "hmdb_id": hmdb_id,
                    "name": name,
                    "chemical_formula": chemical_formula,
                    "molecular_weight": avg_molecular_weight,
                    "smiles": smiles,
                    "inchikey": inchikey,
                    "pathways": pathways[:5] if pathways else [],
                    "biofluids": biofluids,
                    "diseases": diseases[:5] if diseases else [],
                    "url": target.get("url", f"https://hmdb.ca/metabolites/{hmdb_id}"),
                })

            # Summary
            metabolite_summary = {
                "total_metabolites": len(metabolites),
                "top_pathways": sorted(pathway_counts.items(), key=lambda x: x[1], reverse=True)[:10],
                "biofluids": dict(biofluid_counts),
                "with_structure": sum(1 for m in metabolites if m.get("smiles")),
            }

            return self._create_result(
                success=True,
                data={
                    "metabolites": metabolites,
                    "metabolite_summary": metabolite_summary,
                    "metabolite_count": len(metabolites),
                },
                metadata={
                    "query": f"{disease} >> mesh >> hmdb",
                    "metabolite_count": len(metabolites),
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": f"{disease} >> mesh >> hmdb"}
            )


class HMDBEnrichmentPath(BasePath):
    """
    PATH 22b: Enrich genes with associated metabolites from HMDB.

    Uses: genes >> uniprot >> hmdb

    Provides:
    - Metabolites associated with gene products (enzymes)
    - Substrate/product relationships
    """

    @property
    def name(self) -> str:
        return "hmdb_enrichment"

    @property
    def description(self) -> str:
        return "Metabolites associated with disease genes (HMDB)"

    async def execute(
        self,
        disease: str,
        genes: List[str] = None,
        **kwargs
    ) -> PathResult:
        """
        Enrich genes with HMDB metabolite associations.

        Args:
            disease: Disease name (for context)
            genes: List of gene symbols

        Returns:
            PathResult with gene-metabolite associations
        """
        if not genes:
            return self._create_result(
                success=True,
                data={
                    "genes_with_metabolites": {},
                    "gene_count": 0
                },
                metadata={
                    "query": "No genes provided",
                    "gene_count": 0
                }
            )

        try:
            # Query HMDB via UniProt
            mapfilter = ">>ensembl[ensembl.genome==\"homo_sapiens\"]>>uniprot[uniprot.reviewed==true]>>hmdb"
            hmdb_result = await self.biobtree.map_query_all_pages(
                terms=genes[:30],
                mapfilter=mapfilter,
                mode="full",
                preserve_sources=True
            )

            genes_with_metabolites = {}

            # Process results
            results_container = hmdb_result.get("results", {})
            if isinstance(results_container, dict):
                results = results_container.get("results", [])
            else:
                results = results_container

            for result in results:
                source_gene = result.get("source", {}).get("keyword", "")
                targets = result.get("targets", [])

                if not source_gene or not targets:
                    continue

                metabolites = []
                seen_ids = set()

                for target in targets:
                    hmdb_id = target.get("identifier", "")
                    if not hmdb_id or hmdb_id in seen_ids:
                        continue
                    seen_ids.add(hmdb_id)

                    hmdb_data = target.get("hmdb", {})
                    if not hmdb_data:
                        hmdb_data = target.get("Attributes", {}).get("Hmdb", {})

                    metabolites.append({
                        "hmdb_id": hmdb_id,
                        "name": hmdb_data.get("name", target.get("name", "")),
                        "chemical_formula": hmdb_data.get("chemical_formula", ""),
                        "url": target.get("url", f"https://hmdb.ca/metabolites/{hmdb_id}"),
                    })

                if metabolites:
                    genes_with_metabolites[source_gene] = {
                        "gene_symbol": source_gene,
                        "metabolites": metabolites,
                        "metabolite_count": len(metabolites),
                    }

            return self._create_result(
                success=True,
                data={
                    "genes_with_metabolites": genes_with_metabolites,
                    "gene_count": len(genes_with_metabolites),
                    "genes_queried": len(genes),
                },
                genes=list(genes_with_metabolites.keys()),
                metadata={
                    "query": "genes >> uniprot >> hmdb",
                    "gene_count": len(genes_with_metabolites),
                    "genes_queried": len(genes),
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "genes >> uniprot >> hmdb"}
            )
