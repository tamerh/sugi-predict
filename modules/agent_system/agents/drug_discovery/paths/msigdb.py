"""PATH 26: MSigDB (Molecular Signatures Database) Gene Sets.

Retrieves gene set membership and enrichment analysis from MSigDB.
MSigDB provides curated gene sets for functional analysis:
- H: Hallmark gene sets (50 well-defined biological states/processes)
- C1: Positional gene sets (by chromosome)
- C2: Curated gene sets (pathways from KEGG, Reactome, BioCarta, etc.)
- C3: Regulatory target gene sets (microRNA and TF targets)
- C4: Computational gene sets (cancer modules)
- C5: Ontology gene sets (GO terms)
- C6: Oncogenic signatures
- C7: Immunologic signatures
- C8: Cell type signatures

Query chain: gene >> hgnc >> msigdb OR geneset_name >> msigdb
"""

from typing import Dict, Any, List, Optional, Set
from collections import defaultdict

from .base import BasePath, PathResult


# MSigDB Collection descriptions
COLLECTION_INFO = {
    'H': {
        'name': 'Hallmark',
        'description': 'Well-defined biological states and processes',
        'count': 50,
    },
    'C1': {
        'name': 'Positional',
        'description': 'Gene sets by chromosomal position',
    },
    'C2': {
        'name': 'Curated',
        'description': 'Curated pathways from KEGG, Reactome, BioCarta, WikiPathways',
        'subcollections': ['CP:KEGG', 'CP:REACTOME', 'CP:BIOCARTA', 'CP:WIKIPATHWAYS', 'CGP'],
    },
    'C3': {
        'name': 'Regulatory',
        'description': 'MicroRNA and transcription factor targets',
        'subcollections': ['MIR', 'TFT'],
    },
    'C4': {
        'name': 'Computational',
        'description': 'Cancer gene neighborhoods and modules',
    },
    'C5': {
        'name': 'Ontology',
        'description': 'Gene Ontology (BP, MF, CC) and HPO terms',
        'subcollections': ['GO:BP', 'GO:MF', 'GO:CC', 'HPO'],
    },
    'C6': {
        'name': 'Oncogenic',
        'description': 'Oncogenic pathway signatures',
    },
    'C7': {
        'name': 'Immunologic',
        'description': 'Immunologic cell types and perturbations',
    },
    'C8': {
        'name': 'Cell Type',
        'description': 'Cell type signature gene sets',
    },
}


def calculate_enrichment_score(
    query_genes: Set[str],
    geneset_genes: Set[str],
    background_size: int = 20000
) -> Dict[str, Any]:
    """
    Calculate simple enrichment score for a gene set.

    Returns overlap statistics and fold enrichment.
    """
    overlap = query_genes & geneset_genes
    overlap_count = len(overlap)

    if not overlap_count:
        return {
            'overlap_count': 0,
            'overlap_genes': [],
            'coverage': 0.0,
            'fold_enrichment': 0.0,
        }

    # Coverage: fraction of gene set covered by query
    coverage = overlap_count / len(geneset_genes) if geneset_genes else 0

    # Simple fold enrichment
    expected = (len(query_genes) * len(geneset_genes)) / background_size
    fold_enrichment = overlap_count / expected if expected > 0 else 0

    return {
        'overlap_count': overlap_count,
        'overlap_genes': list(overlap),
        'coverage': round(coverage, 4),
        'fold_enrichment': round(fold_enrichment, 2),
    }


class MSigDBPath(BasePath):
    """
    PATH 26: MSigDB Gene Set Enrichment.

    Retrieves gene set memberships from MSigDB and performs
    simple enrichment analysis against query gene lists.

    Useful for:
    - Pathway enrichment (what pathways are genes involved in?)
    - Functional annotation (biological processes, molecular functions)
    - Disease signatures (oncogenic, immunologic patterns)
    - Regulatory analysis (TF targets, miRNA targets)
    """

    @property
    def name(self) -> str:
        return "msigdb"

    @property
    def description(self) -> str:
        return "MSigDB gene set membership and enrichment analysis"

    async def _get_geneset_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get MSigDB gene set by name or systematic ID."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[name],
                mapfilter="msigdb",
                mode="full"
            )

            for r in result.get('results', {}).get('results', []):
                attr = r.get('Attributes', {}).get('Msigdb', {})
                if attr:
                    return attr
            return None
        except Exception:
            return None

    async def _get_genesets_for_gene(self, gene_symbol: str) -> List[Dict[str, Any]]:
        """Get all gene sets containing a gene."""
        try:
            result = await self.biobtree.map_query_all_pages(
                terms=[gene_symbol],
                mapfilter="hgnc>>msigdb",
                mode="full"
            )

            genesets = []
            for r in result.get('results', {}).get('results', []):
                for t in r.get('targets', []):
                    attr = t.get('msigdb', {})
                    if attr:
                        genesets.append(attr)
            return genesets
        except Exception:
            return []

    async def execute(
        self,
        disease: str,
        genes: List[str] = None,
        geneset_names: List[str] = None,
        collections: List[str] = None,
        min_overlap: int = 2,
        max_genesets: int = 100,
        **kwargs
    ) -> PathResult:
        """
        Get MSigDB gene set data and perform enrichment.

        Args:
            disease: Disease name (for context)
            genes: List of gene symbols to analyze for enrichment
            geneset_names: Specific gene sets to retrieve (e.g., ['HALLMARK_APOPTOSIS'])
            collections: Filter to collections (e.g., ['H', 'C2', 'C5'])
            min_overlap: Minimum genes overlapping for inclusion
            max_genesets: Maximum gene sets to return

        Returns:
            PathResult with gene set memberships and enrichment scores
        """
        # Direct gene set lookup
        if geneset_names:
            return await self._get_specific_genesets(geneset_names, disease)

        # Gene-based enrichment
        if genes:
            return await self._analyze_gene_enrichment(
                genes, collections, min_overlap, max_genesets, disease
            )

        return self._create_result(
            success=True,
            data={"genesets": [], "note": "No genes or geneset names provided"},
            metadata={"query": "msigdb"}
        )

    async def _get_specific_genesets(
        self,
        geneset_names: List[str],
        disease: str
    ) -> PathResult:
        """Retrieve specific gene sets by name."""
        try:
            genesets = []

            for name in geneset_names[:50]:
                gs_data = await self._get_geneset_by_name(name)

                if gs_data:
                    collection = gs_data.get('collection', '')
                    genesets.append({
                        'systematic_name': gs_data.get('systematic_name', ''),
                        'standard_name': gs_data.get('standard_name', ''),
                        'collection': collection,
                        'collection_name': COLLECTION_INFO.get(collection, {}).get('name', ''),
                        'description': gs_data.get('description', ''),
                        'gene_symbols': gs_data.get('gene_symbols', []),
                        'gene_count': gs_data.get('gene_count', 0),
                        'pmid': gs_data.get('pmid', ''),
                        'contributor': gs_data.get('contributor', ''),
                    })

            return self._create_result(
                success=True,
                data={
                    "genesets": genesets,
                    "summary": {
                        "genesets_found": len(genesets),
                        "total_genes": sum(gs['gene_count'] for gs in genesets),
                    },
                    "note": f"MSigDB gene sets for {disease}"
                },
                metadata={"query": "msigdb geneset lookup"}
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "msigdb"}
            )

    async def _analyze_gene_enrichment(
        self,
        genes: List[str],
        collections: Optional[List[str]],
        min_overlap: int,
        max_genesets: int,
        disease: str
    ) -> PathResult:
        """Analyze gene list for gene set enrichment."""
        try:
            query_genes = set(g.upper() for g in genes)

            # Collect gene sets for each gene
            all_genesets = {}  # systematic_name -> geneset_data
            gene_to_genesets = defaultdict(list)

            for gene in list(query_genes)[:100]:  # Limit query genes
                genesets = await self._get_genesets_for_gene(gene)

                for gs in genesets:
                    sys_name = gs.get('systematic_name', '')
                    if not sys_name:
                        continue

                    # Filter by collection
                    collection = gs.get('collection', '')
                    if collections and collection not in collections:
                        continue

                    if sys_name not in all_genesets:
                        all_genesets[sys_name] = {
                            'systematic_name': sys_name,
                            'standard_name': gs.get('standard_name', ''),
                            'collection': collection,
                            'collection_name': COLLECTION_INFO.get(collection, {}).get('name', ''),
                            'description': gs.get('description', ''),
                            'gene_symbols': gs.get('gene_symbols', []),
                            'gene_count': gs.get('gene_count', 0),
                        }

                    gene_to_genesets[gene].append(sys_name)

            # Calculate enrichment for each gene set
            enriched_genesets = []

            for sys_name, gs_data in all_genesets.items():
                gs_genes = set(g.upper() for g in gs_data.get('gene_symbols', []))

                enrichment = calculate_enrichment_score(query_genes, gs_genes)

                if enrichment['overlap_count'] >= min_overlap:
                    enriched_genesets.append({
                        **gs_data,
                        'overlap_count': enrichment['overlap_count'],
                        'overlap_genes': enrichment['overlap_genes'],
                        'coverage': enrichment['coverage'],
                        'fold_enrichment': enrichment['fold_enrichment'],
                    })

            # Sort by fold enrichment and limit
            enriched_genesets.sort(key=lambda x: x['fold_enrichment'], reverse=True)
            enriched_genesets = enriched_genesets[:max_genesets]

            # Collection summary
            collection_counts = defaultdict(int)
            for gs in enriched_genesets:
                collection_counts[gs['collection']] += 1

            # Top hallmarks (most commonly disease-relevant)
            hallmarks = [
                gs for gs in enriched_genesets
                if gs['collection'] == 'H'
            ]

            return self._create_result(
                success=True,
                data={
                    "enriched_genesets": enriched_genesets,
                    "hallmark_genesets": hallmarks,
                    "gene_memberships": dict(gene_to_genesets),
                    "summary": {
                        "query_genes": len(query_genes),
                        "genes_with_genesets": len(gene_to_genesets),
                        "total_genesets_found": len(all_genesets),
                        "enriched_genesets": len(enriched_genesets),
                        "collection_distribution": dict(collection_counts),
                        "top_hallmarks": len(hallmarks),
                    },
                    "collections_info": COLLECTION_INFO,
                    "note": f"MSigDB enrichment for {disease} genes"
                },
                genes=list(query_genes),
                metadata={
                    "query": "msigdb gene enrichment",
                    "query_genes": len(query_genes),
                    "min_overlap": min_overlap,
                    "collections_filter": collections,
                }
            )

        except Exception as e:
            return self._create_result(
                success=False,
                error=str(e),
                metadata={"query": "msigdb"}
            )
