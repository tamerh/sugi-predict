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
            tools=["disease_drug_discovery", "biobtree_query"],  # Specialized + general tools
            max_iterations=3,  # Reduced - specialized tool does the work
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

    def _format_disease_drug_result(self, data: dict) -> str:
        """
        Format disease_drug_discovery tool output for observation.

        Args:
            data: Tool result with direct_indications and gene-based targets

        Returns:
            Formatted string for LLM observation
        """
        lines = []
        disease = data.get("disease", "Unknown")
        lines.append(f"Disease Drug Discovery Results for: {disease}")
        lines.append("=" * 50)

        # Direct indications
        direct = data.get("direct_indications", {})
        direct_drugs = direct.get("drugs", [])
        lines.append(f"\n## Direct Indications ({len(direct_drugs)} drugs with Phase 3+)")

        if direct_drugs:
            lines.append("| Drug Name | ChEMBL ID | Phase | Mechanism |")
            lines.append("|-----------|-----------|-------|-----------|")
            for drug in direct_drugs[:15]:  # Limit to 15
                name = drug.get("name", drug.get("id", "?"))
                drug_id = drug.get("id", "?")
                phase = drug.get("indication_phase", "?")
                mechanism = drug.get("mechanism", "")[:50]  # Truncate
                lines.append(f"| {name} | {drug_id} | {phase} | {mechanism} |")
            if len(direct_drugs) > 15:
                lines.append(f"... and {len(direct_drugs) - 15} more drugs")
        else:
            lines.append("No drugs found with Phase 3+ indications for this disease.")

        # Format gene-based sources (GWAS, ClinVar, Reactome, UniProt) - ChEMBL drugs
        source_configs = [
            ("gwas_targets", "GWAS Targets (ChEMBL)", "Genetically associated genes"),
            ("clinvar_targets", "ClinVar Targets (ChEMBL)", "Genes with disease-associated variants"),
            ("reactome_targets", "Reactome Targets (ChEMBL)", "Genes in disease-related pathways"),
            ("uniprot_targets", "UniProt Targets (ChEMBL)", "Proteins annotated with disease"),
        ]

        for source_key, source_name, source_desc in source_configs:
            source_data = data.get(source_key, {})
            source_genes = source_data.get("genes", [])
            drugs_by_gene = source_data.get("drugs_by_gene", {})
            total_drugs = source_data.get("drug_count", 0)

            # Only show sources with results
            if source_genes and total_drugs > 0:
                lines.append(f"\n## {source_name} ({len(source_genes)} genes, {total_drugs} drugs)")
                lines.append(f"*{source_desc}*")
                lines.append(f"Genes: {', '.join(source_genes)}")

                if drugs_by_gene:
                    lines.append("| Target Gene | Drug Name | ChEMBL ID | Drug Phase |")
                    lines.append("|-------------|-----------|-----------|------------|")
                    shown = 0
                    for gene, drugs in drugs_by_gene.items():
                        for drug in drugs[:3]:  # Max 3 drugs per gene
                            if shown >= 15:  # Max 15 rows total per source
                                break
                            name = drug.get("name", drug.get("id", "?"))
                            drug_id = drug.get("id", "?")
                            phase = drug.get("drug_phase", "?")
                            lines.append(f"| {gene} | {name} | {drug_id} | {phase} |")
                            shown += 1
                        if shown >= 15:
                            break
                    remaining = total_drugs - shown
                    if remaining > 0:
                        lines.append(f"... and {remaining} more drug-gene associations")

        # Format PubChem FDA-approved drugs
        pubchem_data = data.get("pubchem_targets", {})
        pubchem_genes = pubchem_data.get("genes", [])
        pubchem_drugs_by_gene = pubchem_data.get("drugs_by_gene", {})
        pubchem_total_drugs = pubchem_data.get("drug_count", 0)

        if pubchem_genes and pubchem_total_drugs > 0:
            lines.append(f"\n## PubChem FDA-Approved Drugs ({len(pubchem_genes)} genes, {pubchem_total_drugs} drugs)")
            lines.append(f"*FDA-approved drugs from PubChem bioactivity data targeting {disease}-associated genes*")

            # Show drugs grouped by gene with actual CIDs
            if pubchem_drugs_by_gene:
                for gene, drugs in pubchem_drugs_by_gene.items():
                    drug_count = len(drugs)
                    # Get sample CIDs
                    sample_cids = [d.get("cid", d.get("id", "?")) for d in drugs[:5]]
                    cids_str = ", ".join(f"CID:{cid}" for cid in sample_cids)
                    if drug_count > 5:
                        cids_str += f" (+{drug_count - 5} more)"
                    lines.append(f"- **{gene}**: {drug_count} FDA-approved drugs - {cids_str}")

                # Also show detailed table for first few
                lines.append("\nSample drugs with details:")
                lines.append("| Target Gene | PubChem CID | Formula |")
                lines.append("|-------------|-------------|---------|")
                shown = 0
                for gene, drugs in pubchem_drugs_by_gene.items():
                    for drug in drugs[:2]:  # Max 2 drugs per gene in table
                        if shown >= 10:
                            break
                        cid = drug.get("cid", drug.get("id", "?"))
                        formula = drug.get("molecular_formula", "")
                        lines.append(f"| {gene} | {cid} | {formula} |")
                        shown += 1
                    if shown >= 10:
                        break

                lines.append(f"\n*Note: Use PubChem CID to lookup drug details at pubchem.ncbi.nlm.nih.gov*")

        # Format Reactome pathways
        reactome_data = data.get("reactome_pathways", {})
        reactome_genes = reactome_data.get("genes", [])
        pathways_by_gene = reactome_data.get("pathways_by_gene", {})
        total_pathways = reactome_data.get("pathway_count", 0)

        if reactome_genes and total_pathways > 0:
            lines.append(f"\n## Reactome Pathways ({len(reactome_genes)} genes, {total_pathways} pathways)")
            lines.append(f"*Biological pathways involving {disease}-associated genes*")
            lines.append(f"**INCLUDE THIS DATA IN YOUR RESPONSE - list each gene with its pathways below:**")

            for gene, pathways in pathways_by_gene.items():
                # Show pathway names for each gene
                disease_pathways = [p for p in pathways if p.get("is_disease_pathway")]
                other_pathways = [p for p in pathways if not p.get("is_disease_pathway")]

                pathway_names = []
                # Prioritize disease pathways
                for p in disease_pathways[:3]:
                    pathway_names.append(f"**{p.get('name', p.get('id'))}** (disease)")
                for p in other_pathways[:2]:
                    name = p.get('name', p.get('id'))
                    if len(name) > 50:
                        name = name[:47] + "..."
                    pathway_names.append(name)

                more_count = len(pathways) - len(pathway_names)
                pathways_str = ", ".join(pathway_names)
                if more_count > 0:
                    pathways_str += f" (+{more_count} more)"

                lines.append(f"- **{gene}**: {pathways_str}")

        # Summary
        summary = data.get("summary", {})
        lines.append(f"\n## Summary")
        lines.append(f"- Direct indication drugs (ChEMBL): {summary.get('direct_indication_drugs', 0)}")
        lines.append(f"- Total target genes: {summary.get('total_target_genes', 0)}")
        lines.append(f"- Total gene-based drugs (ChEMBL): {summary.get('total_gene_based_drugs', 0)}")
        lines.append(f"- FDA-approved drugs (PubChem): {summary.get('pubchem_fda_drugs', 0)}")
        lines.append(f"- Reactome pathways: {summary.get('reactome_pathways', 0)}")
        lines.append(f"- Sources with results: {summary.get('sources_with_results', [])}")

        return "\n".join(lines)

    def _format_observation(self, data: dict) -> str:
        """
        Format tool result for clearer observation.

        Handles:
        - disease_drug_discovery tool output
        - biobtree_query tool output

        Args:
            data: Tool result data

        Returns:
            Formatted string
        """
        if not isinstance(data, dict):
            return str(data)

        # Handle disease_drug_discovery tool output
        if "direct_indications" in data or "gwas_targets" in data:
            return self._format_disease_drug_result(data)

        lines = []

        # Handle lite mode response (results_lite structure)
        if "results_lite" in data:
            lite = data["results_lite"]
            stats = lite.get("stats", {})
            mappings = lite.get("mappings", [])

            lines.append("Mode: lite")
            if stats:
                mapped = stats.get('mapped', 0)
                total = stats.get('total_terms', 0)
                total_targets = stats.get('total_targets', 0)
                lines.append(f"Stats: {mapped}/{total} terms mapped, {total_targets} drug hits")

            if mappings:
                lines.append("Drug mappings:")
                for m in mappings[:10]:
                    if m.get("error"):
                        continue
                    term = m.get("term") or m.get("input", "?")
                    targets = m.get("targets", [])
                    if targets:
                        drug_ids = [t.get("id", "?") for t in targets[:5]]
                        more = len(targets) - 5 if len(targets) > 5 else 0
                        drug_list = ", ".join(drug_ids)
                        if more > 0:
                            drug_list += f" (+{more} more)"
                        lines.append(f"  {term} -> {drug_list}")
                    else:
                        lines.append(f"  {term} -> (no drugs found)")

        # Handle full mode response (results structure)
        elif "results" in data:
            results = data.get("results", {})
            # Handle both nested (results.results) and flat (results as list) structures
            if isinstance(results, list):
                inner_results = results
            else:
                inner_results = results.get("results", [])

            lines.append("Mode: full")

            if inner_results:
                # Extract drugs grouped by source
                drugs_by_source = {}
                total_drugs = 0
                is_direct_indication_query = False

                for r in inner_results:
                    source = r.get("source", {})
                    source_name = source.get("keyword") or source.get("identifier", "?")
                    source_dataset = source.get("dataset", "")
                    targets = r.get("targets", [])

                    # Detect if this is a direct indication query (PATH 1)
                    # In PATH 1, source is EFO disease, targets are chembl_molecule
                    if source_dataset == "efo" or source_name.startswith("EFO:"):
                        is_direct_indication_query = True

                    if source_name not in drugs_by_source:
                        drugs_by_source[source_name] = []

                    for t in targets:
                        drug_id = t.get("identifier", "?")
                        target_dataset = t.get("dataset", "")

                        # Drug info location depends on API:
                        # - gRPC: t.chembl.molecule
                        # - REST: t.Attributes.Chembl.molecule
                        chembl_data = t.get("chembl", {})
                        if not chembl_data:
                            attrs = t.get("Attributes", {})
                            chembl_data = attrs.get("Chembl", {}) or attrs.get("chembl", {})
                        drug_info = chembl_data.get("molecule", {})

                        # Extract drug name from altNames
                        drug_name = None
                        alt_names = drug_info.get("altNames", [])
                        if alt_names and isinstance(alt_names, list):
                            for name in alt_names:
                                if name and len(name) > 2:
                                    drug_name = name
                                    break

                        drug_phase = drug_info.get("highestDevelopmentPhase", "N/A")
                        drug_type = drug_info.get("type", "")
                        mechanism = drug_info.get("mechanism", {})
                        mechanism_desc = ""
                        if mechanism:
                            mechanism_desc = mechanism.get("desc", "") or mechanism.get("action", "")

                        # Get indications and find indication-specific phase
                        indications = drug_info.get("indications", [])
                        indication_str = ""
                        indication_phase = None

                        if indications:
                            # For direct indication queries, find the matching indication
                            for ind in indications:
                                ind_name = ind.get("efoName", "")
                                ind_phase = ind.get("highestDevelopmentPhase")

                                # Check if this indication matches the query disease
                                if is_direct_indication_query and source_name.lower() in ind_name.lower():
                                    indication_phase = ind_phase
                                    indication_str = f"{ind_name} (Phase {ind_phase})"
                                    break

                            # If no exact match, show first 2 indications
                            if not indication_str:
                                indication_names = [
                                    f"{ind.get('efoName', '')} (P{ind.get('highestDevelopmentPhase', '?')})"
                                    for ind in indications[:2]
                                    if ind.get("efoName")
                                ]
                                if indication_names:
                                    indication_str = ", ".join(indication_names)

                        drugs_by_source[source_name].append({
                            "id": drug_id,
                            "name": drug_name,
                            "drug_phase": drug_phase,
                            "indication_phase": indication_phase,
                            "type": drug_type,
                            "indication": indication_str,
                            "mechanism": mechanism_desc
                        })
                        total_drugs += 1

                lines.append(f"Found {total_drugs} drugs across {len(drugs_by_source)} sources")

                if is_direct_indication_query:
                    lines.append("Query type: Direct Disease Indication (PATH 1)")
                    lines.append("NOTE: Check indication_phase for disease-specific approval status")

                # Show drugs grouped by source
                for source, drugs in drugs_by_source.items():
                    lines.append(f"\n{source} ({len(drugs)} drugs):")

                    # Sort by indication_phase (approved first) if available
                    sorted_drugs = sorted(
                        drugs,
                        key=lambda d: (
                            -(d.get("indication_phase") or 0),  # Higher indication phase first
                            -(d.get("drug_phase") if d.get("drug_phase") != "N/A" else 0)
                        )
                    )

                    for drug in sorted_drugs[:8]:  # Show top 8 per source
                        name_str = drug["name"] if drug["name"] else drug["id"]

                        # Show indication-specific phase if available (important for PATH 1)
                        if drug.get("indication_phase") is not None:
                            phase_str = f"[Indication Phase {drug['indication_phase']}]"
                        elif drug["drug_phase"] != "N/A":
                            phase_str = f"[Drug Phase {drug['drug_phase']}]"
                        else:
                            phase_str = ""

                        # Build the line
                        line_parts = [f"  - {name_str} ({drug['id']}) {phase_str}"]
                        if drug["mechanism"]:
                            line_parts.append(f"Mechanism: {drug['mechanism']}")
                        if drug["indication"] and not drug.get("indication_phase"):
                            line_parts.append(f"Indications: {drug['indication']}")

                        lines.append(" | ".join(line_parts))

                    if len(drugs) > 8:
                        lines.append(f"  ... and {len(drugs) - 8} more")

            else:
                lines.append("No drugs found")

        # Fallback for other formats
        else:
            mode = data.get("mode", "unknown")
            stats = data.get("stats", {})
            mappings = data.get("mappings", [])

            lines.append(f"Mode: {mode}")

            if stats:
                mapped = stats.get('mapped', 0)
                total = stats.get('total_terms', 0)
                total_targets = stats.get('total_targets', 0)
                lines.append(f"Stats: {mapped}/{total} terms mapped, {total_targets} drug hits")

            if mappings:
                lines.append("Drug mappings:")
                for m in mappings[:10]:
                    if m.get("error"):
                        continue
                    term = m.get("term") or m.get("input", "?")
                    targets = m.get("targets", [])
                    if targets:
                        drug_ids = [t.get("id", "?") for t in targets[:5]]
                        more = len(targets) - 5 if len(targets) > 5 else 0
                        drug_list = ", ".join(drug_ids)
                        if more > 0:
                            drug_list += f" (+{more} more)"
                        lines.append(f"  {term} -> {drug_list}")
                    else:
                        lines.append(f"  {term} -> (no drugs found)")

        return "\n".join(lines)
