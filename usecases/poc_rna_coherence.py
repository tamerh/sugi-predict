#!/usr/bin/env python3
"""PoC 1 (RNA modality) — does an RNA language model produce MEANINGFUL vectors?

The RNA analog of the protein/peptide coherence test. The "atlas recipe" needs an encoder where
similar-vector => similar-behavior. Here "behavior" proxy = Rfam family (sequences in the same Rfam
family are homologous / share a function & structure). If RNA-FM embeddings are meaningful, a held-out
sequence's nearest neighbour (in embedding space) should be in the SAME Rfam family far above chance.

The protein-homology attempt FAILED (ESM-2 similarity 2% < random). So we DO NOT assume; we test with
two hard controls:
  CONTROL A (shuffled-sequence NULL): di-nucleotide-shuffle every sequence (destroys real motif/structure
            order but keeps length + base composition), re-embed, re-run NN. A meaningful encoder must
            collapse to ~chance on shuffled input. If shuffled scores ~as high as real, the "signal" is
            just length/composition leakage, not biology.
  CONTROL B (chance): 1/n_families, the rate of guessing a neighbour's family at random.

Encoder: multimolecule/rnafm (RNA-FM, 12L, 640-d, ESM-style). multimolecule's tokenizer is broken under
transformers 4.57, so we build the token ids manually from the published vocab (single-nucleotide).
Mean-pool over residues (exclude cls/eos/pad), then mean-center + L2-normalize (same as our ESM-2 pipeline).

Data: Rfam 15.1 seed alignments (Rfam.seed.gz). Sample ~30 families x ~25 sequences.
Run: /data/miniconda3/envs/bioyoda/bin/python poc_rna_coherence.py 2>&1 | grep -v -iE "warn|deprecat"
"""
import sys, os, gzip, random, collections
import numpy as np
import torch

SEED = 42
rng = random.Random(SEED)
np.random.seed(SEED); torch.manual_seed(SEED)
SEEDFILE = "/data/bioyoda/work/Rfam.seed.gz"
N_FAMILIES = 30
N_PER_FAM = 25
MIN_LEN, MAX_LEN = 30, 320     # CPU-friendly; RNA-FM max 1024
EMB_CACHE = "/data/bioyoda/work/rna_coherence_emb.npz"

# ---- RNA-FM vocab (from multimolecule/rnafm vocab.txt) : token -> id ----
VOCAB = {"<pad>":0,"<cls>":1,"<eos>":2,"<unk>":3,"<mask>":4,"<null>":5,
         "A":6,"C":7,"G":8,"U":9,"N":10,"R":11,"Y":12,"S":13,"W":14,"K":15,
         "M":16,"B":17,"D":18,"H":19,"V":20,"I":21,"X":22,"|":23,".":24,"*":25,"-":26,"?":27}
CLS, EOS, UNK = 1, 2, 3

def encode_ids(seq):
    ids = [CLS] + [VOCAB.get(c, UNK) for c in seq] + [EOS]
    return ids

# ---- parse Rfam seed (Stockholm), gather family -> list of ungapped RNA seqs ----
def parse_rfam(path):
    fam = {}
    cur_ac = None; seqs = {}
    with gzip.open(path, "rt", errors="ignore") as f:
        for line in f:
            if line.startswith("#=GF AC"):
                cur_ac = line.split()[2]
            elif line.startswith("//"):
                if cur_ac and seqs:
                    fam[cur_ac] = seqs
                cur_ac = None; seqs = {}
            elif line.startswith("#") or not line.strip():
                continue
            else:
                parts = line.split()
                if len(parts) == 2:
                    name, aln = parts
                    seqs[name] = seqs.get(name, "") + aln
    return fam

def clean(aln):
    # remove gaps, uppercase, T->U; keep only standard-ish bases
    s = aln.upper().replace("T", "U")
    s = "".join(c for c in s if c in "ACGU")
    return s

def dinuc_shuffle(s, rng):
    # preserve dinucleotide composition (Altschul-Erikson style, simple Eulerian walk)
    if len(s) < 4:
        l = list(s); rng.shuffle(l); return "".join(l)
    # build graph of dinucleotide edges
    edges = collections.defaultdict(list)
    for a, b in zip(s, s[1:]):
        edges[a].append(b)
    for k in edges:
        rng.shuffle(edges[k])
    # simple walk reconstruction; fall back to mononucleotide shuffle on failure
    start = s[0]; out = [start]; cur = start
    used = collections.defaultdict(int)
    try:
        for _ in range(len(s) - 1):
            nxt = edges[cur][used[cur]]
            used[cur] += 1
            out.append(nxt); cur = nxt
        if len(out) == len(s):
            return "".join(out)
    except IndexError:
        pass
    l = list(s); rng.shuffle(l); return "".join(l)

print("parsing Rfam seed…", flush=True)
fam = parse_rfam(SEEDFILE)
# clean + length filter; keep families with enough usable sequences
usable = {}
for ac, seqs in fam.items():
    cs = []
    seen = set()
    for nm, aln in seqs.items():
        c = clean(aln)
        if MIN_LEN <= len(c) <= MAX_LEN and c not in seen:
            seen.add(c); cs.append(c)
    if len(cs) >= N_PER_FAM:
        usable[ac] = cs
print(f"  {len(fam)} families parsed; {len(usable)} have >= {N_PER_FAM} usable seqs in [{MIN_LEN},{MAX_LEN}]nt")

# sample N_FAMILIES families, N_PER_FAM seqs each
fam_ids = sorted(usable)
rng.shuffle(fam_ids)
fam_ids = fam_ids[:N_FAMILIES]
data = []  # (fam, seq)
for ac in fam_ids:
    pool = list(usable[ac]); rng.shuffle(pool)
    for s in pool[:N_PER_FAM]:
        data.append((ac, s))
labels = np.array([d[0] for d in data])
seqs = [d[1] for d in data]
print(f"  sampled {len(fam_ids)} families x up to {N_PER_FAM} = {len(seqs)} sequences")
print(f"  mean len = {np.mean([len(s) for s in seqs]):.0f}nt   chance NN-same-family = {1/len(fam_ids):.2%}")

# ---- embed with RNA-FM ----
# multimolecule 0.0.5 (the only version whose import works under transformers 4.57) has an OLDER config
# schema than the published checkpoint (HF config.json carries lm_head fields like 'loss_weight' that the
# old MaskedLMHeadConfig rejects). The ENCODER weights we need are independent of the LM head, so we build
# a clean RnaFmConfig from the known architecture (config.json: 12L / 640d / 20 heads / 5120 ffn / vocab 28)
# and load only the base-model weights from the HF safetensors. This is a load-path workaround, NOT a change
# to the model: the transformer blocks + embeddings are the published RNA-FM weights.
from multimolecule.models.rnafm.configuration_rnafm import RnaFmConfig
from multimolecule import RnaFmModel
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
print("loading RNA-FM (clean-config workaround)…", flush=True)
cfg = RnaFmConfig(vocab_size=28, hidden_size=640, num_hidden_layers=12, num_attention_heads=20,
                  intermediate_size=5120, max_position_embeddings=1026, token_dropout=True,
                  emb_layer_norm_before=True, layer_norm_eps=1e-5, pad_token_id=0)
model = RnaFmModel(cfg, add_pooling_layer=False)
wpath = hf_hub_download("multimolecule/rnafm", "model.safetensors")
sd = load_file(wpath)
# keep only encoder/embedding weights (drop lm_head / pretrain heads), strip a leading prefix if present
base_sd = {}
for k, v in sd.items():
    kk = k
    for pref in ("rnafm.", "model."):
        if kk.startswith(pref): kk = kk[len(pref):]
    if kk.startswith(("lm_head", "pretrain", "ss_head", "contact_head", "head.")):
        continue
    # final encoder LayerNorm is named differently across versions
    if kk.startswith("encoder.layer_norm."):
        kk = kk.replace("encoder.layer_norm.", "encoder.emb_layer_norm_after.")
    base_sd[kk] = v
missing, unexpected = model.load_state_dict(base_sd, strict=False)
loaded = len(base_sd) - len(unexpected)
print(f"  loaded {loaded} tensors into encoder; missing={len(missing)} unexpected={len(unexpected)}")
# sanity: the core transformer + embeddings MUST be present (not randomly initialized)
core_missing = [m for m in missing if any(t in m for t in ("encoder.layer", "embeddings.word_embeddings"))]
assert not core_missing, f"core encoder weights missing -> would be random init: {core_missing[:5]}"
model.eval()
dev = "cpu"

@torch.no_grad()
def embed(seq_list, tag):
    out = np.zeros((len(seq_list), 640), dtype=np.float32)
    for i, s in enumerate(seq_list):
        ids = torch.tensor([encode_ids(s)], device=dev)
        h = model(input_ids=ids).last_hidden_state[0]   # (L+2, 640)
        h = h[1:-1]                                       # drop cls/eos
        out[i] = h.mean(0).cpu().numpy()
        if (i + 1) % 50 == 0:
            print(f"    {tag}: embedded {i+1}/{len(seq_list)}", flush=True)
    return out

def normalize(E):
    E = E - E.mean(0, keepdims=True)               # mean-center
    n = np.linalg.norm(E, axis=1, keepdims=True); n[n == 0] = 1
    return E / n

# real embeddings (cache)
if os.path.exists(EMB_CACHE):
    z = np.load(EMB_CACHE, allow_pickle=True)
    E_real = z["real"]; E_shuf = z["shuf"]
    cached_seqs = list(z["seqs"])
    if cached_seqs != seqs:    # cache stale -> recompute
        E_real = None
    else:
        print("  loaded cached embeddings")
else:
    E_real = None

if E_real is None or (isinstance(E_real, np.ndarray) and E_real.shape[0] != len(seqs)):
    E_real = embed(seqs, "real")
    shuf_seqs = [dinuc_shuffle(s, rng) for s in seqs]
    E_shuf = embed(shuf_seqs, "shuffled-null")
    np.savez(EMB_CACHE, real=E_real, shuf=E_shuf, seqs=np.array(seqs, dtype=object))

E_real_n = normalize(E_real)
E_shuf_n = normalize(E_shuf)

# ---- NN-same-family test (leave-one-out, cosine = dot of normalized) ----
def nn_same_family(E, labels):
    S = E @ E.T
    np.fill_diagonal(S, -2.0)
    nn = S.argmax(1)
    return float(np.mean(labels[nn] == labels)), nn

acc_real, _ = nn_same_family(E_real_n, labels)
acc_shuf, _ = nn_same_family(E_shuf_n, labels)
chance = 1 / len(fam_ids)

# also report k=5 (any of top-5 same family) for the real encoder
def topk_same(E, labels, k=5):
    S = E @ E.T; np.fill_diagonal(S, -2.0)
    idx = np.argsort(-S, axis=1)[:, :k]
    return float(np.mean([(labels[row] == labels[i]).any() for i, row in enumerate(idx)]))

top5_real = topk_same(E_real_n, labels, 5)

print("\n==================== PoC 1 RESULTS — RNA-FM embedding coherence ====================")
print(f"  families={len(fam_ids)}  sequences={len(seqs)}  encoder=multimolecule/rnafm (640-d)")
print(f"  NN-is-same-Rfam-family  REAL sequences      = {acc_real:6.2%}")
print(f"  NN-is-same-Rfam-family  SHUFFLED null       = {acc_shuf:6.2%}   (di-nucleotide shuffle)")
print(f"  NN-is-same-Rfam-family  CHANCE (1/families) = {chance:6.2%}")
print(f"  top-5 any-same-family   REAL                = {top5_real:6.2%}")
gap_chance = acc_real / chance if chance else float('inf')
gap_null = acc_real / acc_shuf if acc_shuf else float('inf')
print(f"\n  REAL / CHANCE   = {gap_chance:5.1f}x")
print(f"  REAL / SHUFFLED = {gap_null:5.1f}x")
# ---- diagnostic: how much of the signal is just length+composition (not learned structure)? ----
# Build a trivial composition feature vector per sequence (length + mononuc + dinuc frequencies) and run
# the SAME NN test. If composition alone already scores high, then a chunk of RNA-FM's score is leakage,
# and the di-nuc-shuffle null (which preserves exactly these features) is the honest control to beat.
def comp_feats(seq_list):
    bases = "ACGU"; dinuc = [a+b for a in bases for b in bases]
    F = np.zeros((len(seq_list), 1 + 4 + 16), dtype=np.float32)
    for i, s in enumerate(seq_list):
        L = max(len(s), 1)
        F[i, 0] = len(s)
        for j, b in enumerate(bases):
            F[i, 1+j] = s.count(b) / L
        for j, d in enumerate(dinuc):
            F[i, 5+j] = sum(1 for a, b in zip(s, s[1:]) if a+b == d) / L
    return F
Fc = comp_feats(seqs)
Fc = (Fc - Fc.mean(0)) / (Fc.std(0) + 1e-9)           # z-score so length doesn't dominate
acc_comp, _ = nn_same_family(normalize(Fc), labels)
print(f"\n  [diagnostic] NN-same-family from LENGTH+COMPOSITION only = {acc_comp:6.2%}")
print(f"  [diagnostic] => di-nuc-shuffle null ({acc_shuf:.1%}) is the honest floor; RNA-FM must beat IT, not just chance.")

# the meaningful comparison: REAL vs the structure-free null that shares composition
verdict = ("VALIDATES" if (acc_real > 0.80 and acc_real - acc_shuf > 0.30 and acc_real > 3*chance)
           else "PARTIAL" if (acc_real > acc_shuf + 0.15 and acc_real > 3*chance)
           else "WEAK/DOESN'T")
print(f"\n  VERDICT: RNA-FM vectors are meaningful iff REAL >> SHUFFLED(composition-null) and >> CHANCE")
print(f"           REAL={acc_real:.1%}  SHUFFLED-null={acc_shuf:.1%}  CHANCE={chance:.1%}  ->  {verdict}")
