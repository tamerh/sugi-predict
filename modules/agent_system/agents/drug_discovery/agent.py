"""Drug Discovery Agent for finding drugs, targets, and mechanisms."""

import re
from pathlib import Path
from typing import Optional

from ..base import Agent, AgentContext, AgentResult
from ...llm.base import LLMProvider
from ...tools.registry import ToolRegistry


class DrugDiscoveryAgent(Agent):
    """
    Agent specialized for drug discovery queries.

    Handles queries like:
    - "What drugs target EGFR?"
    - "Find inhibitors for TP53"
    - "What compounds bind to BRCA1?"
    - "Show me drugs for these genes: EGFR, KRAS, BRAF"
    """

    AGENT_DIR = Path(__file__).parent

    # Class-level cache for prompt (loaded once, not per instance)
    _cached_prompt: Optional[str] = None

    # Keywords that suggest drug discovery queries
    DRUG_KEYWORDS = [
        "drug", "drugs", "compound", "compounds", "molecule", "molecules",
        "inhibitor", "inhibitors", "target", "targets", "targeting",
        "therapeutic", "treatment", "therapy", "medicine",
        "chembl", "drugbank", "pharmaceutical",
        "mechanism", "action", "binding", "bind", "binds",
        "agonist", "antagonist", "modulator", "blocker"
    ]

    # Drug-related patterns
    DRUG_PATTERNS = [
        r"chembl\d+",      # ChEMBL compound ID
        r"db\d{5}",        # DrugBank ID
        r"what.+drug",     # "what drugs..."
        r"find.+drug",     # "find drugs..."
        r"drug.+for",      # "drugs for..."
        r"target.+by",     # "targeted by..."
        r"inhibit",        # inhibitor-related
    ]

    def __init__(
        self,
        llm: LLMProvider,
        tool_registry: ToolRegistry,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize Drug Discovery Agent.

        Args:
            llm: LLM provider
            tool_registry: Tool registry
            system_prompt: Optional custom system prompt
        """
        # Load prompt from file if not provided (cached at class level)
        if system_prompt is None:
            if DrugDiscoveryAgent._cached_prompt is None:
                prompt_file = self.AGENT_DIR / "prompt.txt"
                if prompt_file.exists():
                    DrugDiscoveryAgent._cached_prompt = prompt_file.read_text()
            system_prompt = DrugDiscoveryAgent._cached_prompt

        super().__init__(
            name="drug_discovery",
            description="Finds drugs, compounds, and therapeutic targets for genes/proteins",
            llm=llm,
            tool_registry=tool_registry,
            tools=["biobtree_query"],
            max_iterations=3,
            system_prompt=system_prompt
        )

    def _default_system_prompt(self) -> str:
        """Return default system prompt for drug discovery."""
        return """You are a drug discovery assistant. Your role is to help users find drugs, compounds, and therapeutic relationships for biological targets.

## Your Capabilities
You can find:
- Drugs/compounds that target specific genes or proteins
- Drug targets for known compounds
- Mechanism of action relationships
- ChEMBL compound information

## BioBTree Query Syntax for Drug Discovery

### Gene/Protein to Drugs (most common)
To find drugs targeting a gene, chain through the full ChEMBL path:
```
GENE >> ensembl >> uniprot >> chembl_target_component >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule
```

Examples:
- Single gene: "EGFR >> ensembl >> uniprot >> chembl_target_component >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule"
- Multiple genes: "EGFR,KRAS,BRAF >> ensembl >> uniprot >> chembl_target_component >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule"

### Gene to ChEMBL Targets only (faster, no molecules)
If you just need to confirm drug target status:
```
GENE >> ensembl >> uniprot >> chembl_target_component >> chembl_target
```

### Protein to Drugs (if starting with UniProt ID)
```
P00533 >> uniprot >> chembl_target_component >> chembl_target >> chembl_assay >> chembl_activity >> chembl_molecule
```

## Important Rules
1. For gene symbols (EGFR, TP53), start from ensembl
2. For UniProt IDs (P00533), start from uniprot
3. The ChEMBL chain is: target_component → target → assay → activity → molecule
4. chembl_molecule contains the actual drug/compound information

## Response Guidelines
- List the drugs/compounds found with their ChEMBL IDs
- If no drugs found, suggest the target may not have known drug interactions
- For multiple targets, summarize which have drug hits"""

    def can_handle(self, query: str) -> float:
        """
        Determine confidence that this query is a drug discovery request.

        Args:
            query: User query

        Returns:
            Confidence score 0-1
        """
        query_lower = query.lower()
        score = 0.0

        # Check for drug keywords (strong signal)
        drug_keyword_count = 0
        for keyword in self.DRUG_KEYWORDS:
            if keyword in query_lower:
                drug_keyword_count += 1

        if drug_keyword_count >= 2:
            score += 0.5
        elif drug_keyword_count == 1:
            score += 0.3

        # Check for drug-related patterns
        for pattern in self.DRUG_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                score += 0.3
                break

        # Check for ChEMBL IDs (very strong signal)
        if re.search(r'chembl\d+', query_lower, re.IGNORECASE):
            score += 0.4

        # Check for common gene symbols with drug context
        common_drug_targets = ["egfr", "kras", "braf", "her2", "vegf", "bcr-abl", "jak", "mtor"]
        for target in common_drug_targets:
            if target in query_lower:
                score += 0.1
                break

        # Cap at 1.0
        return min(score, 1.0)

    def _format_observation(self, data: dict) -> str:
        """
        Format BioBTree drug discovery result for clearer observation.

        Args:
            data: Tool result data

        Returns:
            Formatted string
        """
        if not isinstance(data, dict):
            return str(data)

        mode = data.get("mode", "unknown")
        stats = data.get("stats", {})
        mappings = data.get("mappings", [])

        lines = [f"Mode: {mode}"]

        if stats:
            mapped = stats.get('mapped', 0)
            total = stats.get('total_terms', 0)
            total_targets = stats.get('total_targets', 0)
            lines.append(f"Stats: {mapped}/{total} genes mapped, {total_targets} drug hits")

        if mappings:
            lines.append("Drug mappings:")
            for m in mappings[:10]:
                if m.get("error"):
                    continue
                term = m.get("term") or m.get("input", "?")
                targets = m.get("targets", [])
                if targets:
                    # Show up to 5 drug IDs
                    drug_ids = [t.get("id", "?") for t in targets[:5]]
                    more = len(targets) - 5 if len(targets) > 5 else 0
                    drug_list = ", ".join(drug_ids)
                    if more > 0:
                        drug_list += f" (+{more} more)"
                    lines.append(f"  {term} -> {drug_list}")
                else:
                    lines.append(f"  {term} -> (no drugs found)")

        return "\n".join(lines)
