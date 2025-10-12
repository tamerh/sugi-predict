"""
Core RAG (Retrieval-Augmented Generation) Engine for BioYoda

Integrates:
- Semantic search via BioYodaSearchEngine
- LLM answer generation via LLMProvider
- Prompt engineering via PromptTemplate
- Citation validation and quality metrics
"""

import time
import logging
from typing import Dict, List, Optional, Any
from .search import BioYodaSearchEngine
from .llm_providers import LLMProvider, get_llm_provider
from .prompts import PromptTemplate

logger = logging.getLogger(__name__)


class RAGEngine:
    """
    Retrieval-Augmented Generation engine for biomedical Q&A

    Workflow:
    1. User asks a question
    2. Encode and search vector database
    3. Retrieve top-k relevant abstracts/trials
    4. Build prompt with context
    5. Generate answer with LLM
    6. Validate citations
    7. Return answer with sources
    """

    def __init__(
        self,
        search_engine: BioYodaSearchEngine,
        llm_config: Dict[str, Any],
        default_collections: Optional[List[str]] = None,
        default_top_k: int = 5,
        max_context_length: int = 100000,
        enable_validation: bool = True,
        enable_aggregation: bool = True,
        retrieval_multiplier: int = 4,
        aggregation_strategy: str = "max"
    ):
        """
        Initialize RAG engine

        Args:
            search_engine: BioYodaSearchEngine instance
            llm_config: LLM provider configuration dict
            default_collections: Default collections to search
            default_top_k: Default number of documents to return
            max_context_length: Maximum context length in characters
            enable_validation: Enable citation validation
            enable_aggregation: Enable chunk aggregation by document (deduplication)
            retrieval_multiplier: Retrieve N times more chunks before aggregation (default: 4)
            aggregation_strategy: Scoring strategy for aggregation ("max", "avg", "sum")
        """
        self.search_engine = search_engine
        self.llm_provider = get_llm_provider(llm_config)
        self.prompt_template = PromptTemplate()

        self.default_collections = default_collections or [
            "pubmed_abstracts",
            "clinical_trials"
        ]
        self.default_top_k = default_top_k
        self.max_context_length = max_context_length
        self.enable_validation = enable_validation

        # New aggregation settings
        self.enable_aggregation = enable_aggregation
        self.retrieval_multiplier = retrieval_multiplier
        self.aggregation_strategy = aggregation_strategy

        logger.info(
            f"✅ RAG Engine initialized with {llm_config.get('provider')} "
            f"(model: {llm_config.get('model')})"
        )
        if enable_aggregation:
            logger.info(
                f"   Document aggregation: enabled (multiplier={retrieval_multiplier}, "
                f"strategy={aggregation_strategy})"
            )

    async def ask(
        self,
        question: str,
        collections: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        temperature: float = 0.1,
        max_tokens: int = 1000,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Answer a question using RAG

        Args:
            question: User's question
            collections: Collections to search (default: pubmed + trials)
            top_k: Number of results to retrieve (default: 5)
            temperature: LLM temperature (0.0-1.0, default: 0.1 for factual)
            max_tokens: Maximum tokens in response
            filters: Optional metadata filters

        Returns:
            Dict containing:
                - question: Original question
                - answer: Generated answer
                - sources: List of source documents
                - metrics: Performance and quality metrics
                - validation: Citation validation results
        """
        start_time = time.time()

        # Use defaults if not specified
        collections = collections or self.default_collections
        top_k = top_k or self.default_top_k

        logger.info(f"RAG query: '{question}' (collections={collections}, top_k={top_k})")

        try:
            # Step 1: Retrieve relevant context
            search_start = time.time()

            # Calculate retrieval limit (retrieve more chunks if aggregation is enabled)
            if self.enable_aggregation:
                retrieval_limit = top_k * self.retrieval_multiplier
                logger.debug(
                    f"Retrieving {retrieval_limit} chunks (top_k={top_k} × multiplier={self.retrieval_multiplier}) "
                    f"for aggregation"
                )
            else:
                retrieval_limit = top_k

            if len(collections) == 1:
                # Single collection search
                search_results = self.search_engine.search_single_collection(
                    query=question,
                    collection=collections[0],
                    limit=retrieval_limit,
                    filters=filters
                )
            else:
                # Multi-collection search
                multi_results = self.search_engine.search_multi_collection(
                    query=question,
                    collections=collections,
                    limit=retrieval_limit,
                    filters=filters
                )
                # Merge and rank by score
                search_results = self.search_engine.merge_and_rank_results(
                    multi_results,
                    limit=retrieval_limit
                )

            # Step 1.5: Aggregate chunks by document (if enabled)
            if self.enable_aggregation and search_results:
                logger.debug(f"Aggregating {len(search_results)} chunks by document...")
                search_results = self.search_engine.aggregate_chunks_by_document(
                    results=search_results,
                    limit=top_k,
                    scoring_strategy=self.aggregation_strategy
                )
                logger.info(
                    f"After aggregation: {len(search_results)} unique documents "
                    f"(from {retrieval_limit} chunks)"
                )

            search_time_ms = (time.time() - search_start) * 1000

            if not search_results:
                logger.warning("No search results found for query")
                return self._build_no_results_response(
                    question=question,
                    search_time_ms=search_time_ms,
                    total_time_ms=(time.time() - start_time) * 1000
                )

            logger.info(f"Retrieved {len(search_results)} results in {search_time_ms:.0f}ms")

            # Step 2: Build prompt with context
            prompt = self.prompt_template.build_rag_prompt(
                question=question,
                search_results=search_results,
                include_citations=True,
                max_context_length=self.max_context_length
            )

            # Step 3: Generate answer with LLM
            llm_start = time.time()
            answer = self.llm_provider.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            llm_time_ms = (time.time() - llm_start) * 1000

            logger.info(f"LLM generated answer in {llm_time_ms:.0f}ms")

            # Step 4: Validate citations (if enabled)
            validation_results = None
            if self.enable_validation:
                validation_results = self.prompt_template.validate_citations(
                    response_text=answer,
                    source_results=search_results
                )

                if validation_results.get('warning'):
                    logger.warning(f"Citation validation: {validation_results['warning']}")

            # Step 5: Build sources metadata
            sources = self._build_sources(search_results)

            # Step 6: Calculate metrics
            total_time_ms = (time.time() - start_time) * 1000

            # Estimate cost
            cost_estimate = self.llm_provider.get_cost_estimate(
                input_text=prompt,
                output_text=answer
            )

            response = {
                "question": question,
                "answer": answer,
                "sources": sources,
                "metrics": {
                    "search_time_ms": round(search_time_ms, 2),
                    "llm_time_ms": round(llm_time_ms, 2),
                    "total_time_ms": round(total_time_ms, 2),
                    "num_sources": len(sources),
                    "model_used": self.llm_provider.model,
                    "estimated_cost_usd": round(cost_estimate, 4)
                }
            }

            # Add validation results if enabled
            if validation_results:
                response["validation"] = {
                    "citation_coverage": round(validation_results["citation_coverage"], 2),
                    "cited_count": len(validation_results["cited_ids"]),
                    "valid_citations": validation_results["valid_citations"],
                    "invalid_citations": validation_results["invalid_citations"],
                    "warning": validation_results.get("warning")
                }

            logger.info(
                f"RAG completed in {total_time_ms:.0f}ms "
                f"(search: {search_time_ms:.0f}ms, LLM: {llm_time_ms:.0f}ms)"
            )

            return response

        except Exception as e:
            logger.error(f"RAG error: {str(e)}", exc_info=True)
            raise

    def _build_sources(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build sources list from search results

        Args:
            search_results: Raw search results

        Returns:
            List of formatted source dicts
        """
        sources = []

        for result in search_results:
            payload = result.get('payload', {})
            score = result.get('score', 0.0)
            collection = result.get('collection', 'unknown')

            # Extract identifier
            pmid = payload.get('pmid')
            nct_id = payload.get('nct_id')

            if pmid:
                identifier = f"PMID:{pmid}"
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            elif nct_id:
                identifier = nct_id
                url = f"https://clinicaltrials.gov/study/{nct_id}"
            else:
                identifier = result.get('id', 'unknown')
                url = None

            # Extract metadata
            title = payload.get('title', 'No title available')
            text = payload.get('chunk_text', payload.get('text', ''))

            # Create text preview (first 200 chars)
            text_preview = text[:200] + "..." if len(text) > 200 else text

            source = {
                "id": identifier,
                "score": round(score, 3),
                "collection": collection,
                "title": title,
                "text_preview": text_preview
            }

            if url:
                source["url"] = url

            sources.append(source)

        return sources

    def _build_no_results_response(
        self,
        question: str,
        search_time_ms: float,
        total_time_ms: float
    ) -> Dict[str, Any]:
        """
        Build response when no search results found

        Args:
            question: Original question
            search_time_ms: Search time in milliseconds
            total_time_ms: Total time in milliseconds

        Returns:
            Response dict with "no results" message
        """
        return {
            "question": question,
            "answer": (
                "I apologize, but I couldn't find relevant information in the database "
                "to answer your question. This could mean:\n\n"
                "1. The topic is not well-represented in the current literature database\n"
                "2. The question might need to be rephrased for better search results\n"
                "3. This might be a very recent or emerging topic not yet in the database\n\n"
                "Please try:\n"
                "- Rephrasing your question with different medical/scientific terms\n"
                "- Breaking down complex questions into simpler parts\n"
                "- Using more specific disease, drug, or gene names"
            ),
            "sources": [],
            "metrics": {
                "search_time_ms": round(search_time_ms, 2),
                "llm_time_ms": 0.0,
                "total_time_ms": round(total_time_ms, 2),
                "num_sources": 0,
                "model_used": self.llm_provider.model,
                "estimated_cost_usd": 0.0
            },
            "validation": {
                "citation_coverage": 0.0,
                "cited_count": 0,
                "valid_citations": [],
                "invalid_citations": [],
                "warning": "No search results found"
            }
        }

    def get_conversation_response(
        self,
        current_question: str,
        conversation_history: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Answer question with conversation context (future feature)

        Args:
            current_question: Current user question
            conversation_history: Previous Q&A turns
            **kwargs: Additional parameters for ask()

        Returns:
            Response dict (same format as ask())
        """
        # For now, just use regular ask (no conversation support yet)
        # TODO: Implement multi-turn conversation in Phase 4
        logger.warning("Conversation mode not yet implemented, using standard RAG")
        return self.ask(current_question, **kwargs)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get RAG engine statistics

        Returns:
            Dict with engine stats
        """
        return {
            "llm_provider": self.llm_provider.__class__.__name__,
            "llm_model": self.llm_provider.model,
            "default_collections": self.default_collections,
            "default_top_k": self.default_top_k,
            "max_context_length": self.max_context_length,
            "validation_enabled": self.enable_validation,
            "search_engine_healthy": self.search_engine.health_check()
        }


# Example usage and testing
if __name__ == "__main__":
    import asyncio
    from .config import load_config

    async def test_rag():
        """Test RAG engine with example question"""
        # Load config
        config = load_config()

        # Initialize search engine
        # Build collection models mapping
        collection_models = {
            'pubmed_abstracts': config['pubmed']['model_name'],
            'clinical_trials': config.get('clinical_trials', {}).get('model_name', config['pubmed']['model_name'])
        }
        search_engine = BioYodaSearchEngine(
            qdrant_url=config.get('qdrant_url', 'http://localhost:6333'),
            collection_models=collection_models
        )

        # Initialize RAG engine
        llm_config = config.get('rag', {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet-20241022",
            "api_key": "your-api-key-here"
        })

        rag_engine = RAGEngine(
            search_engine=search_engine,
            llm_config=llm_config
        )

        # Test question
        question = "What is CRISPR gene editing and how is it used in medicine?"

        print(f"\n{'='*80}")
        print(f"Question: {question}")
        print(f"{'='*80}\n")

        # Get answer
        result = await rag_engine.ask(question=question)

        # Print results
        print(f"Answer:\n{result['answer']}\n")
        print(f"{'='*80}")
        print(f"Sources ({len(result['sources'])}):")
        for i, source in enumerate(result['sources'], 1):
            print(f"\n{i}. {source['id']} (score: {source['score']})")
            print(f"   {source['title']}")
            if 'url' in source:
                print(f"   {source['url']}")

        print(f"\n{'='*80}")
        print(f"Metrics:")
        for key, value in result['metrics'].items():
            print(f"  {key}: {value}")

        if 'validation' in result:
            print(f"\nValidation:")
            for key, value in result['validation'].items():
                print(f"  {key}: {value}")

    # Run test
    asyncio.run(test_rag())
