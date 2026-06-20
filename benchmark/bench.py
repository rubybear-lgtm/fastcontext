#!/usr/bin/env python3
"""Local benchmark harness for FastContext quantization comparison.

Runs FastContext against SWE-bench instances using local git clones instead of
Docker. Produces per-instance and aggregate scores for comparing model variants.

Usage:
    # Run baseline 4-bit model on 20 instances:
    python benchmark/bench.py --model mattrobenolt/FastContext-1.0-4B-SFT-mlx-4bit --run-head 20

    # Compare a custom quantization:
    python benchmark/bench.py --model ~/.cache/fastcontext/quantized/affine4-g32 --run-head 20

    # Run all quantized variants:
    python benchmark/bench.py --compare --run-head 20
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"'))

import datasets

BENCH_DIR = Path(__file__).parent
REPO_CACHE = Path.home() / ".cache" / "fastcontext" / "bench_repos"
RESULTS_DIR = BENCH_DIR / "results"

DATASET_MAPPING = {
    "swebench-multilingual": "SWE-bench/SWE-bench_Multilingual",
    "swebench-verified": "princeton-nlp/SWE-Bench_Verified",
    "swebench-pro": "ScaleAI/SWE-bench_Pro",
}

QUANTIZED_DIR = Path.home() / ".cache" / "fastcontext" / "quantized"

# Models to compare in --compare mode
COMPARE_MODELS = {
    "4bit-mattrobenolt": "mattrobenolt/FastContext-1.0-4B-SFT-mlx-4bit",
    "affine4-g64": str(QUANTIZED_DIR / "affine4-g64"),
    "affine4-g32": str(QUANTIZED_DIR / "affine4-g32"),
    "affine8": str(QUANTIZED_DIR / "affine8"),
    "affine3": str(QUANTIZED_DIR / "affine3"),
}


def clone_repo(repo: str, commit: str) -> Path:
    """Clone a repo and checkout a specific commit, caching for reuse.

    Returns a short symlink path like /tmp/fc_bench/<repo_name> so the model
    sees a workspace path it can work with (it struggles with deeply nested paths).
    """
    cache_dir = REPO_CACHE / repo.replace("/", "__") / commit[:12]
    if not (cache_dir.exists() and (cache_dir / ".git").exists()):
        cache_dir.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/{repo}.git"
        print(f"    Cloning {repo}@{commit[:12]}...")
        subprocess.run(
            ["git", "clone", "--quiet", url, str(cache_dir)],
            check=True, capture_output=True, timeout=300,
        )
        subprocess.run(
            ["git", "checkout", "--quiet", commit],
            cwd=str(cache_dir), check=True, capture_output=True, timeout=60,
        )

    link_path = Path("/tmp/testbed")
    if link_path.is_symlink() or link_path.exists():
        link_path.unlink()
    link_path.symlink_to(cache_dir)
    return link_path


def run_single_instance(model_path: str, instance: dict, max_turns: int = 6) -> dict:
    """Run FastContext on a single SWE-bench instance in a subprocess."""
    instance_id = instance["instance_id"]
    repo = instance["repo"]
    commit = instance["base_commit"]
    patch = instance["patch"]
    query = instance["problem_statement"]

    try:
        repo_dir = clone_repo(repo, commit)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return {
            "instance_id": instance_id,
            "error": f"clone failed: {e}",
            "raw_output": "",
            "citations": [],
            "elapsed": 0,
            "tokens_per_sec": 0,
        }

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        traj_path = tf.name

    runner_script = BENCH_DIR / "_runner.py"
    t0 = time.time()
    try:
        result = subprocess.run(
            [
                sys.executable, str(runner_script),
                "--model", model_path,
                "--work-dir", str(repo_dir),
                "--query", query,
                "--max-turns", str(max_turns),
                "--traj", traj_path,
            ],
            capture_output=True, text=True, timeout=600,
        )
        elapsed = time.time() - t0
        raw_output = result.stdout.strip()

        if result.returncode != 0:
            return {
                "instance_id": instance_id,
                "error": f"runner exit {result.returncode}: {result.stderr[-500:]}",
                "raw_output": raw_output,
                "citations": [],
                "elapsed": elapsed,
                "tokens_per_sec": 0,
            }

        try:
            output_data = json.loads(raw_output)
        except json.JSONDecodeError:
            output_data = {"final_answer": raw_output, "stats": {}}

        sys.path.insert(0, str(BENCH_DIR))
        from scoring import parse_final_answer, parse_patch, score_file, score_line

        workspace = str(repo_dir).rstrip("/") + "/"
        citations = parse_final_answer(output_data.get("final_answer", ""), workspace=workspace)
        edits = parse_patch(patch)

        file_scores = score_file(edits, citations)
        line_scores = score_line(edits, citations)

        return {
            "instance_id": instance_id,
            "error": None,
            "raw_output": output_data.get("final_answer", ""),
            "citations": citations,
            "edits_true": edits,
            "file_scores": file_scores,
            "line_scores": line_scores,
            "elapsed": elapsed,
            "stats": output_data.get("stats", {}),
        }

    except subprocess.TimeoutExpired:
        return {
            "instance_id": instance_id,
            "error": "timeout (600s)",
            "raw_output": "",
            "citations": [],
            "elapsed": 600,
            "tokens_per_sec": 0,
        }
    finally:
        Path(traj_path).unlink(missing_ok=True)


def run_benchmark(model_path: str, instances: list[dict], max_turns: int = 6) -> list[dict]:
    """Run benchmark across all instances sequentially."""
    results = []
    for i, inst in enumerate(instances):
        iid = inst["instance_id"]
        print(f"  [{i+1}/{len(instances)}] {iid}...", end=" ", flush=True)
        result = run_single_instance(model_path, inst, max_turns)
        if result.get("error"):
            print(f"ERROR: {result['error'][:80]}")
        else:
            fs = result["file_scores"]
            print(f"file_f1={fs['f1']:.2f} elapsed={result['elapsed']:.1f}s")
        results.append(result)
    return results


def aggregate_results(results: list[dict]) -> dict:
    """Compute aggregate metrics across all instances."""
    valid = [r for r in results if not r.get("error")]
    n_total = len(results)
    n_valid = len(valid)
    n_error = n_total - n_valid

    if not valid:
        return {"n_total": n_total, "n_valid": 0, "n_error": n_error}

    file_f1s = [r["file_scores"]["f1"] for r in valid]
    file_scores = [r["file_scores"]["score"] for r in valid]
    line_f1s = [r["line_scores"]["f1"] for r in valid]
    line_scores = [r["line_scores"]["score"] for r in valid]
    elapsed = [r["elapsed"] for r in valid]

    return {
        "n_total": n_total,
        "n_valid": n_valid,
        "n_error": n_error,
        "file_f1_mean": sum(file_f1s) / len(file_f1s),
        "file_score_mean": sum(file_scores) / len(file_scores),
        "line_f1_mean": sum(line_f1s) / len(line_f1s),
        "line_score_mean": sum(line_scores) / len(line_scores),
        "elapsed_mean": sum(elapsed) / len(elapsed),
        "elapsed_total": sum(elapsed),
    }


def print_comparison(all_results: dict[str, dict]):
    """Print a comparison table across model variants."""
    print("\n" + "=" * 90)
    print(f"{'Model':<25s} {'N':>3s} {'File F1':>8s} {'File Sc':>8s} {'Line F1':>8s} {'Line Sc':>8s} {'Avg(s)':>7s}")
    print("-" * 90)
    for name, agg in all_results.items():
        if agg["n_valid"] == 0:
            print(f"{name:<25s} {agg['n_total']:>3d}  {'(all errors)':>40s}")
            continue
        print(
            f"{name:<25s} {agg['n_valid']:>3d} "
            f"{agg['file_f1_mean']:>8.3f} {agg['file_score_mean']:>8.3f} "
            f"{agg['line_f1_mean']:>8.3f} {agg['line_score_mean']:>8.3f} "
            f"{agg['elapsed_mean']:>7.1f}"
        )
    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(description="Local FastContext benchmark")
    parser.add_argument("--model", type=str, default=None, help="Model path or HF name")
    parser.add_argument("--bench", type=str, default="swebench-multilingual")
    parser.add_argument("--run-head", type=int, default=20, help="Number of instances to run")
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--compare", action="store_true", help="Run all quantized variants")
    parser.add_argument("--output", type=str, default=None, help="Output JSON path")
    parser.add_argument("--repos", nargs="*", default=None, help="Filter by repo names")
    args = parser.parse_args()

    # Load dataset
    bench_name = DATASET_MAPPING.get(args.bench, args.bench)
    print(f"Loading dataset: {bench_name}")
    ds = datasets.load_dataset(bench_name, split="test")
    instances = list(ds)
    print(f"Loaded {len(instances)} instances")

    if args.repos:
        instances = [i for i in instances if any(r in i["repo"] for r in args.repos)]
        print(f"Filtered to {len(instances)} instances matching repos: {args.repos}")

    if args.run_head:
        instances = instances[:args.run_head]
        print(f"Using first {len(instances)} instances")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.compare:
        models = {}
        for name, path in COMPARE_MODELS.items():
            if path.startswith("/") or path.startswith(str(Path.home())):
                if not Path(path).exists():
                    print(f"Skipping {name}: {path} not found (run quantize.py first)")
                    continue
            models[name] = path

        if not models:
            print("No models available. Run quantize.py first.")
            return

        all_agg = {}
        all_results = {}
        for name, path in models.items():
            print(f"\n{'='*60}")
            print(f"Benchmarking: {name} ({path})")
            print(f"{'='*60}")
            results = run_benchmark(path, instances, args.max_turns)
            agg = aggregate_results(results)
            all_agg[name] = agg
            all_results[name] = results
            print(f"  -> File F1: {agg.get('file_f1_mean', 0):.3f}, "
                  f"Line F1: {agg.get('line_f1_mean', 0):.3f}, "
                  f"Avg time: {agg.get('elapsed_mean', 0):.1f}s")

        print_comparison(all_agg)

        out = args.output or str(RESULTS_DIR / "comparison.json")
        with open(out, "w") as f:
            json.dump({"aggregate": all_agg, "per_instance": {
                name: [
                    {k: v for k, v in r.items() if k != "raw_output"}
                    for r in results
                ]
                for name, results in all_results.items()
            }}, f, indent=2, default=str)
        print(f"\nResults saved to {out}")

    else:
        model = args.model or "mattrobenolt/FastContext-1.0-4B-SFT-mlx-4bit"
        print(f"\nBenchmarking: {model}")
        results = run_benchmark(model, instances, args.max_turns)
        agg = aggregate_results(results)

        print(f"\n{'='*60}")
        print(f"Aggregate Results ({agg['n_valid']}/{agg['n_total']} succeeded)")
        print(f"  File F1:     {agg.get('file_f1_mean', 0):.3f}")
        print(f"  File Score:  {agg.get('file_score_mean', 0):.3f}")
        print(f"  Line F1:     {agg.get('line_f1_mean', 0):.3f}")
        print(f"  Line Score:  {agg.get('line_score_mean', 0):.3f}")
        print(f"  Avg time:    {agg.get('elapsed_mean', 0):.1f}s")
        print(f"{'='*60}")

        out = args.output or str(RESULTS_DIR / "single_run.json")
        with open(out, "w") as f:
            json.dump({"model": model, "aggregate": agg, "per_instance": results
            }, f, indent=2, default=str)
        print(f"Results saved to {out}")


if __name__ == "__main__":
    main()
