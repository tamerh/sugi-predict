"""Base Path Classes for Drug Discovery.

Defines the abstract base class for all data gathering paths.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class PathResult:
    """Result from a single path execution."""
    path_name: str
    success: bool
    data: Dict[str, Any]
    drugs: List[Dict] = field(default_factory=list)
    genes: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path_name": self.path_name,
            "success": self.success,
            "data": self.data,
            "drugs": self.drugs,
            "genes": self.genes,
            "metadata": self.metadata,
            "error": self.error
        }


class BasePath(ABC):
    """
    Base class for all data gathering paths.

    Each path represents a specific query route for gathering drug discovery evidence.
    Examples:
    - DirectIndicationsPath: disease >> efo >> chembl_molecule
    - GWASPath: disease >> efo >> gwas >> ensembl >> drugs
    - ClinVarPath: disease >> mondo >> clinvar >> ensembl >> drugs
    """

    def __init__(self, biobtree_client, qdrant_client=None):
        """
        Initialize path with required clients.

        Args:
            biobtree_client: BioBTree client for database queries
            qdrant_client: Optional Qdrant client for vector search
        """
        self.biobtree = biobtree_client
        self.qdrant = qdrant_client

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Path identifier.

        Examples: 'direct_indications', 'gwas', 'clinvar', 'pubchem'
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of this path."""
        pass

    @property
    def requires_qdrant(self) -> bool:
        """Whether this path requires Qdrant client."""
        return False

    @abstractmethod
    async def execute(self, disease: str, **kwargs) -> PathResult:
        """
        Execute this path and return results.

        Args:
            disease: Disease name or ID to query
            **kwargs: Path-specific options

        Returns:
            PathResult with gathered data
        """
        pass

    def _create_result(
        self,
        success: bool,
        data: Dict[str, Any] = None,
        drugs: List[Dict] = None,
        genes: List[str] = None,
        metadata: Dict = None,
        error: str = None
    ) -> PathResult:
        """Helper to create PathResult with this path's name."""
        return PathResult(
            path_name=self.name,
            success=success,
            data=data or {},
            drugs=drugs or [],
            genes=genes or [],
            metadata=metadata or {},
            error=error
        )
