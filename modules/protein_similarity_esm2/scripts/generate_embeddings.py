#!/usr/bin/env python3
"""
Generate ESM-2 embeddings for protein sequences

Uses Meta AI's ESM-2 model to generate semantic embeddings
"""

import argparse
import torch
import h5py
import numpy as np
from pathlib import Path
from Bio import SeqIO
from tqdm import tqdm
import esm

def load_model(model_name, device):
    """Load ESM-2 model"""
    print(f"Loading model: {model_name}")
    print(f"Device: {device}")

    if model_name == "esm2_t30_150M_UR50D":
        model, alphabet = esm.pretrained.esm2_t30_150M_UR50D()
    elif model_name == "esm2_t33_650M_UR50D":
        model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
    elif model_name == "esm2_t36_3B_UR50D":
        model, alphabet = esm.pretrained.esm2_t36_3B_UR50D()
    else:
        raise ValueError(f"Unknown model: {model_name}")

    model = model.to(device)
    model.eval()  # Set to evaluation mode

    return model, alphabet


def truncate_sequence(seq, max_len):
    """Truncate sequence if too long"""
    if len(seq) > max_len:
        print(f"Warning: Truncating sequence from {len(seq)} to {max_len} residues")
        return seq[:max_len]
    return seq


def generate_embeddings(fasta_file, output_file, model_name, batch_size,
                       device, repr_layer, max_seq_len):
    """Generate embeddings for all sequences in FASTA file"""

    # Load model
    model, alphabet = load_model(model_name, device)
    batch_converter = alphabet.get_batch_converter()

    # Read sequences
    print(f"Reading sequences from {fasta_file}")
    sequences = []
    for record in SeqIO.parse(fasta_file, "fasta"):
        seq_str = str(record.seq)
        seq_str = truncate_sequence(seq_str, max_seq_len)
        sequences.append((record.id, seq_str))

    print(f"Total sequences: {len(sequences)}")

    # Process in batches
    all_embeddings = []
    all_ids = []

    num_batches = (len(sequences) + batch_size - 1) // batch_size

    with torch.no_grad():  # Disable gradient computation
        for i in tqdm(range(0, len(sequences), batch_size),
                     total=num_batches, desc="Generating embeddings"):
            batch = sequences[i:i + batch_size]

            # Extract IDs and sequences
            batch_ids = [item[0] for item in batch]

            # Convert batch to tokens
            batch_labels, batch_strs, batch_tokens = batch_converter(batch)
            batch_tokens = batch_tokens.to(device)

            # Generate embeddings
            results = model(batch_tokens, repr_layers=[repr_layer])

            # Extract embeddings (mean pooling across sequence length)
            # Shape: [batch_size, seq_len, embedding_dim]
            # We take mean over seq_len to get [batch_size, embedding_dim]
            embeddings = results["representations"][repr_layer].cpu().numpy()

            # Mean pooling (skip special tokens: first and last)
            # BOS (beginning) and EOS (end) tokens
            for j, embedding in enumerate(embeddings):
                # Get sequence length (excluding padding)
                seq_len = len(batch_strs[j])
                # Mean pool over sequence (skip BOS and EOS tokens)
                mean_embedding = embedding[1:seq_len+1].mean(axis=0)
                all_embeddings.append(mean_embedding)
                all_ids.append(batch_ids[j])

    # Convert to numpy array
    all_embeddings = np.array(all_embeddings)

    print(f"Generated embeddings shape: {all_embeddings.shape}")
    print(f"Embedding dimension: {all_embeddings.shape[1]}")

    # Save to HDF5
    print(f"Saving embeddings to {output_file}")
    with h5py.File(output_file, 'w') as f:
        f.create_dataset('embeddings', data=all_embeddings, compression='gzip')
        # Store IDs as strings
        dt = h5py.string_dtype(encoding='utf-8')
        f.create_dataset('ids', data=np.array(all_ids, dtype=object), dtype=dt)

        # Store metadata
        f.attrs['model'] = model_name
        f.attrs['num_sequences'] = len(all_ids)
        f.attrs['embedding_dim'] = all_embeddings.shape[1]
        f.attrs['repr_layer'] = repr_layer

    print(f"Saved {len(all_ids)} embeddings")
    print(f"Output file size: {Path(output_file).stat().st_size / 1024 / 1024:.2f} MB")


def main():
    parser = argparse.ArgumentParser(description='Generate ESM-2 embeddings')
    parser.add_argument('input_fasta', type=Path, help='Input FASTA file')
    parser.add_argument('output_h5', type=Path, help='Output HDF5 file')
    parser.add_argument('--model', default='esm2_t33_650M_UR50D',
                       help='ESM-2 model name')
    parser.add_argument('--batch-size', type=int, default=16,
                       help='Batch size for processing')
    parser.add_argument('--device', default='auto',
                       help='Device: cuda, cpu, or auto')
    parser.add_argument('--repr-layer', type=int, default=33,
                       help='Representation layer to extract')
    parser.add_argument('--max-seq-len', type=int, default=1024,
                       help='Maximum sequence length')

    args = parser.parse_args()

    # Determine device
    if args.device == 'auto':
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    else:
        device = torch.device(args.device)

    print("=" * 80)
    print("ESM-2 Embedding Generation")
    print("=" * 80)
    print(f"Input: {args.input_fasta}")
    print(f"Output: {args.output_h5}")
    print(f"Model: {args.model}")
    print(f"Batch size: {args.batch_size}")
    print(f"Device: {device}")
    print(f"Repr layer: {args.repr_layer}")
    print(f"Max sequence length: {args.max_seq_len}")
    print("=" * 80)

    # Create output directory
    args.output_h5.parent.mkdir(parents=True, exist_ok=True)

    # Generate embeddings
    generate_embeddings(
        args.input_fasta,
        args.output_h5,
        args.model,
        args.batch_size,
        device,
        args.repr_layer,
        args.max_seq_len
    )

    print("=" * 80)
    print("Embedding generation complete!")
    print("=" * 80)


if __name__ == '__main__':
    main()
