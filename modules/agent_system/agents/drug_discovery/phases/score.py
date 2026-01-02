"""
Phase 3: Evidence Scoring for Drug Discovery Agent.

This module provides evidence-based scoring for genes and drugs discovered
through multiple BioBTree paths (Phase 2: Gather). Entities appearing in
multiple sources receive higher confidence scores.

Scoring Philosophy:
- Multi-source evidence = higher confidence
- Clinical validation (Phase 4, trials) = highest weight
- Genetic associations (GWAS, ClinVar) = strong evidence
- Patent activity = emerging interest indicator
- Recency matters (active trials > completed)

Score Range: 0-100
- 70+ : High confidence (multiple validated sources)
- 40-69: Medium confidence (some validation)
- <40 : Low confidence (limited evidence, potentially novel)

Usage:
    from .phases import GatherPhase, EvidenceScorer

    gather = GatherPhase(biobtree_client)
    result = await gather.execute(disease="glioblastoma")

    scorer = EvidenceScorer()
    scoring = scorer.score_results(result.to_dict())
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum


class EntityType(Enum):
    """Type of scored entity."""
    DRUG = "drug"
    GENE = "gene"
    PROTEIN = "protein"


class ConfidenceLevel(Enum):
    """Confidence level based on score."""
    HIGH = "high"        # 70+
    MEDIUM = "medium"    # 40-69
    LOW = "low"          # <40


@dataclass
class EvidenceBreakdown:
    """Detailed breakdown of evidence sources contributing to score."""

    # Drug-specific evidence
    direct_indication: float = 0.0      # Phase-weighted (Phase 4=40, Phase 3=30, etc.)
    clinical_trials: float = 0.0        # Active trials boost score

    # Gene-specific evidence
    gwas: float = 0.0                   # GWAS association
    clinvar: float = 0.0                # ClinVar variant (pathogenic boost)
    reactome: float = 0.0               # Pathway membership
    uniprot: float = 0.0                # Protein annotation

    # Shared evidence
    pubchem_fda: float = 0.0            # FDA-approved in PubChem
    patents: float = 0.0                # Patent activity
    literature: float = 0.0             # PubMed mentions (future)

    # Bonuses
    multi_source_bonus: float = 0.0     # Appears in 3+ sources
    recency_bonus: float = 0.0          # Recent activity

    def total(self) -> float:
        """Calculate total score from all components."""
        return min(100.0, sum([
            self.direct_indication,
            self.clinical_trials,
            self.gwas,
            self.clinvar,
            self.reactome,
            self.uniprot,
            self.pubchem_fda,
            self.patents,
            self.literature,
            self.multi_source_bonus,
            self.recency_bonus
        ]))

    def sources(self) -> List[str]:
        """Get list of sources that contributed to score."""
        source_map = {
            "direct_indication": self.direct_indication,
            "clinical_trials": self.clinical_trials,
            "gwas": self.gwas,
            "clinvar": self.clinvar,
            "reactome": self.reactome,
            "uniprot": self.uniprot,
            "pubchem_fda": self.pubchem_fda,
            "patents": self.patents,
            "literature": self.literature
        }
        return [k for k, v in source_map.items() if v > 0]

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for JSON serialization."""
        return {
            "direct_indication": self.direct_indication,
            "clinical_trials": self.clinical_trials,
            "gwas": self.gwas,
            "clinvar": self.clinvar,
            "reactome": self.reactome,
            "uniprot": self.uniprot,
            "pubchem_fda": self.pubchem_fda,
            "patents": self.patents,
            "literature": self.literature,
            "multi_source_bonus": self.multi_source_bonus,
            "recency_bonus": self.recency_bonus,
            "total": self.total()
        }


@dataclass
class ScoredEntity:
    """A scored gene or drug with evidence breakdown."""

    entity_id: str                          # ChEMBL ID, gene symbol, etc.
    entity_type: EntityType                 # drug, gene, protein
    name: str                               # Human-readable name
    score: float                            # Total score (0-100)
    confidence: ConfidenceLevel             # High/Medium/Low
    breakdown: EvidenceBreakdown            # Detailed scoring
    sources: List[str]                      # List of evidence sources

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)  # e.g., "novel_target", "emerging"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "score": self.score,
            "confidence": self.confidence.value,
            "sources": self.sources,
            "source_count": len(self.sources),
            "breakdown": self.breakdown.to_dict(),
            "flags": self.flags,
            "metadata": self.metadata
        }


@dataclass
class ScoringResult:
    """Complete scoring results with patterns detected."""

    scored_drugs: List[ScoredEntity]
    scored_genes: List[ScoredEntity]
    patterns: Dict[str, List[str]]
    summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scored_drugs": [d.to_dict() for d in self.scored_drugs],
            "scored_genes": [g.to_dict() for g in self.scored_genes],
            "patterns": self.patterns,
            "summary": self.summary
        }


class EvidenceScorer:
    """
    Scores genes and drugs based on evidence from multiple sources.

    Usage:
        scorer = EvidenceScorer()
        result = scorer.score_results(disease_drug_result)

        # Access scored entities
        for drug in result.scored_drugs:
            print(f"{drug.name}: {drug.score} ({drug.confidence.value})")

        # Access detected patterns
        print(result.patterns["high_confidence"])
        print(result.patterns["novel_targets"])
    """

    # Scoring weights (configurable)
    WEIGHTS = {
        # Drug scoring
        "indication_phase_4": 40,
        "indication_phase_3": 30,
        "indication_phase_2": 20,
        "indication_phase_1": 10,
        "indication_default": 5,
        "trials_base": 15,
        "trials_per_recruiting": 2,
        "trials_max": 25,

        # Gene scoring
        "gwas": 20,
        "clinvar_pathogenic": 25,
        "clinvar_likely_pathogenic": 20,
        "clinvar_default": 15,
        "reactome": 10,
        "uniprot": 10,

        # Shared scoring
        "pubchem_fda": 10,
        "patents_base": 5,
        "patents_per_10": 1,
        "patents_max": 10,
        "literature_per_paper": 2,
        "literature_max": 10,

        # Bonuses
        "multi_source_bonus": 10,  # 3+ sources
        "recency_bonus": 5,        # Recent activity
    }

    # Confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 70
    MEDIUM_CONFIDENCE_THRESHOLD = 40

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize scorer with optional custom weights.

        Args:
            weights: Optional dict to override default weights
        """
        if weights:
            self.WEIGHTS.update(weights)

    def score_drug(
        self,
        drug: Dict[str, Any],
        clinical_trials: Optional[List[Dict]] = None,
        patents: Optional[List[Dict]] = None
    ) -> ScoredEntity:
        """
        Score a drug based on available evidence.

        Args:
            drug: Drug data from BioBTree (must have 'id', 'name')
            clinical_trials: Optional list of trials for this drug
            patents: Optional list of patents for this drug

        Returns:
            ScoredEntity with score and breakdown
        """
        breakdown = EvidenceBreakdown()
        flags = []
        metadata = {}

        drug_id = drug.get("id", "")
        drug_name = drug.get("name", drug_id)

        # --- Direct Indication Scoring ---
        if drug.get("indication_phase") is not None:
            phase = drug.get("indication_phase", 0)
            phase_scores = {
                4: self.WEIGHTS["indication_phase_4"],
                3: self.WEIGHTS["indication_phase_3"],
                2: self.WEIGHTS["indication_phase_2"],
                1: self.WEIGHTS["indication_phase_1"],
            }
            breakdown.direct_indication = phase_scores.get(
                phase, self.WEIGHTS["indication_default"]
            )
            metadata["indication_phase"] = phase

            if phase == 4:
                flags.append("approved")

        # --- Clinical Trials Scoring ---
        if clinical_trials:
            recruiting = sum(
                1 for t in clinical_trials
                if t.get("status", "").upper() == "RECRUITING"
            )
            trial_score = self.WEIGHTS["trials_base"] + (
                recruiting * self.WEIGHTS["trials_per_recruiting"]
            )
            breakdown.clinical_trials = min(
                trial_score, self.WEIGHTS["trials_max"]
            )
            metadata["trial_count"] = len(clinical_trials)
            metadata["recruiting_trials"] = recruiting

            if recruiting > 0:
                flags.append("active_trials")

        # --- Evidence from gene-based paths ---
        if drug.get("from_gwas"):
            breakdown.gwas = self.WEIGHTS["gwas"]
            metadata["gwas_genes"] = drug.get("gwas_genes", [])

        if drug.get("from_clinvar"):
            breakdown.clinvar = self.WEIGHTS["clinvar_default"]
            metadata["clinvar_genes"] = drug.get("clinvar_genes", [])

        # --- PubChem FDA ---
        if drug.get("pubchem_fda"):
            breakdown.pubchem_fda = self.WEIGHTS["pubchem_fda"]
            flags.append("fda_approved")

        # --- Patents ---
        if patents:
            patent_count = len(patents)
            patent_score = self.WEIGHTS["patents_base"] + (
                (patent_count // 10) * self.WEIGHTS["patents_per_10"]
            )
            breakdown.patents = min(patent_score, self.WEIGHTS["patents_max"])
            metadata["patent_count"] = patent_count

            if patent_count > 50:
                flags.append("high_patent_activity")

        # --- Multi-source bonus ---
        sources = breakdown.sources()
        if len(sources) >= 3:
            breakdown.multi_source_bonus = self.WEIGHTS["multi_source_bonus"]
            flags.append("multi_source")

        # --- Calculate final score and confidence ---
        total_score = breakdown.total()
        confidence = self._get_confidence(total_score)

        return ScoredEntity(
            entity_id=drug_id,
            entity_type=EntityType.DRUG,
            name=drug_name,
            score=total_score,
            confidence=confidence,
            breakdown=breakdown,
            sources=sources,
            metadata=metadata,
            flags=flags
        )

    def score_gene(
        self,
        gene: Dict[str, Any],
        has_targeting_drugs: bool = False
    ) -> ScoredEntity:
        """
        Score a gene based on available evidence.

        Args:
            gene: Gene data (must have 'symbol' or 'id')
                  Can include: in_gwas, in_clinvar, in_reactome, in_uniprot flags
            has_targeting_drugs: Whether any drugs target this gene

        Returns:
            ScoredEntity with score and breakdown
        """
        breakdown = EvidenceBreakdown()
        flags = []
        metadata = {}

        gene_symbol = gene.get("symbol", gene.get("id", ""))
        gene_name = gene.get("name", gene_symbol)

        # --- GWAS ---
        if gene.get("in_gwas"):
            breakdown.gwas = self.WEIGHTS["gwas"]
            flags.append("gwas")
            if gene.get("gwas_pvalue"):
                metadata["gwas_pvalue"] = gene.get("gwas_pvalue")

        # --- ClinVar ---
        if gene.get("in_clinvar"):
            classification = gene.get("clinvar_classification", "").lower()
            if "pathogenic" in classification and "likely" not in classification:
                breakdown.clinvar = self.WEIGHTS["clinvar_pathogenic"]
                flags.append("pathogenic_variants")
            elif "likely pathogenic" in classification:
                breakdown.clinvar = self.WEIGHTS["clinvar_likely_pathogenic"]
            else:
                breakdown.clinvar = self.WEIGHTS["clinvar_default"]
            flags.append("clinvar")
            metadata["clinvar_classification"] = classification if classification else "variant_present"

        # --- Reactome ---
        if gene.get("in_reactome"):
            breakdown.reactome = self.WEIGHTS["reactome"]
            flags.append("reactome")
            if gene.get("pathways"):
                metadata["pathway_count"] = len(gene.get("pathways", []))

        # --- UniProt ---
        if gene.get("in_uniprot"):
            breakdown.uniprot = self.WEIGHTS["uniprot"]
            flags.append("uniprot")

        # --- Druggability ---
        if has_targeting_drugs:
            flags.append("druggable")
            metadata["has_targeting_drugs"] = True
            metadata["drug_count"] = gene.get("drug_count", 0)
        else:
            flags.append("novel_target")
            metadata["has_targeting_drugs"] = False

        # --- Multi-source bonus ---
        sources = breakdown.sources()
        source_count = len(sources)
        metadata["source_count"] = source_count

        if source_count >= 3:
            breakdown.multi_source_bonus = self.WEIGHTS["multi_source_bonus"]
            flags.append("multi_source")
        elif source_count == 2:
            # Partial bonus for 2 sources
            breakdown.multi_source_bonus = self.WEIGHTS["multi_source_bonus"] / 2
            flags.append("dual_source")

        # --- Calculate final score and confidence ---
        total_score = breakdown.total()
        confidence = self._get_confidence(total_score)

        return ScoredEntity(
            entity_id=gene_symbol,
            entity_type=EntityType.GENE,
            name=gene_name,
            score=total_score,
            confidence=confidence,
            breakdown=breakdown,
            sources=sources,
            metadata=metadata,
            flags=flags
        )

    def score_results(self, result_data: Dict[str, Any]) -> ScoringResult:
        """
        Score all entities in a disease drug discovery result.

        Args:
            result_data: Output from DiseaseDrugDiscoveryTool.execute()

        Returns:
            ScoringResult with scored entities and detected patterns
        """
        scored_drugs = []
        scored_genes = []

        # --- Collect ALL drugs from all paths ---
        all_drugs: Dict[str, Dict[str, Any]] = {}  # drug_id -> drug info with sources

        # PATH 1: Direct indication drugs
        direct_indications = result_data.get("direct_indications", {})
        for drug in direct_indications.get("drugs", []):
            drug_id = drug.get("id", "")
            if drug_id:
                if drug_id not in all_drugs:
                    all_drugs[drug_id] = {**drug, "sources": set(), "target_genes": set()}
                all_drugs[drug_id]["sources"].add("direct_indication")

        # PATH 2: GWAS drugs (from drugs_by_gene)
        gwas_data = result_data.get("gwas_targets", {})
        for gene, drugs in gwas_data.get("drugs_by_gene", {}).items():
            for drug in drugs:
                drug_id = drug.get("id", "")
                if drug_id:
                    if drug_id not in all_drugs:
                        all_drugs[drug_id] = {**drug, "sources": set(), "target_genes": set()}
                    all_drugs[drug_id]["sources"].add("gwas")
                    all_drugs[drug_id]["target_genes"].add(gene)

        # PATH 3: ClinVar drugs (from drugs_by_gene)
        clinvar_data = result_data.get("clinvar_targets", {})
        for gene, drugs in clinvar_data.get("drugs_by_gene", {}).items():
            for drug in drugs:
                drug_id = drug.get("id", "")
                if drug_id:
                    if drug_id not in all_drugs:
                        all_drugs[drug_id] = {**drug, "sources": set(), "target_genes": set()}
                    all_drugs[drug_id]["sources"].add("clinvar")
                    all_drugs[drug_id]["target_genes"].add(gene)

        # PATH 6: PubChem FDA drugs (from drugs_by_gene)
        pubchem_data = result_data.get("pubchem_targets", {})
        for gene, drugs in pubchem_data.get("drugs_by_gene", {}).items():
            for drug in drugs:
                drug_id = drug.get("cid") or drug.get("id", "")
                if drug_id:
                    drug_id = f"CID:{drug_id}" if not str(drug_id).startswith("CID:") else str(drug_id)
                    if drug_id not in all_drugs:
                        all_drugs[drug_id] = {
                            "id": drug_id,
                            "name": drug.get("name", drug.get("title", drug_id)),
                            "drug_phase": 4,  # FDA approved
                            "sources": set(),
                            "target_genes": set()
                        }
                    all_drugs[drug_id]["sources"].add("pubchem_fda")
                    all_drugs[drug_id]["target_genes"].add(gene)

        # Get clinical trials and patents for enrichment
        clinical_trials = result_data.get("clinical_trials", {}).get("trials", [])
        patents_data = result_data.get("patents", {})
        patents_by_molecule = patents_data.get("by_molecule", {})

        # --- Score all collected drugs ---
        for drug_id, drug in all_drugs.items():
            drug_id = drug.get("id", "")
            drug_name = drug.get("name", "").lower()

            # Build list of all names to search for (primary + alternates)
            all_drug_names = set()
            if drug_name:
                all_drug_names.add(drug_name)

            # Add alternate names (from ChEMBL altNames)
            alt_names = drug.get("alt_names", [])
            for alt in alt_names:
                if alt:
                    # Skip very long IUPAC-like names (contain brackets or too long)
                    if len(alt) < 60 and '[' not in alt and '{' not in alt:
                        all_drug_names.add(alt.lower())

            # Find trials for this drug (by name matching in interventions)
            drug_trials = []
            for t in clinical_trials:
                interventions = t.get("interventions", [])
                intervention_str = " ".join(str(i) for i in interventions).lower()

                # Check if any drug name matches (case-insensitive)
                for name in all_drug_names:
                    # For short names (<=3 chars), require word boundary match to avoid false positives
                    if len(name) <= 3:
                        if re.search(r'\b' + re.escape(name) + r'\b', intervention_str):
                            drug_trials.append(t)
                            break
                    elif name in intervention_str:
                        drug_trials.append(t)
                        break  # Found a match, no need to check other names

            # Find patents for this drug
            drug_patents = []
            if drug_id in patents_by_molecule:
                drug_patents = patents_by_molecule[drug_id].get("patents", [])

            # Convert sources set to expected flags for score_drug()
            sources = drug.get("sources", set())
            drug["from_gwas"] = "gwas" in sources
            drug["from_clinvar"] = "clinvar" in sources
            drug["pubchem_fda"] = "pubchem_fda" in sources
            drug["gwas_genes"] = list(drug.get("target_genes", set())) if "gwas" in sources else []
            drug["clinvar_genes"] = list(drug.get("target_genes", set())) if "clinvar" in sources else []
            drug["_all_sources"] = list(sources)  # Store for later use
            drug["_target_genes"] = list(drug.get("target_genes", set()))

            scored = self.score_drug(drug, drug_trials, drug_patents)
            scored_drugs.append(scored)

        # --- Collect all genes from all sources and merge ---
        # First pass: collect genes and their sources
        gene_sources: Dict[str, Dict[str, Any]] = {}  # gene_symbol -> info

        source_mapping = {
            "gwas_targets": "in_gwas",
            "clinvar_targets": "in_clinvar",
            "reactome_pathways": "in_reactome",  # Note: key is reactome_pathways, not reactome_targets
            "uniprot_targets": "in_uniprot"
        }

        for source_key, flag_name in source_mapping.items():
            source_data = result_data.get(source_key, {})
            genes = source_data.get("genes", [])
            drugs_by_gene = source_data.get("drugs_by_gene", {})

            for gene_symbol in genes:
                # Skip Ensembl IDs (start with ENSG) - prefer gene symbols
                if gene_symbol.startswith("ENSG"):
                    continue

                # Initialize or update gene info
                if gene_symbol not in gene_sources:
                    gene_sources[gene_symbol] = {
                        "symbol": gene_symbol,
                        "name": gene_symbol,
                        "in_gwas": False,
                        "in_clinvar": False,
                        "in_reactome": False,
                        "in_uniprot": False,
                        "has_drugs": False,
                        "drug_count": 0
                    }

                # Mark this source
                gene_sources[gene_symbol][flag_name] = True

                # Check for drugs
                if gene_symbol in drugs_by_gene:
                    drug_list = drugs_by_gene[gene_symbol]
                    if drug_list:
                        gene_sources[gene_symbol]["has_drugs"] = True
                        gene_sources[gene_symbol]["drug_count"] += len(drug_list)

        # Second pass: score each unique gene with all its sources
        for gene_symbol, gene_info in gene_sources.items():
            scored = self.score_gene(gene_info, has_targeting_drugs=gene_info["has_drugs"])
            scored_genes.append(scored)

        # --- Detect patterns ---
        patterns = self._detect_patterns(scored_drugs, scored_genes)

        # --- Build summary ---
        summary = {
            "total_drugs_scored": len(scored_drugs),
            "total_genes_scored": len(scored_genes),
            "high_confidence_drugs": len([d for d in scored_drugs if d.confidence == ConfidenceLevel.HIGH]),
            "high_confidence_genes": len([g for g in scored_genes if g.confidence == ConfidenceLevel.HIGH]),
            "novel_targets": len(patterns.get("novel_targets", [])),
            "multi_source_entities": len(patterns.get("multi_source", [])),
            "top_drug": scored_drugs[0].to_dict() if scored_drugs else None,
            "top_gene": scored_genes[0].to_dict() if scored_genes else None
        }

        # Sort by score
        scored_drugs.sort(key=lambda x: x.score, reverse=True)
        scored_genes.sort(key=lambda x: x.score, reverse=True)

        return ScoringResult(
            scored_drugs=scored_drugs,
            scored_genes=scored_genes,
            patterns=patterns,
            summary=summary
        )

    def _get_confidence(self, score: float) -> ConfidenceLevel:
        """Determine confidence level from score."""
        if score >= self.HIGH_CONFIDENCE_THRESHOLD:
            return ConfidenceLevel.HIGH
        elif score >= self.MEDIUM_CONFIDENCE_THRESHOLD:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW

    def _detect_patterns(
        self,
        scored_drugs: List[ScoredEntity],
        scored_genes: List[ScoredEntity]
    ) -> Dict[str, List[str]]:
        """
        Detect patterns in scored entities.

        Patterns detected:
        - high_confidence: Entities with score >= 70
        - multi_source: Entities appearing in 3+ sources
        - novel_targets: Genes with variants but no targeting drugs
        - approved_drugs: Drugs with Phase 4 approval
        - active_development: Drugs in recruiting trials
        - emerging: High patent activity but lower clinical evidence

        Returns:
            Dict mapping pattern name to list of entity IDs
        """
        patterns = {
            "high_confidence": [],
            "multi_source": [],
            "novel_targets": [],
            "approved_drugs": [],
            "active_development": [],
            "emerging": [],
            "gaps": []
        }

        # Analyze drugs
        for drug in scored_drugs:
            if drug.confidence == ConfidenceLevel.HIGH:
                patterns["high_confidence"].append(drug.entity_id)

            if "multi_source" in drug.flags:
                patterns["multi_source"].append(drug.entity_id)

            if "approved" in drug.flags:
                patterns["approved_drugs"].append(drug.entity_id)

            if "active_trials" in drug.flags:
                patterns["active_development"].append(drug.entity_id)

            # Emerging: high patent activity but low clinical evidence
            if ("high_patent_activity" in drug.flags and
                drug.breakdown.direct_indication < 20):
                patterns["emerging"].append(drug.entity_id)

        # Analyze genes
        genes_with_drugs = set()
        genes_without_drugs = set()

        for gene in scored_genes:
            if gene.confidence == ConfidenceLevel.HIGH:
                patterns["high_confidence"].append(gene.entity_id)

            if "multi_source" in gene.flags:
                patterns["multi_source"].append(gene.entity_id)

            if "novel_target" in gene.flags:
                patterns["novel_targets"].append(gene.entity_id)
                genes_without_drugs.add(gene.entity_id)
            else:
                genes_with_drugs.add(gene.entity_id)

        # Identify gaps (genes with strong evidence but no drugs)
        for gene in scored_genes:
            if (gene.entity_id in genes_without_drugs and
                gene.score >= self.MEDIUM_CONFIDENCE_THRESHOLD):
                patterns["gaps"].append(
                    f"{gene.entity_id} (score: {gene.score:.0f}) has disease association but no targeting drugs"
                )

        return patterns


# Convenience function
def create_evidence_scorer(weights: Optional[Dict[str, float]] = None) -> EvidenceScorer:
    """
    Create an EvidenceScorer instance.

    Args:
        weights: Optional custom scoring weights

    Returns:
        Configured EvidenceScorer
    """
    return EvidenceScorer(weights=weights)
