#!/usr/bin/env python3
"""Quantize microsoft/FastContext-1.0-4B-SFT with different MLX strategies.

Usage:
    python benchmark/quantize.py                    # all default variants
    python benchmark/quantize.py --methods affine4   # single variant
    python benchmark/quantize.py --list              # show available methods
"""

import argparse
import json
import sys
import time
from pathlib import Path

BASE_MODEL = "microsoft/FastContext-1.0-4B-SFT"
OUTPUT_DIR = Path.home() / ".cache" / "fastcontext" / "quantized"

METHODS = {
    "affine4-g64": {
        "description": "Affine 4-bit, group_size=64 (matches mattrobenolt's)",
        "bits": 4,
        "group_size": 64,
    },
    "affine4-g32": {
        "description": "Affine 4-bit, group_size=32 (finer granularity)",
        "bits": 4,
        "group_size": 32,
    },
    "affine8": {
        "description": "Affine 8-bit (quality reference)",
        "bits": 8,
        "group_size": 64,
    },
    "affine3": {
        "description": "Affine 3-bit (speed reference, lower quality)",
        "bits": 3,
        "group_size": 64,
    },
}


def list_methods():
    for name, cfg in METHODS.items():
        print(f"  {name:20s}  {cfg['description']}")


def quantize_model(method_name: str, config: dict) -> Path:
    from mlx_lm import convert

    out_path = OUTPUT_DIR / method_name
    if out_path.exists() and (out_path / "config.json").exists():
        print(f"  {method_name}: already exists at {out_path}, skipping")
        return out_path

    if out_path.exists():
        import shutil
        shutil.rmtree(out_path)
    print(f"  {method_name}: quantizing {BASE_MODEL} -> {out_path}")
    print(f"    bits={config['bits']}, group_size={config['group_size']}")

    t0 = time.time()
    convert(
        BASE_MODEL,
        quantize=True,
        q_bits=config["bits"],
        q_group_size=config["group_size"],
        mlx_path=str(out_path),
    )
    elapsed = time.time() - t0
    print(f"    done in {elapsed:.1f}s")

    meta = {
        "base_model": BASE_MODEL,
        "method": method_name,
        "bits": config["bits"],
        "group_size": config["group_size"],
        "quantize_time_s": round(elapsed, 1),
    }
    (out_path / "quant_meta.json").write_text(json.dumps(meta, indent=2))
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Quantize FastContext for MLX benchmarking")
    parser.add_argument("--methods", nargs="*", default=None, help="Methods to quantize (default: all)")
    parser.add_argument("--list", action="store_true", help="List available methods")
    args = parser.parse_args()

    if args.list:
        list_methods()
        return

    methods = args.methods or list(METHODS.keys())
    for name in methods:
        if name not in METHODS:
            print(f"Unknown method: {name}. Available: {', '.join(METHODS.keys())}")
            sys.exit(1)

    print(f"Base model: {BASE_MODEL}")
    print(f"Output dir: {OUTPUT_DIR}")
    print(f"Methods: {', '.join(methods)}")
    print()

    for name in methods:
        quantize_model(name, METHODS[name])
    print("\nAll done.")


if __name__ == "__main__":
    main()
