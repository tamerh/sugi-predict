"""MCP tool definitions + execution. The same three engine primitives, agent-facing."""
import asyncio
import json
import logging
from typing import Any, Dict

from mcp.types import Tool

from . import engine as E
from .prompts import TOOL_DESCRIPTIONS, INPUT_SCHEMAS

logger = logging.getLogger(__name__)

MCP_TOOLS = [
    Tool(name="bioyoda_query", description=TOOL_DESCRIPTIONS["bioyoda_query"], inputSchema=INPUT_SCHEMAS["bioyoda_query"]),
    Tool(name="bioyoda_predict", description=TOOL_DESCRIPTIONS["bioyoda_predict"], inputSchema=INPUT_SCHEMAS["bioyoda_predict"]),
    Tool(name="bioyoda_provenance", description=TOOL_DESCRIPTIONS["bioyoda_provenance"], inputSchema=INPUT_SCHEMAS["bioyoda_provenance"]),
]


async def execute_tool(tool_name: str, arguments: Dict[str, Any], max_result_length: int = 50000) -> str:
    """Run a tool in a worker thread (the engine is sync) and return a JSON string."""
    try:
        if tool_name == "bioyoda_query":
            result = await asyncio.to_thread(
                E.query, arguments["collection"], arguments.get("text"), arguments.get("smiles"),
                arguments.get("accession"), arguments.get("filter"), arguments.get("limit", 10), arguments.get("offset"))
        elif tool_name == "bioyoda_predict":
            result = await asyncio.to_thread(
                E.predict, arguments["smiles"], arguments.get("top", 20), arguments.get("human_only", True))
        elif tool_name == "bioyoda_provenance":
            result = await asyncio.to_thread(
                E.provenance, arguments["ids"], arguments.get("max_per", 8))
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        s = json.dumps(result, indent=2, default=str)
        return s if len(s) <= max_result_length else s[:max_result_length] + "\n... [truncated]"
    except Exception as e:
        logger.exception(f"Tool execution error: {e}")
        return json.dumps({"error": str(e)})
