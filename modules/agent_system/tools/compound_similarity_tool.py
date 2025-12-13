"""Compound similarity search tool using Morgan fingerprints."""

from typing import Any, Dict, List, Optional
import numpy as np

from .base import Tool, ToolResult
from ..llm.base import ToolDefinition
from ..integrations.qdrant_client import BioYodaQdrantClient
from ..integrations.biobtree_client import BioBTreeClient

# RDKit imports for fingerprint generation
try:
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors
    from rdkit.DataStructs import ExplicitBitVect
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False


def smiles_to_fingerprint(smiles: str, radius: int = 2, n_bits: int = 2048) -> Optional[List[float]]:
    """
    Convert SMILES to Morgan fingerprint vector.

    Args:
        smiles: SMILES string
        radius: Morgan fingerprint radius (default: 2)
        n_bits: Number of bits in fingerprint (default: 2048)

    Returns:
        Fingerprint as list of floats, or None if parsing fails
    """
    if not RDKIT_AVAILABLE:
        return None

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        # Generate Morgan fingerprint
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=radius, nBits=n_bits)

        # Convert to numpy array
        fp_array = np.zeros((n_bits,), dtype=np.float32)
        for bit in fp.GetOnBits():
            fp_array[bit] = 1.0

        return fp_array.tolist()

    except Exception:
        return None


def get_molecular_properties(smiles: str) -> Optional[Dict[str, Any]]:
    """
    Calculate molecular properties from SMILES.

    Args:
        smiles: SMILES string

    Returns:
        Dict with molecular properties or None if parsing fails
    """
    if not RDKIT_AVAILABLE:
        return None

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None

        return {
            "molecular_weight": round(Descriptors.MolWt(mol), 2),
            "logp": round(Descriptors.MolLogP(mol), 2),
            "num_h_donors": Descriptors.NumHDonors(mol),
            "num_h_acceptors": Descriptors.NumHAcceptors(mol),
            "num_rotatable_bonds": Descriptors.NumRotatableBonds(mol),
            "tpsa": round(Descriptors.TPSA(mol), 2),
            "num_rings": Descriptors.RingCount(mol)
        }

    except Exception:
        return None


class CompoundSimilarityTool(Tool):
    """
    Tool for finding similar chemical compounds using Morgan fingerprints.

    Uses Qdrant vector database with 30M+ patent compound fingerprints
    and BioBTree for cross-referencing with ChEMBL/PubChem.

    Example queries:
    - "Find compounds similar to aspirin"
    - "Search for molecules similar to CC(=O)OC1=CC=CC=C1C(=O)O"
    - "Find similar compounds to CHEMBL25"
    """

    def __init__(
        self,
        qdrant_client: BioYodaQdrantClient,
        biobtree_client: BioBTreeClient
    ):
        """
        Initialize compound similarity tool.

        Args:
            qdrant_client: Qdrant client for vector search
            biobtree_client: BioBTree client for compound resolution
        """
        super().__init__(
            name="compound_similarity_search",
            description="Find chemical compounds similar to a given compound using Morgan fingerprints. "
                        "Input a SMILES string, ChEMBL ID, PubChem CID, or compound name "
                        "to find structurally similar molecules from 30M+ patent compounds."
        )
        self.qdrant = qdrant_client
        self.biobtree = biobtree_client

    def get_definition(self) -> ToolDefinition:
        """Get tool definition for LLM function calling."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Compound identifier: SMILES string (e.g., 'CC(=O)OC1=CC=CC=C1C(=O)O'), "
                                       "ChEMBL ID (e.g., 'CHEMBL25'), PubChem CID (e.g., '2244'), "
                                       "or compound name (e.g., 'aspirin')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of similar compounds to return (default: 10)",
                        "default": 10
                    },
                    "min_similarity": {
                        "type": "number",
                        "description": "Minimum Tanimoto similarity score (0-1, default: 0.5)",
                        "default": 0.5
                    }
                },
                "required": ["query"]
            }
        )

    async def execute(
        self,
        query: str,
        limit: int = 10,
        min_similarity: float = 0.5,
        **kwargs
    ) -> ToolResult:
        """
        Execute compound similarity search.

        Args:
            query: Compound identifier (SMILES, ChEMBL ID, PubChem CID, or name)
            limit: Maximum number of results
            min_similarity: Minimum similarity score threshold

        Returns:
            ToolResult with similar compounds
        """
        if not RDKIT_AVAILABLE:
            return ToolResult(
                success=False,
                data=None,
                error="RDKit is not installed. Cannot perform compound similarity search."
            )

        try:
            # Step 1: Resolve query to SMILES and fingerprint
            resolved = await self._resolve_compound(query)

            if not resolved:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Could not resolve compound: {query}. "
                          f"Please provide a valid SMILES string, ChEMBL ID, PubChem CID, or compound name."
                )

            smiles = resolved.get('smiles')
            fingerprint = resolved.get('fingerprint')

            if not fingerprint:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Could not generate fingerprint for: {query}"
                )

            # Step 2: Search for similar compounds in Qdrant
            similar_compounds = await self.qdrant.search_similar_compounds(
                query_vector=fingerprint,
                limit=limit + 1,  # Extra to filter out exact match
                score_threshold=min_similarity
            )

            # Filter out exact match (same SMILES)
            similar_compounds = [
                c for c in similar_compounds
                if c.get('smiles') != smiles
            ][:limit]

            # Step 3: Calculate properties for query compound
            query_props = get_molecular_properties(smiles)

            return ToolResult(
                success=True,
                data={
                    "query_compound": {
                        "original_query": query,
                        "smiles": smiles,
                        "resolved_from": resolved.get('source', 'direct'),
                        "properties": query_props
                    },
                    "similar_compounds": similar_compounds,
                    "count": len(similar_compounds),
                    "method": "Morgan fingerprint similarity (2048-bit, radius=2)",
                    "database": "SureChEMBL patents (30.8M compounds)",
                    "min_similarity": min_similarity
                },
                metadata={
                    "tool": self.name,
                    "limit": limit,
                    "min_similarity": min_similarity
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"Compound similarity search failed: {str(e)}"
            )

    async def _resolve_compound(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a query to SMILES and fingerprint.

        Tries multiple resolution strategies:
        1. Direct SMILES parsing
        2. SureChEMBL ID lookup in Qdrant
        3. ChEMBL ID via BioBTree
        4. PubChem CID via BioBTree
        5. Compound name search

        Args:
            query: Compound query string

        Returns:
            Dict with 'smiles', 'fingerprint', 'source' or None
        """
        query = query.strip()

        # Strategy 1: Try as direct SMILES
        fingerprint = smiles_to_fingerprint(query)
        if fingerprint:
            return {
                'smiles': query,
                'fingerprint': fingerprint,
                'source': 'direct_smiles'
            }

        # Strategy 2: Try as SureChEMBL ID - use scroll with timeout
        if query.upper().startswith('SCHEMBL'):
            try:
                # Direct scroll lookup with filter (may be slow on 30M docs)
                from qdrant_client.models import Filter, FieldCondition, MatchValue
                results = self.qdrant.client.scroll(
                    collection_name="patents_compounds",
                    scroll_filter=Filter(
                        must=[FieldCondition(key="surechembl_id", match=MatchValue(value=query.upper()))]
                    ),
                    limit=1,
                    with_vectors=True,
                    with_payload=True
                )
                if results[0]:
                    point = results[0][0]
                    smiles = point.payload.get('smiles')
                    vector = point.vector
                    if smiles and vector:
                        return {
                            'smiles': smiles,
                            'fingerprint': vector,
                            'source': 'surechembl_id'
                        }
            except Exception:
                pass  # Fall through to other strategies

        # Strategy 3: Try as ChEMBL ID
        if query.upper().startswith('CHEMBL'):
            smiles = await self._get_smiles_from_chembl(query.upper())
            if smiles:
                fingerprint = smiles_to_fingerprint(smiles)
                if fingerprint:
                    return {
                        'smiles': smiles,
                        'fingerprint': fingerprint,
                        'source': 'chembl_id'
                    }

        # Strategy 4: Try as PubChem CID (numeric)
        if query.isdigit():
            smiles = await self._get_smiles_from_pubchem(query)
            if smiles:
                fingerprint = smiles_to_fingerprint(smiles)
                if fingerprint:
                    return {
                        'smiles': smiles,
                        'fingerprint': fingerprint,
                        'source': 'pubchem_cid'
                    }

        # Strategy 5: Try as compound name via ChEMBL search
        smiles = await self._search_compound_name(query)
        if smiles:
            fingerprint = smiles_to_fingerprint(smiles)
            if fingerprint:
                return {
                    'smiles': smiles,
                    'fingerprint': fingerprint,
                    'source': 'name_search'
                }

        return None

    async def _get_smiles_from_chembl(self, chembl_id: str) -> Optional[str]:
        """Get SMILES from ChEMBL ID via BioBTree.

        Most ChEMBL molecules have SMILES stored directly. For entries without
        SMILES (like CHEMBL25/aspirin), we fall back to using altNames to search PubChem.
        """
        try:
            await self.biobtree.connect()

            # Search ChEMBL to find the entry
            result = await self.biobtree.search([chembl_id], dataset="chembl_molecule")
            results = result.get('results', {}).get('results', [])

            if not results:
                return None

            for r in results:
                if isinstance(r, dict):
                    chembl = r.get('chembl', {}).get('molecule', {})

                    # First try: direct SMILES from ChEMBL (most compounds have this)
                    smiles = chembl.get('smiles')
                    if smiles:
                        return smiles

                    # Fallback: use altNames to search PubChem
                    alt_names = chembl.get('altNames', [])
                    for name in alt_names[:5]:  # Try first 5 names
                        # Skip names that look like IDs (SID*, NSC-*, etc.)
                        if name.startswith('SID') or name.startswith('NSC-'):
                            continue
                        smiles = await self._search_compound_name(name)
                        if smiles:
                            return smiles

        except Exception:
            pass

        return None

    async def _get_smiles_from_pubchem(self, cid: str) -> Optional[str]:
        """Get SMILES from PubChem CID via BioBTree search.

        BioBTree's PubChem search returns SMILES directly in the result.
        """
        try:
            await self.biobtree.connect()

            # Search PubChem by CID - this returns SMILES in result
            result = await self.biobtree.search([cid], dataset="pubchem")
            results = result.get('results', {}).get('results', [])

            for r in results:
                if isinstance(r, dict):
                    # SMILES is in pubchem sub-object
                    pubchem = r.get('pubchem', {})
                    smiles = pubchem.get('smiles')
                    if smiles:
                        return smiles

        except Exception:
            pass

        return None

    async def _search_compound_name(self, name: str) -> Optional[str]:
        """Search for compound by name via BioBTree.

        Uses PubChem search (which has SMILES) rather than ChEMBL.
        """
        try:
            await self.biobtree.connect()

            # Search PubChem by name - returns SMILES directly
            result = await self.biobtree.search([name], dataset="pubchem")
            results = result.get('results', {}).get('results', [])

            for r in results:
                if isinstance(r, dict):
                    pubchem = r.get('pubchem', {})
                    smiles = pubchem.get('smiles')
                    if smiles:
                        return smiles

        except Exception:
            pass

        return None


def _format_compound_similarity_result(result: ToolResult) -> str:
    """
    Format compound similarity result for agent display.

    Args:
        result: ToolResult from compound similarity search

    Returns:
        Formatted string for agent
    """
    if not result.success:
        return f"Error: {result.error}"

    data = result.data
    query = data.get('query_compound', {})
    similar = data.get('similar_compounds', [])
    props = query.get('properties', {})

    lines = [
        f"## Compound Similarity Search Results",
        f"",
        f"**Query Compound**:",
        f"- SMILES: `{query.get('smiles', 'N/A')}`",
        f"- Resolved from: {query.get('resolved_from', 'unknown')}",
    ]

    if props:
        lines.extend([
            f"- Molecular Weight: {props.get('molecular_weight', 'N/A')} Da",
            f"- LogP: {props.get('logp', 'N/A')}",
            f"- H-Bond Donors/Acceptors: {props.get('num_h_donors', 'N/A')}/{props.get('num_h_acceptors', 'N/A')}",
        ])

    lines.extend([
        f"",
        f"**Similar Compounds** ({len(similar)} found, min similarity: {data.get('min_similarity', 0.5)}):",
        f""
    ])

    for i, compound in enumerate(similar[:10], 1):
        schembl_id = compound.get('surechembl_id', 'Unknown')
        score = compound.get('score', 0)
        smiles = compound.get('smiles', 'N/A')
        mw = compound.get('molecular_weight', 'N/A')

        # Truncate long SMILES
        smiles_display = smiles[:50] + "..." if len(smiles) > 50 else smiles

        lines.append(f"{i}. **{schembl_id}** (similarity: {score:.3f})")
        lines.append(f"   SMILES: `{smiles_display}`")
        if mw and mw != 'N/A':
            lines.append(f"   MW: {mw:.1f} Da")
        lines.append("")

    lines.extend([
        f"*Method: {data.get('method', 'Morgan fingerprint')}*",
        f"*Database: {data.get('database', 'SureChEMBL')}*"
    ])

    return "\n".join(lines)
