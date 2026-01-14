"""Drug Discovery Data Gathering Paths.

Individual query paths for gathering drug discovery evidence:

BioBTree Paths:
- PATH 1: Direct indications (disease >> mondo >> efo >> chembl_molecule)
- PATH 2: GWAS genetic associations (disease >> mondo >> efo >> gwas >> ensembl)
- PATH 3: ClinVar variant associations
- PATH 6a: PubChem enrichment via InChI key (ChEMBL drugs >> InChI >> PubChem)
- PATH 6b: PubChem via target activity (genes >> uniprot >> pubchem_activity >> pubchem[fda])
- PATH 7: Reactome pathways
- PATH 11: Clinical trials
- PATH 12: Patents (chembl_molecule >> patent_compound >> patent)
- PATH 13: BindingDB binding data
- PATH 14: Therapeutic antibodies
- PATH 15: GenCC expert-curated gene-disease associations
- PATH 16: Bgee tissue expression
- PATH 17: GO Gene Ontology enrichment
- PATH 18: PPI protein interactions (STRING)
- PATH 19: PDB protein structures
- PATH 20: InterPro protein domains
- PATH 21: MeSH drug classification/enrichment
- PATH 22: HMDB metabolites
- PATH 23: PubChem Bioactivity (IC50, Ki, Kd, targets, assay details)
- PATH 24: CTD chemical-gene-disease interactions
- PATH 25: DrugCentral drug-target MOA data
- PATH 26: MSigDB gene set enrichment

Qdrant Paths:
- PATH 8: Similar proteins (ESM-2 embeddings, 573K proteins)
- PATH 9: Similar compounds (Morgan fingerprints, 30M+ patent compounds)
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
from .gencc import GenCCPath
from .bgee import BgeeExpressionPath
from .go_enrichment import GOEnrichmentPath
from .ppi import PPIPath
from .structures import StructuresPath
from .interpro import InterProPath
from .mesh_enrichment import MeSHEnrichmentPath
from .hmdb import HMDBPath, HMDBEnrichmentPath
from .similar_proteins import SimilarProteinsPath
from .similar_compounds import SimilarCompoundsPath
from .bioactivity import BioactivityPath
from .ctd import CTDPath
from .drugcentral import DrugCentralPath
from .msigdb import MSigDBPath

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
    "GenCCPath",
    "BgeeExpressionPath",
    "GOEnrichmentPath",
    "PPIPath",
    "StructuresPath",
    "InterProPath",
    "MeSHEnrichmentPath",
    "HMDBPath",
    "HMDBEnrichmentPath",
    "SimilarProteinsPath",
    "SimilarCompoundsPath",
    "BioactivityPath",
    "CTDPath",
    "DrugCentralPath",
    "MSigDBPath",
]
