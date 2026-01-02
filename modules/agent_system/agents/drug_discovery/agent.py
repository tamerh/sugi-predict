"""Drug Discovery Agent - Six-Phase Reasoning Loop.

This agent orchestrates the drug discovery workflow directly using phases,
rather than delegating to a mega-tool. The agent IS the orchestrator.

Six-Phase Loop:
1. Understand - Parse user intent (detect disease query vs ad-hoc)
2. Gather - Run BioBTree paths in parallel (GatherPhase)
3. Score - Evidence scoring and pattern detection (EvidenceScorer)
4. Reason - LLM reasoning about results
5. Follow-up - Qdrant validation (future)
6. Synthesize - Generate final response
"""

import re
from pathlib import Path
from typing import Optional, Dict, Any, List

from ..base import Agent, AgentContext, AgentResult, AgentStatus
from ...llm.base import LLMProvider, Message
from ...tools.registry import ToolRegistry
from ...core.config import get_config
from ...integrations.biobtree_client import create_biobtree_client

# Import phases
from .phases import GatherPhase, GatherOptions, EvidenceScorer


class DrugDiscoveryAgent(Agent):
    """
    Agent specialized for drug discovery queries.

    Uses phase-based orchestration for disease drug queries:
    - "What drugs for glioblastoma?" → Phase-based (Gather → Score → Synthesize)
    - "What is EGFR?" → ReAct loop with biobtree_query tool

    Handles queries like:
    - "What drugs for glioblastoma?"
    - "Find treatments for type 2 diabetes"
    - "What drugs target EGFR?"
    - "Show me drugs for breast cancer"
    """

    AGENT_DIR = Path(__file__).parent

    # Class-level cache for prompt
    _cached_prompt: Optional[str] = None

    # Disease query patterns (trigger phase-based flow)
    DISEASE_PATTERNS = [
        r"drugs?\s+for\s+",           # "drugs for X"
        r"treatment[s]?\s+for\s+",    # "treatments for X"
        r"therap(?:y|ies)\s+for\s+",  # "therapy for X"
        r"what\s+drugs?\s+",          # "what drugs..."
        r"find\s+drugs?\s+",          # "find drugs..."
        r"compounds?\s+for\s+",       # "compounds for X"
    ]

    # Disease keywords (boost confidence)
    DISEASE_KEYWORDS = [
        "cancer", "tumor", "carcinoma", "lymphoma", "leukemia", "melanoma",
        "diabetes", "alzheimer", "parkinson", "huntington",
        "glioblastoma", "glioma", "neuroblastoma",
        "arthritis", "lupus", "sclerosis", "fibrosis",
        "asthma", "copd", "hypertension", "obesity",
        "hiv", "hepatitis", "tuberculosis", "malaria",
        "disease", "disorder", "syndrome", "condition"
    ]

    # Drug keywords (for routing confidence)
    DRUG_KEYWORDS = [
        "drug", "drugs", "compound", "compounds", "molecule", "molecules",
        "inhibitor", "inhibitors", "target", "targets", "targeting",
        "therapeutic", "treatment", "therapy", "medicine",
        "chembl", "drugbank", "pharmaceutical",
        "mechanism", "action", "binding", "bind", "binds",
        "agonist", "antagonist", "modulator", "blocker"
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
            llm: LLM provider for reasoning phases
            tool_registry: Tool registry (for ad-hoc queries)
            system_prompt: Optional custom system prompt
        """
        # Load prompt from file if not provided
        if system_prompt is None:
            if DrugDiscoveryAgent._cached_prompt is None:
                prompt_file = self.AGENT_DIR / "prompt.txt"
                if prompt_file.exists():
                    DrugDiscoveryAgent._cached_prompt = prompt_file.read_text()
            system_prompt = DrugDiscoveryAgent._cached_prompt

        super().__init__(
            name="drug_discovery",
            description="Finds drugs, compounds, and therapeutic targets for diseases and genes",
            llm=llm,
            tool_registry=tool_registry,
            # Tools for ad-hoc queries (ReAct fallback)
            tools=["biobtree_query", "protein_similarity_search", "compound_similarity_search"],
            max_iterations=3,
            system_prompt=system_prompt
        )

        # Create BioBTree client for phase-based queries
        config = get_config()
        self._biobtree = create_biobtree_client(config.integrations.biobtree)

        # Initialize phases
        self._gather_phase = GatherPhase(self._biobtree)
        self._scorer = EvidenceScorer()

    def _default_system_prompt(self) -> str:
        """Return default system prompt for drug discovery."""
        return """You are a drug discovery assistant. You help users find drugs, compounds, and therapeutic relationships for diseases and biological targets.

When presented with drug discovery results, synthesize the information into a clear, actionable response:
1. Highlight the most promising drugs (highest evidence scores)
2. Explain the evidence sources (direct indications, GWAS, ClinVar, etc.)
3. Note any patterns (novel targets, therapeutic gaps)
4. Suggest next steps if appropriate

Be concise but comprehensive. Focus on clinically relevant insights."""

    def _is_disease_query(self, query: str) -> tuple[bool, Optional[str]]:
        """
        Detect if query is a disease drug discovery request.

        Returns:
            Tuple of (is_disease_query, extracted_disease_name)
        """
        query_lower = query.lower()

        # First, try to find "for DISEASE" pattern (most reliable)
        for_match = re.search(r'\bfor\s+([a-z0-9\s\-]+?)(?:\?|$|\.)', query_lower)
        if for_match:
            disease = for_match.group(1).strip()
            # Check if it looks like a disease (contains disease keyword or is simple noun phrase)
            if disease and len(disease) > 2:
                return True, disease

        # Check for disease query patterns like "drugs for X", "what drugs X"
        for pattern in self.DISEASE_PATTERNS:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                # Look for "for DISEASE" after the pattern
                remainder = query_lower[match.end():].strip()
                # Try to find "for X" in remainder
                for_in_remainder = re.search(r'\bfor\s+([a-z0-9\s\-]+?)(?:\?|$|\.)', remainder)
                if for_in_remainder:
                    disease = for_in_remainder.group(1).strip()
                    if disease:
                        return True, disease
                # Otherwise take the remainder (for patterns like "drugs for X")
                disease = re.split(r'[?.!]', remainder)[0].strip()
                if disease and len(disease) > 2:
                    return True, disease

        # Check for disease keywords without explicit pattern
        for keyword in self.DISEASE_KEYWORDS:
            if keyword in query_lower:
                # Try to extract the disease context
                # Look for "X disease" or "X cancer" patterns
                pattern = rf'(\w+\s+)?{keyword}'
                match = re.search(pattern, query_lower)
                if match:
                    disease = match.group(0).strip()
                    return True, disease

        return False, None

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

        # Check for disease query patterns (strong signal)
        is_disease, _ = self._is_disease_query(query)
        if is_disease:
            score += 0.5

        # Check for drug keywords
        drug_keyword_count = sum(1 for kw in self.DRUG_KEYWORDS if kw in query_lower)
        if drug_keyword_count >= 2:
            score += 0.3
        elif drug_keyword_count == 1:
            score += 0.2

        # Check for disease keywords
        disease_keyword_count = sum(1 for kw in self.DISEASE_KEYWORDS if kw in query_lower)
        if disease_keyword_count >= 1:
            score += 0.2

        # Check for ChEMBL IDs
        if re.search(r'chembl\d+', query_lower, re.IGNORECASE):
            score += 0.3

        return min(score, 1.0)

    async def run(
        self,
        query: str,
        context: Optional[AgentContext] = None
    ) -> AgentResult:
        """
        Execute agent using phase-based or ReAct approach.

        For disease queries: Uses six-phase loop (Gather → Score → Synthesize)
        For ad-hoc queries: Falls back to ReAct loop with tools

        Args:
            query: User query
            context: Optional execution context

        Returns:
            Agent execution result
        """
        context = context or AgentContext()

        # Phase 1: Understand - Detect query type
        is_disease, disease_name = self._is_disease_query(query)

        if is_disease and disease_name:
            # Use phase-based flow for disease queries
            return await self._run_phase_based(query, disease_name, context)
        else:
            # Fall back to ReAct loop for ad-hoc queries
            return await super().run(query, context)

    async def _run_phase_based(
        self,
        query: str,
        disease: str,
        context: AgentContext
    ) -> AgentResult:
        """
        Execute six-phase drug discovery workflow.

        Args:
            query: Original user query
            disease: Extracted disease name
            context: Execution context

        Returns:
            AgentResult with synthesized response
        """
        reasoning = []
        tool_calls = []

        try:
            # ========================================
            # Phase 2: Gather - Run BioBTree paths
            # ========================================
            reasoning.append(f"Phase 2: Gathering data for disease '{disease}'")

            gather_options = GatherOptions(
                include_gwas=True,
                include_clinvar=True,
                include_pubchem=True,
                include_reactome=True,
                include_clinical_trials=True,
                min_indication_phase=3
            )

            gather_result = await self._gather_phase.execute(disease, gather_options)

            # Check if we got any data (direct_indications is always run)
            if not gather_result.direct_indications:
                return AgentResult(
                    status=AgentStatus.ERROR,
                    answer=f"Failed to gather data for '{disease}'",
                    reasoning=reasoning,
                    error="No data from direct indications query",
                    iterations=1
                )

            # Convert to dict for scoring
            gather_data = gather_result.to_dict()

            # Count successful paths
            paths_succeeded = 1  # direct_indications always runs
            if gather_result.gwas and gather_result.gwas.success:
                paths_succeeded += 1
            if gather_result.clinvar and gather_result.clinvar.success:
                paths_succeeded += 1
            if gather_result.pubchem and gather_result.pubchem.success:
                paths_succeeded += 1
            if gather_result.reactome and gather_result.reactome.success:
                paths_succeeded += 1
            if gather_result.clinical_trials and gather_result.clinical_trials.success:
                paths_succeeded += 1

            tool_calls.append({
                "tool": "GatherPhase",
                "args": {"disease": disease},
                "result": {
                    "paths_succeeded": paths_succeeded,
                    "total_drugs": len(gather_result.all_drugs),
                    "total_genes": len(gather_result.all_genes)
                },
                "success": True
            })

            reasoning.append(
                f"Gathered: {len(gather_result.all_drugs)} drugs, "
                f"{len(gather_result.all_genes)} genes from {paths_succeeded} paths"
            )

            # ========================================
            # Phase 3: Score - Evidence scoring
            # ========================================
            reasoning.append("Phase 3: Scoring evidence")

            scoring_result = self._scorer.score_results(gather_data)

            # Add scoring to gather_data
            gather_data["scoring"] = {
                "scored_drugs": [d.to_dict() for d in scoring_result.scored_drugs[:20]],
                "scored_genes": [g.to_dict() for g in scoring_result.scored_genes[:20]],
                "patterns": scoring_result.patterns,
                "summary": scoring_result.summary
            }

            tool_calls.append({
                "tool": "EvidenceScorer",
                "args": {},
                "result": {
                    "drugs_scored": len(scoring_result.scored_drugs),
                    "genes_scored": len(scoring_result.scored_genes),
                    "high_confidence_drugs": scoring_result.summary.get("high_confidence_drugs", 0),
                    "novel_targets": len(scoring_result.patterns.get("novel_targets", []))
                },
                "success": True
            })

            reasoning.append(
                f"Scored: {len(scoring_result.scored_drugs)} drugs, "
                f"{len(scoring_result.scored_genes)} genes. "
                f"Found {len(scoring_result.patterns.get('novel_targets', []))} novel targets."
            )

            # ========================================
            # Phase 6: Synthesize - Generate response
            # ========================================
            reasoning.append("Phase 6: Synthesizing response")

            # Format data for LLM
            formatted_data = self._format_disease_drug_result(gather_data)

            # Create synthesis prompt
            synthesis_prompt = f"""Based on the drug discovery results below, provide a comprehensive but concise response to the user's query: "{query}"

{formatted_data}

Instructions:
1. Start with the most clinically relevant findings (approved drugs, Phase 3+)
2. Highlight top drugs by evidence score
3. Mention key target genes and their drug coverage
4. Note any therapeutic gaps (high-evidence genes without drugs)
5. Include relevant clinical trial activity
6. Be specific with drug names and ChEMBL IDs where relevant

Keep the response focused and actionable."""

            # Call LLM for synthesis
            messages = [
                Message(role="system", content=self.system_prompt),
                Message(role="user", content=synthesis_prompt)
            ]

            response = await self.llm.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=1500
            )

            final_answer = response.content

            return AgentResult(
                status=AgentStatus.COMPLETED,
                answer=final_answer,
                reasoning=reasoning,
                tool_calls=tool_calls,
                iterations=1
            )

        except Exception as e:
            reasoning.append(f"Error: {str(e)}")
            return AgentResult(
                status=AgentStatus.ERROR,
                answer=f"An error occurred during drug discovery: {str(e)}",
                reasoning=reasoning,
                tool_calls=tool_calls,
                error=str(e),
                iterations=1
            )

    def _format_disease_drug_result(self, data: dict) -> str:
        """
        Format disease drug discovery result for LLM synthesis.

        Args:
            data: GatherResult.to_dict() with scoring added

        Returns:
            Formatted string for LLM
        """
        lines = []
        disease = data.get("disease", "Unknown")
        lines.append(f"# Drug Discovery Results for: {disease}")
        lines.append("=" * 50)

        # Direct indications
        direct = data.get("direct_indications", {})
        direct_drugs = direct.get("drugs", [])
        lines.append(f"\n## Direct Indications ({len(direct_drugs)} drugs with Phase 3+)")

        if direct_drugs:
            for drug in direct_drugs[:10]:
                name = drug.get("name", drug.get("id", "?"))
                drug_id = drug.get("id", "?")
                phase = drug.get("indication_phase", "?")
                mechanism = drug.get("mechanism", "")[:40]
                lines.append(f"- {name} ({drug_id}) - Phase {phase} - {mechanism}")
        else:
            lines.append("No direct indication drugs found.")

        # Gene-based targets (GWAS, ClinVar)
        for source_key, source_name in [
            ("gwas_targets", "GWAS Targets"),
            ("clinvar_targets", "ClinVar Targets")
        ]:
            source_data = data.get(source_key, {})
            genes = source_data.get("genes", [])
            drug_count = source_data.get("drug_count", 0)

            if genes and drug_count > 0:
                lines.append(f"\n## {source_name} ({len(genes)} genes, {drug_count} drugs)")
                lines.append(f"Genes: {', '.join(genes[:10])}")
                drugs_by_gene = source_data.get("drugs_by_gene", {})
                for gene, drugs in list(drugs_by_gene.items())[:5]:
                    drug_names = [d.get("name", d.get("id")) for d in drugs[:3]]
                    lines.append(f"- {gene}: {', '.join(drug_names)}")

        # PubChem FDA drugs
        pubchem = data.get("pubchem_targets", {})
        if pubchem.get("drug_count", 0) > 0:
            lines.append(f"\n## PubChem FDA-Approved ({pubchem.get('gene_count', 0)} genes, {pubchem.get('drug_count', 0)} drugs)")

        # Clinical Trials
        trials = data.get("clinical_trials", {})
        trial_list = trials.get("trials", [])
        if trial_list:
            by_phase = trials.get("by_phase", {})
            recruiting = trials.get("by_status", {}).get("RECRUITING", 0)
            lines.append(f"\n## Clinical Trials ({len(trial_list)} trials, {recruiting} recruiting)")
            for t in trial_list[:5]:
                nct = t.get("nct_id", "?")
                title = t.get("brief_title", "")[:50]
                phase = t.get("phase", "?")
                lines.append(f"- {nct}: {title}... (Phase {phase})")

        # Scoring results
        scoring = data.get("scoring", {})
        if scoring:
            scored_drugs = scoring.get("scored_drugs", [])
            scored_genes = scoring.get("scored_genes", [])
            patterns = scoring.get("patterns", {})

            if scored_drugs:
                lines.append(f"\n## Top Drugs by Evidence Score")
                for d in scored_drugs[:8]:
                    name = d.get("name", d.get("entity_id", "?"))
                    score = d.get("score", 0)
                    conf = d.get("confidence", "?")
                    sources = ", ".join(d.get("sources", []))
                    lines.append(f"- {name}: {score:.0f} ({conf}) - {sources}")

            if scored_genes:
                lines.append(f"\n## Top Genes by Evidence Score")
                for g in scored_genes[:8]:
                    name = g.get("name", g.get("entity_id", "?"))
                    score = g.get("score", 0)
                    conf = g.get("confidence", "?")
                    flags = ", ".join(g.get("flags", [])[:2])
                    lines.append(f"- {name}: {score:.0f} ({conf}) - {flags}")

            novel = patterns.get("novel_targets", [])
            if novel:
                lines.append(f"\n## Novel Targets (no drugs)")
                lines.append(f"{', '.join(novel[:10])}")

            gaps = patterns.get("gaps", [])
            if gaps:
                lines.append(f"\n## Therapeutic Gaps")
                for gap in gaps[:5]:
                    lines.append(f"- {gap}")

        # Summary
        summary = data.get("summary", {})
        lines.append(f"\n## Summary")
        lines.append(f"- Direct indication drugs: {summary.get('direct_indication_drugs', 0)}")
        lines.append(f"- Total target genes: {summary.get('total_target_genes', 0)}")
        lines.append(f"- Gene-based drugs: {summary.get('total_gene_based_drugs', 0)}")
        lines.append(f"- Clinical trials: {summary.get('clinical_trials', 0)}")

        return "\n".join(lines)

    def _format_observation(self, data: dict) -> str:
        """
        Format tool result for ReAct observation (ad-hoc queries).

        Args:
            data: Tool result data

        Returns:
            Formatted string
        """
        if not isinstance(data, dict):
            return str(data)

        lines = []

        # Handle lite mode response
        if "results_lite" in data:
            lite = data["results_lite"]
            stats = lite.get("stats", {})
            mappings = lite.get("mappings", [])

            lines.append("Mode: lite")
            if stats:
                lines.append(f"Stats: {stats.get('mapped', 0)}/{stats.get('total_terms', 0)} mapped")

            for m in mappings[:10]:
                if m.get("error"):
                    continue
                term = m.get("term") or m.get("input", "?")
                targets = m.get("targets", [])
                if targets:
                    target_ids = [t.get("id", "?") for t in targets[:5]]
                    lines.append(f"  {term} -> {', '.join(target_ids)}")

        # Handle full mode response
        elif "results" in data:
            results = data.get("results", {})
            inner = results.get("results", []) if isinstance(results, dict) else results
            lines.append("Mode: full")
            lines.append(f"Results: {len(inner)} mappings")

        return "\n".join(lines) if lines else str(data)[:500]
