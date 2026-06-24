"""BioYoda substrate server — REST + MCP over the BioYoda Qdrant collections + chemical engine.

Three primitives (the whole contract):
  query(collection, ...)  — embed (text/smiles/protein) + vector search OR pure payload filter, any collection
  predict(smiles)         — chemical target prediction (FPSim2 engine; not a Qdrant op)
  provenance(ids)         — SureChEMBL compound -> patent metadata (parquet join; not a Qdrant op)

Mirrors biobtree's mcp_srv (dual-mode: `python -m mcp_srv --mode http|stdio`).
"""
