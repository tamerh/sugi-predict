"""ID Mapping Agent for biological identifier mapping queries."""

import re
from pathlib import Path
from typing import Optional

from ..base import Agent, AgentContext, AgentResult
from ...llm.base import LLMProvider
from ...tools.registry import ToolRegistry


class IDMappingAgent(Agent):
    """
    Agent specialized for mapping biological identifiers between databases.

    Handles queries like:
    - "What is the UniProt ID for TP53?"
    - "Map BRCA1, TP53, EGFR to proteins"
    - "What gene encodes P04637?"
    - "What pathways is TP53 involved in?"
    - "What GO terms are associated with BRCA1?"
    """

    AGENT_DIR = Path(__file__).parent

    # Class-level cache for prompt (loaded once, not per instance)
    _cached_prompt: Optional[str] = None

    # Keywords that suggest ID mapping queries
    MAPPING_KEYWORDS = [
        "map", "mapping", "convert", "translate",
        "uniprot", "ensembl", "gene id", "protein id",
        "identifier", "accession",
        "what is the", "find the", "get the",
        "corresponds to", "encodes", "encoded by",
        # Pathway/GO keywords
        "pathway", "pathways", "reactome", "kegg",
        "go term", "gene ontology", "function", "process",
        "involved in", "participates", "associated with"
    ]

    # Database name patterns
    DATABASE_PATTERNS = [
        r"uniprot",
        r"ensembl",
        r"ensg\d+",  # Ensembl gene
        r"ensp\d+",  # Ensembl protein
        r"p\d{5}",   # UniProt accession
        r"chembl",
        r"reactome",
        r"hgnc",
        r"dbsnp",
        r"rs\d+",    # dbSNP variant
    ]

    def __init__(
        self,
        llm: LLMProvider,
        tool_registry: ToolRegistry,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize ID Mapping Agent.

        Args:
            llm: LLM provider
            tool_registry: Tool registry
            system_prompt: Optional custom system prompt
        """
        # Load prompt from file if not provided (cached at class level)
        if system_prompt is None:
            if IDMappingAgent._cached_prompt is None:
                prompt_file = self.AGENT_DIR / "prompt.txt"
                if prompt_file.exists():
                    IDMappingAgent._cached_prompt = prompt_file.read_text()
            system_prompt = IDMappingAgent._cached_prompt

        super().__init__(
            name="id_mapping",
            description="Maps biological identifiers between databases (gene IDs, protein IDs, pathways, GO terms)",
            llm=llm,
            tool_registry=tool_registry,
            tools=["biobtree_query"],
            max_iterations=3,
            system_prompt=system_prompt
        )

    def _default_system_prompt(self) -> str:
        """Return default system prompt for ID mapping."""
        return """You are a biological identifier mapping assistant. Your role is to help users map identifiers between different biological databases.

## Your Capabilities
You can map between these databases:
- Ensembl (gene IDs like ENSG00000141510)
- UniProt (protein IDs like P04637)
- ChEMBL (drug/compound targets)
- Reactome (pathways)
- GO (Gene Ontology)
- HGNC (gene symbols)
- dbSNP (variants like rs121912651)

## BioBTree Query Syntax
Use this format: "identifier >> source_dataset >> target_dataset"

Examples:
- Gene to protein: "TP53 >> ensembl >> uniprot"
- Protein to gene: "P04637 >> uniprot >> ensembl"
- Multiple genes: "TP53,BRCA1,EGFR >> ensembl >> uniprot"
- Gene to pathways: "TP53 >> ensembl >> uniprot >> reactome"
- Gene to GO terms: "TP53 >> ensembl >> uniprot >> go"
- Protein to pathways: "P04637 >> uniprot >> reactome"

## Important Rules
1. ALWAYS use the biobtree_query tool for mapping requests
2. For gene symbols (like TP53, BRCA1), start from ensembl dataset
3. For UniProt IDs (like P04637), start from uniprot dataset
4. For multiple identifiers, separate them with commas
5. Explain the mapping results clearly to the user

## Dataset Names
- ensembl - Gene IDs and symbols
- uniprot - Protein accessions
- chembl_target - Drug targets
- chembl_molecule - Drug compounds
- reactome - Biological pathways
- go - Gene Ontology terms
- dbsnp - Genetic variants
- hgnc - Gene nomenclature"""

    def can_handle(self, query: str) -> float:
        """
        Determine confidence that this query is an ID mapping request.

        Args:
            query: User query

        Returns:
            Confidence score 0-1
        """
        query_lower = query.lower()
        score = 0.0

        # Check for mapping keywords
        for keyword in self.MAPPING_KEYWORDS:
            if keyword in query_lower:
                score += 0.2
                break  # Only count once

        # Check for database patterns
        for pattern in self.DATABASE_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                score += 0.3
                break

        # Check for specific ID patterns (strong signal)
        if re.search(r'\b(ensg|ensp)\d+\b', query_lower, re.IGNORECASE):
            score += 0.4
        if re.search(r'\b[pqo]\d{5}\b', query_lower, re.IGNORECASE):
            score += 0.4
        if re.search(r'\brs\d+\b', query_lower, re.IGNORECASE):
            score += 0.4

        # Check for common gene symbols
        common_genes = ["tp53", "brca1", "brca2", "egfr", "kras", "myc", "pten"]
        for gene in common_genes:
            if gene in query_lower:
                score += 0.2
                break

        # Cap at 1.0
        return min(score, 1.0)

    def _format_observation(self, data: dict) -> str:
        """
        Format BioBTree result for clearer observation.

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
            lines.append(f"Stats: {stats.get('mapped', 0)} mapped, {stats.get('not_found', 0)} not found")

        if mappings:
            lines.append("Mappings:")
            for m in mappings[:10]:  # Limit to first 10
                # Skip error mappings
                if m.get("error"):
                    continue
                # Use term (original query) or fall back to input (resolved ID)
                term = m.get("term") or m.get("input", "?")
                resolved_id = m.get("input", "")
                targets = m.get("targets", [])
                if targets:
                    target_ids = [t.get("id", "?") for t in targets[:5]]
                    if term != resolved_id and resolved_id:
                        lines.append(f"  {term} ({resolved_id}) -> {', '.join(target_ids)}")
                    else:
                        lines.append(f"  {term} -> {', '.join(target_ids)}")

        return "\n".join(lines)
