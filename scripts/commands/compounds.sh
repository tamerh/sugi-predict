#!/bin/bash
##############################################################################
#
#   BioYoda Compound Commands
#   Exact-Tanimoto FTO / chemical-density over the 30.9M patent-compound
#   substrate (FPSim2). Companion to Qdrant top-k similarity: this serves the
#   EXHAUSTIVE threshold / "what's-claimed-within-T" / density queries.
#
##############################################################################

# Source common libraries
COMMANDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMANDS_DIR}/../lib/common.sh"

compounds_help() {
    cat << 'EOF'
Compound substrate — exact-Tanimoto FTO / chemical-density (FPSim2, 30.9M patent compounds)

Usage: bioyoda.sh compounds <subcommand> [options]

Subcommands:
    fto <query>     Exact claimed-density + exhaustive neighbors for a molecule (Mode B)
                    <query> = SMILES | SCHEMBL<id> | drug-name (resolved via biobtree)
    xmodal <drug>   Cross-modal dossier: drug -> target -> ESM-2 twilight homolog ->
                    grounded evidence + druggability (Mode C; <drug> = name | ChEMBL id)
    predict <act>   "Modeller": train a predictor on frozen ECFP4 / score molecules (Mode D)
                      train <labeled.csv> [--smiles-col S --label-col L --model logreg|rf --out M.pkl]
                      score <model.pkl> <input>   (input = a .csv OR SMILES|SCHEMBL<id>|drug-name)
    target <mol>    Predict a molecule's protein target(s) by chemical k-NN to the ChEMBL reference,
                    ranked top-5 + Tanimoto confidence, grounded (the validated target-atlas engine)

FTO Options:
    --threshold N   Tanimoto cutoff for the exhaustive neighbor list (default: 0.4)
    --list N        Show top-N neighbors (default: 10)

Examples:
    bioyoda.sh compounds fto osimertinib
    bioyoda.sh compounds fto "COc1cc(N(C)CCN(C)C)c(NC(=O)C=C)cc1Nc1nccc(-c2cn(C)c3ccccc23)n1" --threshold 0.5
    bioyoda.sh compounds fto SCHEMBL29353024 --list 20
    bioyoda.sh compounds xmodal crizotinib
    bioyoda.sh compounds predict train labels.csv --smiles-col mol --label-col Class
    bioyoda.sh compounds predict score work/qsar_models/labels.pkl osimertinib
EOF
}

cmd_compounds() {
    if [[ $# -eq 0 ]]; then
        compounds_help
        exit 1
    fi

    local subcommand=$1
    shift

    case $subcommand in
        fto)            compounds_fto "$@" ;;
        xmodal)         compounds_xmodal "$@" ;;
        predict)        compounds_predict "$@" ;;
        target)         compounds_target "$@" ;;
        help|--help|-h) compounds_help ;;
        *)
            log_error "Unknown compounds subcommand: $subcommand"
            compounds_help
            exit 1
            ;;
    esac
}

# Exact-Tanimoto FTO / density query (Mode B). Usage: bioyoda.sh compounds fto <query> [opts]
compounds_fto() {
    if [[ $# -eq 0 ]]; then
        compounds_help
        exit 1
    fi
    local py="/data/miniconda3/envs/bioyoda/bin/python"
    [[ -x "$py" ]] || py="python3"
    "$py" /data/bioyoda/modules/compounds/fto.py "$@"
}

# Cross-modal dossier (Mode C). Usage: bioyoda.sh compounds xmodal <drug>
compounds_xmodal() {
    if [[ $# -eq 0 ]]; then
        compounds_help
        exit 1
    fi
    local py="/data/miniconda3/envs/bioyoda/bin/python"
    [[ -x "$py" ]] || py="python3"
    "$py" /data/bioyoda/modules/compounds/xmodal.py "$@"
}

# Modeller: train/score a frozen-FP predictor (Mode D). Usage: bioyoda.sh compounds predict <train|score> ...
compounds_predict() {
    if [[ $# -eq 0 ]]; then
        compounds_help
        exit 1
    fi
    local py="/data/miniconda3/envs/bioyoda/bin/python"
    [[ -x "$py" ]] || py="python3"
    "$py" /data/bioyoda/modules/compounds/qsar.py "$@"
}

# Target-atlas engine: predict a molecule's protein target(s). Usage: bioyoda.sh compounds target <mol>
compounds_target() {
    if [[ $# -eq 0 ]]; then
        compounds_help
        exit 1
    fi
    local py="/data/miniconda3/envs/bioyoda/bin/python"
    [[ -x "$py" ]] || py="python3"
    "$py" /data/bioyoda/modules/compounds/target.py "$@"
}
