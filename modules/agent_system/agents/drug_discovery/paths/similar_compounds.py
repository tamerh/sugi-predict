"""PATH 9: Similar Compounds via Morgan Fingerprints.

Find compounds structurally similar to known drugs.
This helps identify:
- Drug analogs in patent literature
- Potential lead optimization candidates
- Related compounds for SAR analysis

Use case: Given approved drugs for disease, find similar compounds
that may have improved properties or different IP status.
"""

from typing import Dict, Any, List, Optional
import logging

from .base import BasePath, PathResult

logger = logging.getLogger(__name__)


def compute_morgan_fingerprint(smiles: str, radius: int = 2, n_bits: int = 2048) -> Optional[List[float]]:
    """
    Compute Morgan fingerprint from SMILES using RDKit.

    Args:
        smiles: SMILES string
        radius: Morgan radius (2 = ECFP4 equivalent)
        n_bits: Fingerprint length (must match Qdrant collection)

    Returns:
        2048-dim fingerprint vector or None if invalid SMILES
    """
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        import numpy as np

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=n_bits)
        # Convert to float array for Qdrant
        arr = np.zeros(n_bits, dtype=np.float32)
        for bit in fp.GetOnBits():
            arr[bit] = 1.0
        return arr.tolist()

    except ImportError:
        logger.warning("RDKit not available, cannot compute fingerprints")
        return None
    except Exception as e:
        logger.warning(f"Failed to compute fingerprint for {smiles[:50]}...: {e}")
        return None


class SimilarCompoundsPath(BasePath):
    """
    PATH 9: Find compounds similar to known drugs.

    Uses: Qdrant patents_compounds collection (30M+ compounds, 2048-dim Morgan FP)

    Input: Drugs with SMILES from ChEMBL (via DirectIndications or gene-based paths)
    Output: Similar compounds from patent literature with SMILES and scores

    Computes Morgan fingerprints locally for speed (avoids slow scroll on 30M collection).
    """

    @property
    def name(self) -> str:
        return "similar_compounds"

    @property
    def description(self) -> str:
        return "Find structurally similar compounds using Morgan fingerprints"

    @property
    def requires_qdrant(self) -> bool:
        return True

    async def execute(
        self,
        disease: str,
        drugs: List[Dict] = None,
        smiles_list: List[str] = None,
        top_k: int = 5,
        min_score: float = 0.7,
        **kwargs
    ) -> PathResult:
        """
        Find compounds similar to known drugs.

        Args:
            disease: Disease name (for context)
            drugs: List of drug dicts with 'smiles' field (from drug extractor)
            smiles_list: Alternative: provide SMILES directly
            top_k: Number of similar compounds per query
            min_score: Minimum Tanimoto similarity (0-1)

        Returns:
            PathResult with similar compounds grouped by query drug
        """
        if not self.qdrant:
            return self._create_result(
                success=False,
                error="Qdrant client not available",
                metadata={"error": "Qdrant required for compound similarity search"}
            )

        # Check if collection is indexed (30M+ vectors need HNSW index)
        # Without index, each search takes 100+ seconds - unusable
        try:
            collections = await self.qdrant.get_collections()
            for col in collections:
                if col["name"] == "patents_compounds":
                    points = col.get("points_count", 0)
                    indexed = col.get("vectors_count", 0)
                    # If we have points but no indexed vectors, index not built
                    if indexed == 0 and points > 1000000:
                        return self._create_result(
                            success=False,
                            error=f"Compound collection not indexed ({points:,} points, 0 indexed). "
                                  "Each search takes 100+ seconds. Run: ./bioyoda.sh qdrant reindex patents_compounds",
                            metadata={
                                "points_count": points,
                                "indexed_count": indexed,
                                "fix": "./bioyoda.sh qdrant reindex patents_compounds",
                                "skip_reason": "unindexed_collection"
                            }
                        )
                    break
        except Exception:
            pass  # Continue anyway if check fails

        # Collect SMILES to search
        query_compounds = []

        if drugs:
            for drug in drugs[:20]:  # Limit to 20 drugs
                smiles = drug.get("smiles")
                if smiles:
                    query_compounds.append({
                        "drug_id": drug.get("id", ""),
                        "drug_name": drug.get("name", ""),
                        "smiles": smiles,
                        "inchi_key": drug.get("inchi_key", "")
                    })

        elif smiles_list:
            for i, smiles in enumerate(smiles_list[:20]):
                query_compounds.append({
                    "drug_id": f"compound_{i}",
                    "drug_name": f"Query {i+1}",
                    "smiles": smiles
                })

        if not query_compounds:
            return self._create_result(
                success=True,
                data={
                    "similar_compounds": {},
                    "compound_count": 0,
                    "message": "No drugs with SMILES to search"
                },
                metadata={"query": "No valid SMILES provided"}
            )

        # Compute fingerprints and search
        similar_by_query = {}
        all_similar = []
        errors = []

        for compound in query_compounds:
            drug_id = compound["drug_id"]
            smiles = compound["smiles"]

            # Compute Morgan fingerprint locally
            fp_vector = compute_morgan_fingerprint(smiles)

            if fp_vector is None:
                errors.append(f"{drug_id}: Invalid SMILES")
                continue

            try:
                # Search Qdrant directly with computed fingerprint
                results = await self.qdrant.search_similar_compounds(
                    query_vector=fp_vector,
                    limit=top_k,
                    score_threshold=min_score
                )

                if results:
                    similar_by_query[drug_id] = {
                        "query_drug": compound["drug_name"],
                        "query_smiles": smiles,
                        "similar": [
                            {
                                "surechembl_id": r.get("surechembl_id"),
                                "smiles": r.get("smiles"),
                                "molecular_weight": r.get("molecular_weight"),
                                "formula": r.get("formula"),
                                "similarity_score": round(r.get("score", 0), 4),
                                "url": f"https://www.surechembl.org/compound/{r.get('surechembl_id')}"
                            }
                            for r in results
                        ]
                    }
                    all_similar.extend(results)

            except Exception as e:
                errors.append(f"{drug_id}: {str(e)}")

        # Summary statistics
        total_similar = sum(len(v.get("similar", [])) for v in similar_by_query.values())
        unique_compounds = len(set(r.get("surechembl_id") for r in all_similar))

        # Get top matches across all queries
        all_similar.sort(key=lambda x: x.get("score", 0), reverse=True)
        top_matches = []
        seen = set()
        for match in all_similar[:10]:
            sid = match.get("surechembl_id")
            if sid and sid not in seen:
                top_matches.append({
                    "surechembl_id": sid,
                    "smiles": match.get("smiles"),
                    "similarity_score": round(match.get("score", 0), 4)
                })
                seen.add(sid)

        return self._create_result(
            success=True,
            data={
                "similar_compounds": similar_by_query,
                "drugs_searched": len(query_compounds),
                "drugs_with_matches": len(similar_by_query),
                "total_similar_found": total_similar,
                "unique_similar_compounds": unique_compounds,
                "top_matches": top_matches,
            },
            drugs=[
                {
                    "id": match["surechembl_id"],
                    "name": match["surechembl_id"],
                    "smiles": match.get("smiles"),
                    "evidence": "compound_similarity"
                }
                for match in top_matches
            ],
            metadata={
                "query": "Morgan fingerprint similarity search",
                "drugs_searched": len(query_compounds),
                "drugs_with_matches": len(similar_by_query),
                "top_k": top_k,
                "min_score": min_score,
                "errors": errors if errors else None
            }
        )
