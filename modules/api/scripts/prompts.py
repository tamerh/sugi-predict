"""
Prompt Engineering Framework for BioYoda RAG

Handles:
- Biomedical-specific system prompts
- RAG prompt templates with context injection
- Citation formatting and requirements
- Hallucination prevention strategies
- Follow-up question support (future)
"""

from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PromptTemplate:
    """Prompt templates for BioYoda RAG system"""

    # Core system prompt for biomedical AI assistant
    SYSTEM_PROMPT = """You are BioYoda, an expert biomedical AI assistant with access to a database of 30M+ PubMed abstracts and 500K+ clinical trials.

Your role:
- Answer questions accurately based ONLY on the provided context from scientific literature
- Always cite specific PMIDs (PubMed IDs) or trial IDs for every claim you make
- If the provided context is insufficient to answer the question, state this clearly - never make up information
- Use clear, accessible language while maintaining scientific accuracy
- Distinguish between well-established facts and emerging research
- When multiple sources conflict, acknowledge the disagreement and cite both perspectives

CRITICAL RULES:
1. Never hallucinate or invent information not in the context
2. Every factual claim must have a citation (e.g., "According to PMID:12345...")
3. If you don't have enough information, say: "The provided sources do not contain sufficient information to answer this question."
4. Always include a "Sources:" section at the end listing all PMIDs used

Remember: Scientific accuracy and proper attribution are paramount."""

    @staticmethod
    def build_rag_prompt(
        question: str,
        search_results: List[Dict],
        include_citations: bool = True,
        max_context_length: int = 100000
    ) -> str:
        """
        Build RAG prompt with context from search results

        Args:
            question: User's question
            search_results: List of search results with payload containing:
                - pmid or nct_id: Identifier
                - chunk_text: Text content
                - score: Relevance score
                - collection: Source collection name
            include_citations: Whether to require citations
            max_context_length: Maximum context length (chars)

        Returns:
            Formatted prompt ready for LLM
        """
        # Format context from search results
        context_parts = []
        total_length = 0

        for i, result in enumerate(search_results, 1):
            payload = result.get('payload', {})

            # Get identifier (PMID or trial ID)
            pmid = payload.get('pmid')
            nct_id = payload.get('nct_id')
            identifier = f"PMID:{pmid}" if pmid else f"Trial:{nct_id}"

            # Get text content
            text = payload.get('chunk_text', payload.get('text', ''))
            if not text:
                continue

            # Get metadata
            score = result.get('score', 0.0)
            collection = payload.get('collection', 'unknown')

            # Build context entry
            context_entry = f"""
[Source {i}] {identifier} (Relevance: {score:.3f}, Collection: {collection})
{text}
---
"""
            # Check length limit
            if total_length + len(context_entry) > max_context_length:
                logger.warning(
                    f"Context truncated at source {i} to stay within {max_context_length} chars"
                )
                break

            context_parts.append(context_entry)
            total_length += len(context_entry)

        if not context_parts:
            context = "[No relevant context found in the database]"
        else:
            context = "\n".join(context_parts)

        # Build final prompt
        citation_instruction = ""
        if include_citations:
            citation_instruction = """
2. Cite specific identifiers for each claim (e.g., "According to PMID:12345..." or "Trial NCT01234567 showed...")
3. End with a "Sources:" section listing all identifiers used"""

        prompt = f"""{PromptTemplate.SYSTEM_PROMPT}

CONTEXT (Retrieved from vector search):
{context}

QUESTION: {question}

INSTRUCTIONS:
1. Answer the question using ONLY the context above{citation_instruction}
4. If the context doesn't contain enough information, state this clearly and explain what information is missing
5. Provide a comprehensive but concise answer (aim for 3-5 paragraphs)

Answer:"""

        return prompt

    @staticmethod
    def build_multi_turn_prompt(
        current_question: str,
        conversation_history: List[Dict[str, str]],
        search_results: List[Dict]
    ) -> str:
        """
        Build prompt for multi-turn conversations (future feature)

        Args:
            current_question: Current user question
            conversation_history: Previous Q&A pairs
                [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
            search_results: Search results for current question

        Returns:
            Formatted prompt with conversation context
        """
        # Build conversation context
        conversation_context = "\n\nPREVIOUS CONVERSATION:\n"
        for turn in conversation_history[-3:]:  # Last 3 turns
            role = turn['role'].upper()
            content = turn['content']
            conversation_context += f"{role}: {content}\n"

        # Build current prompt
        base_prompt = PromptTemplate.build_rag_prompt(
            question=current_question,
            search_results=search_results
        )

        # Insert conversation context before instructions
        parts = base_prompt.split("QUESTION:")
        prompt_with_history = parts[0] + conversation_context + "\nQUESTION:" + parts[1]

        return prompt_with_history

    @staticmethod
    def extract_citations(response_text: str) -> List[str]:
        """
        Extract cited PMIDs/trial IDs from LLM response

        Args:
            response_text: Generated answer text

        Returns:
            List of cited identifiers (PMIDs, NCT IDs)
        """
        import re

        citations = []

        # Pattern for PMID:12345 or PMID: 12345
        pmid_pattern = r'PMID:?\s*(\d+)'
        pmids = re.findall(pmid_pattern, response_text, re.IGNORECASE)
        citations.extend([f"PMID:{p}" for p in pmids])

        # Pattern for NCT12345678 or Trial NCT12345678
        nct_pattern = r'NCT\d{8}'
        ncts = re.findall(nct_pattern, response_text, re.IGNORECASE)
        citations.extend(ncts)

        # Remove duplicates while preserving order
        seen = set()
        unique_citations = []
        for cit in citations:
            cit_upper = cit.upper()
            if cit_upper not in seen:
                seen.add(cit_upper)
                unique_citations.append(cit)

        return unique_citations

    @staticmethod
    def validate_citations(
        response_text: str,
        source_results: List[Dict]
    ) -> Dict[str, any]:
        """
        Validate that citations in response match provided sources

        Args:
            response_text: Generated answer
            source_results: Original search results

        Returns:
            Dict with validation results:
                - cited_ids: List of IDs mentioned in response
                - source_ids: List of IDs from search results
                - citation_coverage: Fraction of sources cited
                - valid_citations: List of correctly cited IDs
                - invalid_citations: List of hallucinated IDs
                - warning: Warning message if issues detected
        """
        # Extract citations from response
        cited_ids = PromptTemplate.extract_citations(response_text)

        # Extract source IDs from results
        source_ids = []
        for result in source_results:
            payload = result.get('payload', {})
            pmid = payload.get('pmid')
            nct_id = payload.get('nct_id')

            if pmid:
                source_ids.append(f"PMID:{pmid}")
            elif nct_id:
                source_ids.append(nct_id)

        # Normalize for comparison
        cited_set = {c.upper() for c in cited_ids}
        source_set = {s.upper() for s in source_ids}

        # Identify valid and invalid citations
        valid_citations = list(cited_set & source_set)
        invalid_citations = list(cited_set - source_set)

        # Calculate coverage
        citation_coverage = len(valid_citations) / len(source_ids) if source_ids else 0.0

        # Generate warnings
        warning = None
        if invalid_citations:
            warning = f"⚠️  Hallucinated citations detected: {', '.join(invalid_citations)}"
        elif citation_coverage < 0.3 and source_ids:
            warning = f"⚠️  Low citation coverage ({citation_coverage:.1%}) - answer may not be well-grounded in sources"
        elif not cited_ids and source_ids:
            warning = "⚠️  No citations found - high hallucination risk"

        return {
            "cited_ids": list(cited_set),
            "source_ids": list(source_set),
            "citation_coverage": citation_coverage,
            "valid_citations": valid_citations,
            "invalid_citations": invalid_citations,
            "warning": warning
        }

    @staticmethod
    def format_sources(search_results: List[Dict]) -> str:
        """
        Format sources section for display

        Args:
            search_results: Search results with metadata

        Returns:
            Formatted sources text
        """
        if not search_results:
            return "No sources available."

        sources_text = "Sources:\n"
        for i, result in enumerate(search_results, 1):
            payload = result.get('payload', {})
            score = result.get('score', 0.0)

            # Get identifier and title
            pmid = payload.get('pmid')
            nct_id = payload.get('nct_id')
            title = payload.get('title', 'No title available')

            if pmid:
                identifier = f"PMID:{pmid}"
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            elif nct_id:
                identifier = nct_id
                url = f"https://clinicaltrials.gov/study/{nct_id}"
            else:
                identifier = f"Source {i}"
                url = None

            sources_text += f"{i}. [{identifier}] {title} (Relevance: {score:.3f})\n"
            if url:
                sources_text += f"   {url}\n"

        return sources_text


# Example usage and testing
if __name__ == "__main__":
    # Example search results
    example_results = [
        {
            "id": "pubmed_123",
            "score": 0.92,
            "payload": {
                "pmid": "12345678",
                "title": "CRISPR-Cas9 gene editing in human cells",
                "chunk_text": "CRISPR-Cas9 is a revolutionary gene editing technology that allows precise modifications to DNA. It consists of two key components: the Cas9 enzyme that cuts DNA, and a guide RNA that directs Cas9 to the correct location in the genome.",
                "collection": "pubmed_abstracts"
            }
        },
        {
            "id": "trial_456",
            "score": 0.85,
            "payload": {
                "nct_id": "NCT03745287",
                "title": "CRISPR Gene Therapy for Sickle Cell Disease",
                "chunk_text": "This clinical trial investigates the use of CRISPR-Cas9 gene editing to treat sickle cell disease by modifying the patient's own blood cells to correct the genetic mutation.",
                "collection": "clinical_trials"
            }
        }
    ]

    # Build RAG prompt
    question = "What is CRISPR gene editing and how is it being used in clinical trials?"
    prompt = PromptTemplate.build_rag_prompt(question, example_results)

    print("=" * 80)
    print("GENERATED PROMPT:")
    print("=" * 80)
    print(prompt)
    print("\n" + "=" * 80)

    # Example response with citations
    example_response = """CRISPR-Cas9 is a revolutionary gene editing technology that enables precise modifications to DNA sequences. According to PMID:12345678, the system consists of two key components: the Cas9 enzyme which functions as molecular scissors to cut DNA, and a guide RNA that directs Cas9 to the specific location in the genome that needs to be edited.

In clinical applications, CRISPR is being investigated for treating genetic diseases. Trial NCT03745287 is currently studying the use of CRISPR-Cas9 gene editing for sickle cell disease, where the technology is used to modify patients' own blood cells to correct the genetic mutation causing the disease.

Sources:
- PMID:12345678
- NCT03745287"""

    # Validate citations
    print("\nCITATION VALIDATION:")
    print("=" * 80)
    validation = PromptTemplate.validate_citations(example_response, example_results)
    print(f"Cited IDs: {validation['cited_ids']}")
    print(f"Citation Coverage: {validation['citation_coverage']:.1%}")
    print(f"Valid Citations: {validation['valid_citations']}")
    print(f"Invalid Citations: {validation['invalid_citations']}")
    if validation['warning']:
        print(f"Warning: {validation['warning']}")
    else:
        print("✅ All citations valid!")

    print("\n" + "=" * 80)
    print("FORMATTED SOURCES:")
    print("=" * 80)
    print(PromptTemplate.format_sources(example_results))
