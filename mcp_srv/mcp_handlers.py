"""MCP protocol handlers — stdio (local Claude CLI) and Streamable-HTTP (POST /mcp). Mirrors biobtree's pattern."""
import logging
from typing import List

from fastapi import APIRouter, Request, Response
from mcp.server import Server
from mcp.types import TextContent

from .config import config
from .tools import MCP_TOOLS, execute_tool

logger = logging.getLogger(__name__)
router = APIRouter(tags=["mcp"])

mcp_server = Server(config.mcp_server_name)


@mcp_server.list_tools()
async def list_tools():
    return MCP_TOOLS


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    logger.info(f"MCP tool call: {name} {arguments}")
    return [TextContent(type="text", text=await execute_tool(name, arguments))]


@router.post("/mcp")
async def mcp_message(request: Request):
    """JSON-RPC over HTTP (tools/list, tools/call, initialize)."""
    body = None
    try:
        body = await request.json()
        method, params, rid = body.get("method"), body.get("params", {}), body.get("id")
        if rid is None:
            return Response(status_code=202)
        if method == "tools/list":
            tools = [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in MCP_TOOLS]
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}}
        if method == "tools/call":
            out = await call_tool(params.get("name"), params.get("arguments", {}))
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": out[0].text}]}}
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": config.mcp_server_name, "version": "1.0.0"},
                "capabilities": {"tools": {}}}}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    except Exception as e:
        logger.exception(f"MCP message error: {e}")
        return {"jsonrpc": "2.0", "id": (body or {}).get("id"), "error": {"code": -32603, "message": str(e)}}


async def run_stdio_server():
    from mcp.server.stdio import stdio_server
    logger.info("Starting BioYoda MCP server in stdio mode")
    async with stdio_server() as (r, w):
        await mcp_server.run(r, w, mcp_server.create_initialization_options())
