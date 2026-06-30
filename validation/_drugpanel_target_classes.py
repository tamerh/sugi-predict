#!/usr/bin/env python3
"""Build a gene -> ChEMBL-protein-class map for the large drug panel.

Source: ChEMBL protein classification, from biobtree's extracted
raw_data/chembl/extracted/chembl_targets.jsonl (`protein_classes` path hierarchy,
human targets). The coarse ChEMBL level-1 (Enzyme / Membrane receptor / ...) is
refined to the pharmacologically-meaningful families the panel cares about:
  Kinase, Protease, Other enzyme         (split out of /Enzyme)
  GPCR, Membrane receptor (other)        (split out of /Membrane receptor)
  Ion channel, Transporter, Epigenetic regulator
  Nuclear receptor                       (split out of /Transcription factor)
  Transcription factor (other), Other/unclassified
Writes gene_class.json = {gene_symbol: class}. Each gene -> a single PRIORITY class
(kinase>protease>GPCR>ion channel>nuclear receptor>transporter>epigenetic>enzyme>...)
so a drug's mechanism gene maps to one class.
"""
import json, sys
REF = "/data/bioyoda/out_prod/work/chembl_reference"
TGT = "/data/biobtree/raw_data/chembl/extracted/chembl_targets.jsonl"
OUT = "/data/bioyoda/validation/results/gene_class.json"

GENES = json.load(open(f"{REF}/target_genes.json"))
def gene(acc): return GENES.get(acc, {}).get("gene", acc)

def classify(paths):
    """paths = list of full ChEMBL protein-class path strings for one target."""
    blob = " ;; ".join(paths)
    if "/Enzyme/Kinase" in blob:                         return "Kinase"
    if "/Enzyme/Protease" in blob:                       return "Protease"
    if "G protein-coupled receptor" in blob:             return "GPCR"
    if "/Ion channel" in blob:                           return "Ion channel"
    if "/Transcription factor/Nuclear receptor" in blob: return "Nuclear receptor"
    if "/Transporter" in blob:                           return "Transporter"
    if "/Epigenetic regulator" in blob:                  return "Epigenetic regulator"
    if "/Membrane receptor" in blob:                     return "Membrane receptor (other)"
    if "/Enzyme" in blob:                                return "Other enzyme"
    if "/Transcription factor" in blob:                  return "Transcription factor (other)"
    if blob and "Unclassified" not in blob:              return "Other (classified)"
    return "Other/unclassified"

# priority for resolving multiple uniprots sharing a gene
PRIO = {"Kinase":0,"Protease":1,"GPCR":2,"Ion channel":3,"Nuclear receptor":4,
        "Transporter":5,"Epigenetic regulator":6,"Membrane receptor (other)":7,
        "Other enzyme":8,"Transcription factor (other)":9,"Other (classified)":10,
        "Other/unclassified":11}

gene_class = {}
n_targets = 0; n_classed = 0
for l in open(TGT):
    d = json.loads(l)
    if d.get("tax_id") != 9606: continue
    paths = [pc["path"] for pc in d.get("protein_classes", [])]
    cls = classify(paths)
    n_targets += 1
    if cls != "Other/unclassified": n_classed += 1
    for acc in d.get("uniprot_ids", []):
        g = gene(acc)
        if g not in gene_class or PRIO[cls] < PRIO[gene_class[g]]:
            gene_class[g] = cls
json.dump(gene_class, open(OUT, "w"))
print(f"human chembl targets scanned: {n_targets}  ({n_classed} with a non-empty class)")
print(f"genes classed: {len(gene_class)} -> {OUT}")
import collections
c = collections.Counter(gene_class.values())
for k, v in c.most_common(): print(f"  {v:5} {k}")
