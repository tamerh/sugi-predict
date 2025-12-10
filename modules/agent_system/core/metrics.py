"""Metrics tracking for agent system observability."""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict


@dataclass
class LLMMetrics:
    """Metrics for a single LLM call."""
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class ToolMetrics:
    """Metrics for a single tool call."""
    tool_name: str
    latency_ms: float
    success: bool
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """
    Collects and aggregates metrics for LLM calls and tool executions.

    Thread-safe singleton for collecting metrics across the agent system.
    """

    _instance: Optional['MetricsCollector'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.reset()

    def reset(self):
        """Reset all metrics."""
        self.llm_calls: List[LLMMetrics] = []
        self.tool_calls: List[ToolMetrics] = []
        self._query_start: Optional[float] = None

    def start_query(self):
        """Mark the start of a new query."""
        self._query_start = time.time()

    def record_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float
    ):
        """Record metrics for an LLM call."""
        self.llm_calls.append(LLMMetrics(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms
        ))

    def record_tool_call(
        self,
        tool_name: str,
        latency_ms: float,
        success: bool = True
    ):
        """Record metrics for a tool call."""
        self.tool_calls.append(ToolMetrics(
            tool_name=tool_name,
            latency_ms=latency_ms,
            success=success
        ))

    def get_summary(self) -> Dict:
        """
        Get summary of all metrics for current query.

        Returns:
            Dictionary with aggregated metrics
        """
        # LLM metrics by model
        llm_by_model: Dict[str, Dict] = defaultdict(lambda: {
            'calls': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'total_latency_ms': 0
        })

        for m in self.llm_calls:
            llm_by_model[m.model]['calls'] += 1
            llm_by_model[m.model]['input_tokens'] += m.input_tokens
            llm_by_model[m.model]['output_tokens'] += m.output_tokens
            llm_by_model[m.model]['total_latency_ms'] += m.latency_ms

        # Tool metrics by name
        tool_by_name: Dict[str, Dict] = defaultdict(lambda: {
            'calls': 0,
            'success': 0,
            'failed': 0,
            'total_latency_ms': 0
        })

        for t in self.tool_calls:
            tool_by_name[t.tool_name]['calls'] += 1
            if t.success:
                tool_by_name[t.tool_name]['success'] += 1
            else:
                tool_by_name[t.tool_name]['failed'] += 1
            tool_by_name[t.tool_name]['total_latency_ms'] += t.latency_ms

        # Calculate totals
        total_input = sum(m.input_tokens for m in self.llm_calls)
        total_output = sum(m.output_tokens for m in self.llm_calls)
        total_llm_time = sum(m.latency_ms for m in self.llm_calls)
        total_tool_time = sum(t.latency_ms for t in self.tool_calls)

        # Query total time
        query_time_ms = None
        if self._query_start:
            query_time_ms = (time.time() - self._query_start) * 1000

        return {
            'llm': {
                'by_model': dict(llm_by_model),
                'total_calls': len(self.llm_calls),
                'total_input_tokens': total_input,
                'total_output_tokens': total_output,
                'total_tokens': total_input + total_output,
                'total_latency_ms': round(total_llm_time, 1)
            },
            'tools': {
                'by_tool': dict(tool_by_name),
                'total_calls': len(self.tool_calls),
                'total_latency_ms': round(total_tool_time, 1)
            },
            'query_total_ms': round(query_time_ms, 1) if query_time_ms else None
        }

    def format_summary(self) -> str:
        """Format metrics summary as readable string."""
        summary = self.get_summary()
        lines = []

        lines.append("\n" + "=" * 50)
        lines.append("METRICS")
        lines.append("=" * 50)

        # LLM metrics
        llm = summary['llm']
        lines.append(f"\nLLM ({llm['total_calls']} calls, {llm['total_latency_ms']}ms):")
        for model, stats in llm['by_model'].items():
            avg_latency = stats['total_latency_ms'] / stats['calls'] if stats['calls'] > 0 else 0
            lines.append(f"  {model}:")
            lines.append(f"    Calls: {stats['calls']}")
            lines.append(f"    Tokens: {stats['input_tokens']} in / {stats['output_tokens']} out")
            lines.append(f"    Latency: {stats['total_latency_ms']:.0f}ms total, {avg_latency:.0f}ms avg")

        lines.append(f"\n  Total tokens: {llm['total_tokens']} ({llm['total_input_tokens']} in / {llm['total_output_tokens']} out)")

        # Tool metrics
        tools = summary['tools']
        if tools['total_calls'] > 0:
            lines.append(f"\nTools ({tools['total_calls']} calls, {tools['total_latency_ms']}ms):")
            for tool, stats in tools['by_tool'].items():
                avg_latency = stats['total_latency_ms'] / stats['calls'] if stats['calls'] > 0 else 0
                status = f"{stats['success']} ok" + (f", {stats['failed']} failed" if stats['failed'] > 0 else "")
                lines.append(f"  {tool}: {stats['calls']} calls ({status}), {stats['total_latency_ms']:.0f}ms total, {avg_latency:.0f}ms avg")

        # Total time
        if summary['query_total_ms']:
            lines.append(f"\nTotal query time: {summary['query_total_ms']:.0f}ms")

        lines.append("=" * 50)

        return "\n".join(lines)


# Global metrics collector instance
def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    return MetricsCollector()
