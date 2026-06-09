#!/bin/bash
# esm2 GPU step — assigned to a GPU citizen; NOT run on this CPU box.
# Generates ESM-2 (650M) embeddings from the SwissProt FASTA into per-chunk h5.
# Real impl: python modules/esm2/scripts/generate_embeddings.py  (needs CUDA)
set -euo pipefail
echo "ESM-2 embedding generation runs on a GPU citizen (CUDA). No-op on CPU host." >&2
