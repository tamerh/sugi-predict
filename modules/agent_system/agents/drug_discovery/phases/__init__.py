"""Drug Discovery Agent Phases.

The six-phase reasoning loop:
1. Understand - Parse user intent (FUTURE)
2. Gather - Coordinate path execution
3. Score - Evidence scoring and pattern detection
4. Reason - LLM reasoning (FUTURE)
5. Follow-up - Qdrant validation (FUTURE)
6. Synthesize - Response synthesis (FUTURE)
"""

from .gather import GatherPhase, GatherOptions, GatherResult
from .score import (
    EvidenceScorer,
    ScoringResult,
    ScoredEntity,
    EvidenceBreakdown,
    EntityType,
    ConfidenceLevel,
)

__all__ = [
    # Phase 2: Gather
    "GatherPhase",
    "GatherOptions",
    "GatherResult",
    # Phase 3: Score
    "EvidenceScorer",
    "ScoringResult",
    "ScoredEntity",
    "EvidenceBreakdown",
    "EntityType",
    "ConfidenceLevel",
]
