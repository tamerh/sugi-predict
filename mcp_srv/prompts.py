"""Agent-facing tool descriptions + JSON-Schemas for the BioYoda substrate tools.

Three tools, documented by capability. Underlying execution (Qdrant, FPSim2, parquet) is intentionally hidden.
"""

COLLECTIONS_DOC = """Collections (pass as `collection`):
  patent_compounds        SureChEMBL patent compounds, each with predicted human protein targets. CHEMICAL
                          (query by `smiles`). Filterable payload: targets (UniProt accession, keyword),
                          best_tanimoto (0-1 float), novel (bool), exact_match (bool), surechembl_id.
  chembl                  ChEMBL reference ligands. CHEMICAL (query by `smiles`).
  clinical_trials_medcpt  ClinicalTrials.gov. TEXT (query by `text`).
  patents_text            patent full text. TEXT (query by `text`).
  esm2                    SwissProt ESM-2 protein embeddings. PROTEIN (query by `accession`, a UniProt id).
"""

TOOL_DESCRIPTIONS = {
    "bioyoda_query": (
        "Search or filter ANY BioYoda collection. Provide a query input matching the collection's modality for "
        "semantic/similarity search: `text` for the text collections, `smiles` for the chemical collections, "
        "`accession` (UniProt id) for the protein collection. OR provide only a `filter` for exact payload "
        "retrieval (no ranking). You can combine a query input with a filter (e.g. smiles similarity restricted to "
        "compounds predicted against a target). Returns ranked hits with their payload; vectors are omitted.\n\n"
        + COLLECTIONS_DOC +
        "\nfilter syntax: {field: value} exact, {field: [v1,v2]} any-of, {field: {gte: x, lte: y}} numeric range. "
        "Multiple fields are AND-ed. Example: {\"targets\": \"P00533\", \"best_tanimoto\": {\"gte\": 0.5}}."
    ),
    "bioyoda_predict": (
        "Predict the protein targets of an arbitrary molecule from its SMILES (chemical k-NN to known ChEMBL "
        "ligands; the prediction engine, not a lookup). Returns ranked targets with gene symbol, confidence "
        "(Tanimoto to the nearest known ligand of that target, 0-1), supporting-neighbour count (of 20), and a "
        "confidence band. Confidence <0.3 means no close known analogue (the molecule is flagged novel). Use this "
        "for any molecule; for a compound already in the atlas, bioyoda_query (by id) returns its stored prediction."
    ),
    "bioyoda_provenance": (
        "Resolve SureChEMBL compound id(s) to their patent metadata: patent number, country, assignee, publication "
        "date, and whether the compound is CLAIMED (in the patent's claims) vs merely disclosed. Also returns "
        "n_patents and a noise flag (a compound in thousands of patents is a generic fragment, not IP-informative). "
        "Honest gaps: only publication date (no priority/filing date), raw un-normalised assignee, no inventors."
    ),
}

INPUT_SCHEMAS = {
    "bioyoda_query": {
        "type": "object",
        "properties": {
            "collection": {"type": "string", "description": "Collection name (see description for the list)."},
            "text": {"type": "string", "description": "Free-text query (text collections only)."},
            "smiles": {"type": "string", "description": "SMILES query (chemical collections only)."},
            "accession": {"type": "string", "description": "UniProt accession query (esm2 only)."},
            "filter": {"type": "object", "description": "Payload filter; see filter syntax in the description."},
            "limit": {"type": "integer", "description": "Max hits (1-100, default 10).", "default": 10},
            "offset": {"description": "Pagination token from a previous response's 'next', or an integer offset."},
        },
        "required": ["collection"],
    },
    "bioyoda_predict": {
        "type": "object",
        "properties": {
            "smiles": {"type": "string", "description": "The molecule's SMILES."},
            "top": {"type": "integer", "description": "Number of targets to return (default 20).", "default": 20},
            "human_only": {"type": "boolean", "description": "Human targets only (default true).", "default": True},
        },
        "required": ["smiles"],
    },
    "bioyoda_provenance": {
        "type": "object",
        "properties": {
            "ids": {"type": "array", "items": {"type": "string"},
                    "description": "SureChEMBL ids, e.g. [\"SCHEMBL964\", \"SCHEMBL8383\"] (bare integers also accepted)."},
            "max_per": {"type": "integer", "description": "Max patents per compound (default 8).", "default": 8},
        },
        "required": ["ids"],
    },
}
