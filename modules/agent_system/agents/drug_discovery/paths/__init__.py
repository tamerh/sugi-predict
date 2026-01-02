"""Drug Discovery Data Gathering Paths.

Individual query paths for gathering drug discovery evidence:

BioBTree Paths:
- PATH 1: Direct indications (disease >> efo >> chembl_molecule)
- PATH 2: GWAS genetic associations
- PATH 3: ClinVar variant associations
- PATH 6a: PubChem enrichment via InChI key (ChEMBL drugs >> InChI >> PubChem)
- PATH 6b: PubChem via target activity (genes >> uniprot >> pubchem_activity >> pubchem[fda])
- PATH 7: Reactome pathways
- PATH 11: Clinical trials
- PATH 12: Patents (chembl_molecule >> patent_compound >> patent)
- PATH 13: BindingDB binding data
- PATH 14: Therapeutic antibodies

Qdrant Paths (TODO):
- PATH 8: Similar proteins (Qdrant ESM-2)
- PATH 9: Similar compounds (Qdrant Morgan FP)
"""

from .base import BasePath, PathResult
from .direct_indications import DirectIndicationsPath
from .gwas import GWASPath
from .clinvar import ClinVarPath
from .pubchem import PubChemPath, PubChemEnrichmentPath, PubChemActivityPath
from .reactome import ReactomePath
from .clinical_trials import ClinicalTrialsPath
from .patents import PatentsPath
from .bindingdb import BindingDBPath
from .antibody import AntibodyPath

__all__ = [
    "BasePath",
    "PathResult",
    "DirectIndicationsPath",
    "GWASPath",
    "ClinVarPath",
    "PubChemPath",
    "PubChemEnrichmentPath",
    "PubChemActivityPath",
    "ReactomePath",
    "ClinicalTrialsPath",
    "PatentsPath",
    "BindingDBPath",
    "AntibodyPath",
]
