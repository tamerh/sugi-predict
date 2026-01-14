"""PATH 19: Protein Structures (PDB).

Enrich genes with protein structure data from PDB.
This helps assess druggability of targets.

Use case: Identify which disease-associated proteins have solved structures,
which is important for structure-based drug design.
"""

from typing import Dict, Any, List
from collections import defaultdict

from .base import BasePath, PathResult


class StructuresPath(BasePath):
    """
    PATH 19: Enrich genes with PDB structure data.

    Uses: genes >> ensembl >> uniprot >> pdb

    Provides:
    - Available crystal structures and cryo-EM structures
    - Resolution information
    - Coverage of protein sequence
    """

    @property
    def name(self) -> str:
        return "structures"

    @property
    def description(self) -> str:
        return "Protein structure availability for disease-associated genes (PDB)"

    async def execute(
        self,
        disease: str,
        genes: List[str] = None,
        max_structures: int = 10,
        **kwargs
    ) -> PathResult:
        """
        Enrich genes with PDB structure data.

        Args:
            disease: Disease name (for context)
            genes: List of gene symbols to query (from GWAS/ClinVar/GenCC)
            max_structures: Maximum structures per gene (default: 10)

        Returns:
            PathResult with structure data for each gene
        """
        if not genes:
            return self._create_result(
                success=True,
                data={
                    "genes_with_structures": {},
                    "structure_summary": {},
                    "gene_count": 0
                },
                metadata={
                    "query": "No genes provided",
                    "gene_count": 0
                }
            )

        try:
            # Query PDB via UniProt
            mapfilter = ">>ensembl[ensembl.genome==\"homo_sapiens\"]>>uniprot[uniprot.reviewed==true]>>pdb"
            pdb_result = await self.biobtree.map_query_all_pages(
                terms=genes[:30],  # Limit to avoid timeout
                mapfilter=mapfilter,
                mode="full",
                preserve_sources=True
            )

            genes_with_structures = {}
            method_counts = defaultdict(int)

            # Process results
            results_container = pdb_result.get("results", {})
            if isinstance(results_container, dict):
                results = results_container.get("results", [])
            else:
                results = results_container

            for result in results:
                source_gene = result.get("source", {}).get("keyword", "")
                targets = result.get("targets", [])

                if not source_gene or not targets:
                    continue

                structures = []

                for target in targets:
                    pdb_id = target.get("identifier", "")
                    pdb_data = target.get("Attributes", {}).get("Pdb", {})
                    if not pdb_data:
                        pdb_data = target.get("pdb", {})

                    if not pdb_id:
                        continue

                    method = pdb_data.get("method", "unknown")
                    resolution = pdb_data.get("resolution", "")
                    chains = pdb_data.get("chains", "")

                    structures.append({
                        "pdb_id": pdb_id,
                        "method": method,
                        "resolution": resolution,
                        "chains": chains,
                        "url": target.get("url", f"https://www.rcsb.org/structure/{pdb_id}"),
                    })

                    method_counts[method] += 1

                # Sort by resolution (best first) and limit
                def parse_resolution(r):
                    try:
                        return float(r.replace(" A", "").replace("Å", ""))
                    except:
                        return 999.0

                structures.sort(key=lambda x: parse_resolution(x.get("resolution", "")))
                structures = structures[:max_structures]

                if structures:
                    genes_with_structures[source_gene] = {
                        "gene_symbol": source_gene,
                        "structures": structures,
                        "structure_count": len(structures),
                        "best_resolution": structures[0].get("resolution", "N/A") if structures else "N/A",
                        "methods": list(set(s["method"] for s in structures)),
                    }

            # Summary by method
            structure_summary = {
                "by_method": dict(method_counts),
                "total_structures": sum(g["structure_count"] for g in genes_with_structures.values()),
                "genes_with_xray": sum(1 for g in genes_with_structures.values() if "x-ray" in g.get("methods", [])),
                "genes_with_em": sum(1 for g in genes_with_structures.values() if "em" in g.get("methods", [])),
            }

            return self._create_result(
                success=True,
                data={
                    "genes_with_structures": genes_with_structures,
                    "structure_summary": structure_summary,
                    "gene_count": len(genes_with_structures),
                    "genes_queried": len(genes),
                },
                genes=list(genes_with_structures.keys()),
                metadata={
                    "query": "genes >> ensembl >> uniprot >> pdb",
                    "gene_count": len(genes_with_structures),
                    "genes_queried": len(genes),
                    "max_structures": max_structures,
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "genes >> ensembl >> uniprot >> pdb"}
            )
