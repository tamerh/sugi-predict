#!/usr/bin/env python3
"""
SaProt Stage 3 -- wt-marginal LLR scoring (GPU; runs on a rented RunPod A100).

Reads combined_seqs.jsonl ({"acc","aa","combined"}), scores every missense with
SaProt via WT-MARGINAL (one forward pass per protein, no per-position masking),
and writes the handoff TSV (uniprot, protein_variant, position, llr, gene_symbol),
gzipped, no header. Skips the WT (diagonal); only WT != MUT rows.

Scoring matches SaProt's own predict_pos_mut math -- P(aa) at a position is the
model's probability summed over that AA paired with all 3Di structure tokens
(marginalize structure), and LLR = log P(mut) - log P(wt) -- but WITHOUT masking
(1 pass/protein instead of L). Done via logsumexp on log-probs (= log of the summed
probs), numerically stable.

  python score_saprot.py \
    --combined /data/bioyoda/out_prod/work/saprot/combined_seqs.jsonl \
    --genes    /data/biobtree/raw_data/esm1b/isoform_list.csv \
    --model    westlake-repl/SaProt_650M_AF2 \
    --saprot   /data/bioyoda/raw_data/saprot/tools/SaProt \
    --out      /data/bioyoda/out_prod/work/saprot/saprot_llr.tsv.gz \
    --batch 8 [--limit N] [--device cuda]
"""
import os, sys, csv, json, gzip, argparse, time
import torch


def load_genes(path):
    g = {}
    with open(path, newline="") as f:
        r = csv.reader(f)
        next(r, None)  # header: id,txt
        for row in r:
            if len(row) >= 2:
                g[row[0].strip()] = row[1].split("(")[0].strip()  # GENE before " ("
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--combined", required=True)
    ap.add_argument("--genes", required=True)
    ap.add_argument("--model", default="westlake-repl/SaProt_650M_AF2")
    ap.add_argument("--saprot", required=True, help="path to the SaProt repo (for utils.constants)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()

    sys.path.insert(0, a.saprot)
    from utils.constants import aa_list, foldseek_struc_vocab
    from transformers import EsmTokenizer, EsmForMaskedLM

    device = a.device if torch.cuda.is_available() else "cpu"
    print("[score] device=%s model=%s" % (device, a.model), flush=True)
    tok = EsmTokenizer.from_pretrained(a.model)
    model = EsmForMaskedLM.from_pretrained(a.model).to(device).eval()
    vocab = tok.get_vocab()
    n3di = len(foldseek_struc_vocab)
    aa_start = {aa: vocab[aa + foldseek_struc_vocab[0]] for aa in aa_list}  # vocab index of "<aa><first-3di>"
    # [20, n3di] gather index: row i = the vocab ids of aa_list[i] paired with every 3Di token.
    # logsumexp over the last dim marginalizes structure -> log P(aa) per position (SaProt's sum-of-probs, in log space).
    aa_idx = torch.tensor([[aa_start[aa] + k for k in range(n3di)] for aa in aa_list], device=device)
    aa_pos = {aa: i for i, aa in enumerate(aa_list)}
    naa = len(aa_list)

    genes = load_genes(a.genes)

    recs = []
    with open(a.combined) as f:
        for line in f:
            recs.append(json.loads(line))
            if a.limit and len(recs) >= a.limit:
                break
    print("[score] %d proteins" % len(recs), flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)

    out = gzip.open(a.out, "wt")
    t0, nrows, done = time.time(), 0, 0
    with torch.no_grad():
        for i in range(0, len(recs), a.batch):
            batch = recs[i:i + a.batch]
            seqs = [" ".join(tok.tokenize(r["combined"])) for r in batch]
            enc = tok(seqs, return_tensors="pt", padding=True).to(device)
            logp = torch.log_softmax(model(**enc).logits, dim=-1)     # [B, L+2, vocab]
            # marginalize 3Di per AA in one vectorized op, then pull to CPU ONCE per batch
            # (no per-row GPU sync): [B, L+2, naa, n3di] -> logsumexp -> [B, L+2, naa]
            aa_logp = torch.logsumexp(logp[:, :, aa_idx], dim=-1).cpu()
            for b, r in enumerate(batch):
                acc, aa, gene = r["acc"], r["aa"], genes.get(r["acc"], "")
                mat = aa_logp[b].tolist()           # [L+2][naa] python floats, one sync
                buf = []
                for pos in range(len(aa)):          # 0-based residue
                    wi = aa_pos.get(aa[pos])
                    if wi is None:
                        continue
                    row = mat[pos + 1]              # CLS at token index 0
                    wt_lp = row[wi]
                    p1 = pos + 1
                    for mi in range(naa):
                        if mi == wi:
                            continue
                        buf.append("%s\t%s%d%s\t%d\t%.3f\t%s"
                                   % (acc, aa[pos], p1, aa_list[mi], p1, row[mi] - wt_lp, gene))
                if buf:
                    out.write("\n".join(buf) + "\n")
                    nrows += len(buf)
                done += 1
            if done % 200 < a.batch:
                print("[score] %d/%d proteins, %d rows (%.1f prot/s)"
                      % (done, len(recs), nrows, done / (time.time() - t0)), flush=True)
    out.close()
    print("[score] DONE %d proteins, %d rows in %.0fs -> %s"
          % (done, nrows, time.time() - t0, a.out), flush=True)


if __name__ == "__main__":
    sys.exit(main())
