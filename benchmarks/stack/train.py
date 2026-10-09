#!/usr/bin/env python3
"""Regenerate one held-out fold of the frozen commercial AnchorBoost team."""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TRAINING = HERE / "training"
RELEASE = HERE.parents[1]
WEIGHT = TRAINING / "tp2_weights/tabpfn-v2-regressor.ckpt"
WEIGHT_SHA = "2ab5a07d5c41dfe6db9aa7ae106fc6de898326c2765be66505a07e2868c10736"
WEIGHT_URL = "https://huggingface.co/Prior-Labs/TabPFN-v2-reg/resolve/main/tabpfn-v2-regressor.ckpt"


def run(*args):
    print(" ".join(map(str, args)), flush=True)
    subprocess.run([sys.executable, *map(str, args)], cwd=TRAINING, check=True)


def run_jobs(jobs, workers, device):
    def worker(gpu, commands):
        for command in commands:
            env = dict(os.environ)
            if device == "cuda":
                env["CUDA_VISIBLE_DEVICES"] = str(gpu)
            print(" ".join(map(str, command)), flush=True)
            subprocess.run([sys.executable, *map(str, command)], cwd=TRAINING, env=env, check=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker, gpu, jobs[gpu::workers]) for gpu in range(workers)]
        for future in futures:
            future.result()


def weight():
    if WEIGHT.exists() and hashlib.sha256(WEIGHT.read_bytes()).hexdigest() == WEIGHT_SHA:
        return
    WEIGHT.parent.mkdir(parents=True, exist_ok=True)
    temporary = WEIGHT.with_suffix(".download")
    with urllib.request.urlopen(WEIGHT_URL, timeout=60) as source, temporary.open("wb") as target:
        shutil.copyfileobj(source, target)
    assert hashlib.sha256(temporary.read_bytes()).hexdigest() == WEIGHT_SHA, "TabPFN-2 checkpoint SHA-256 differs"
    temporary.replace(WEIGHT)


def train_members(fold, k, device, needs_inner, workers):
    weight()
    if needs_inner:
        jobs = [(TRAINING / "teach_tp2.py", "--fold", fold, "--k", k, "--inner", inner, "--device", device)
                for inner in range(5)]
        jobs.append((TRAINING / "teach_tp2.py", "--fold", fold, "--k", k, "--outer", "--device", device))
        run_jobs(jobs, workers, device)
    else:
        run(TRAINING / "tp2_tables.py", "--features", "v2", "--fold", fold, "--k", k)
        run(TRAINING / "tp2_run.py", "--features", "v2", "--fold", fold, "--k", k,
            "--device", device)
    jobs = []
    for seed in range(13, 33 if not needs_inner else 23):
        if needs_inner:
            jobs += [(TRAINING / "teach_lpm.py", "--fold", fold, "--inner", inner, "--seed", seed,
                      "--ks", k, "--device", device) for inner in range(5)]
        jobs.append((TRAINING / "outer_lpm.py", "--fold", fold, "--k", k, "--seed", seed, "--device", device))
    run_jobs(jobs, workers, device)


def score(fold, k, prediction):
    with np.load(TRAINING / "kit/data/matrix.npz", allow_pickle=False) as data:
        Y = data["Y"].astype(np.float64)
        index = {str(c): i for i, c in enumerate(data["chemicals"])}
    by_chemical = {}
    with (TRAINING / f"kit/tasks/k{k}_queries.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["fold"]) != fold:
                continue
            chemical, design = row["chemical"], int(row["design"])
            q = int(row["query_id"])
            actual = Y[index[chemical], int(row["conc_index"])]
            valid = np.isfinite(actual)
            by_chemical.setdefault(chemical, {}).setdefault(design, []).extend(
                np.abs(prediction[q, valid] - actual[valid]).tolist())
    result = {chemical: float(np.mean([np.mean(designs[d]) for d in range(5)]))
              for chemical, designs in by_chemical.items()}
    assert all(np.isfinite(value) for value in result.values()), "Missing predictions on measured cells"
    ref = RELEASE / f"results/final/baselines/anchorboost_team_k{k}.csv"
    with ref.open(newline="") as handle:
        expected = {r["chemical"]: float(r["mae"]) for r in csv.DictReader(handle) if int(r["fold"]) == fold}
    output = HERE / "output" / f"trained_f{fold}_k{k}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("chemical", "fold", "k", "mae", "reference_mae", "abs_gap"))
        writer.writeheader()
        for chemical, value in result.items():
            writer.writerow({"chemical": chemical, "fold": fold, "k": k, "mae": value,
                             "reference_mae": expected[chemical], "abs_gap": abs(value - expected[chemical])})
    gap = max(abs(value - expected[chemical]) for chemical, value in result.items())
    print(json.dumps({"fold": fold, "k": k, "chemicals": len(result),
                      "mae": float(np.mean(list(result.values()))), "max_per_chemical_gap": gap,
                      "exact_reference_match": gap <= 1e-9, "per_chemical_csv": str(output)}))
    return gap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fold", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--k", type=int, choices=range(1, 5), required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--workers", type=int, default=1, help="Independent CPU workers or CUDA devices")
    parser.add_argument("--strict-reference", action="store_true",
                        help="Fail if fresh stochastic training differs from the frozen per-chemical reference")
    parser.add_argument("--reuse-teacher-units", type=Path,
                        help="Use existing frozen teacher units to refit only the residual model")
    parser.add_argument("--reuse-lpm20", type=Path, help="Existing 20-seed outer LPM prediction archive for a cache check")
    parser.add_argument("--reuse-tp2v", type=Path, help="Existing TP2V member archive for a cache check")
    args = parser.parse_args()
    assert args.workers >= 1
    selection = json.loads((HERE / "selection.json").read_text())["k"][str(args.k)][str(args.fold)]
    if args.reuse_teacher_units:
        source = args.reuse_teacher_units.resolve()
        required = []
        if selection["choice"] != "TL":
            required.append(source / "tp2" / f"outer_f{args.fold}_k{args.k}.npz")
            required.append(source / f"L_test_k{args.k}.npz")
            required += [source / "tp2" / f"f{args.fold}_k{args.k}_j{inner}.npz" for inner in range(5)]
            required += [source / "lpm" / f"f{args.fold}_j{inner}_s{seed}.npz"
                         for seed in range(13, 23) for inner in range(5)]
        missing = [path for path in required if not path.exists()]
        if missing:
            raise SystemExit(f"Frozen teacher cache lacks {len(missing)} units; first missing: {missing[0]}")
        if selection["choice"] != "TL":
            (TRAINING / "teachers/tp2").mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / "tp2" / f"outer_f{args.fold}_k{args.k}.npz",
                         TRAINING / "teachers/tp2" / f"outer_f{args.fold}_k{args.k}.npz")
    else:
        train_members(args.fold, args.k, args.device, selection["choice"] != "TL", args.workers)
        source = TRAINING / "teachers"
    choice = selection["choice"]
    if choice == "TL":
        if args.reuse_teacher_units:
            if args.reuse_lpm20 is None:
                raise SystemExit("--reuse-lpm20 is required for the T+L cache check")
            with np.load(args.reuse_lpm20, allow_pickle=False) as z:
                L = z[f"k{args.k}"]
        else:
            run(TRAINING / "assemble.py", "teachers", "--folds", args.fold, "--ks", args.k,
                "--source-teachers", source, "--only-outer-lpm")
            with np.load(TRAINING / "teachers" / f"L_test_k{args.k}.npz") as z:
                L = z["mean"]
        if args.reuse_teacher_units:
            if args.reuse_tp2v is None:
                raise SystemExit("--reuse-tp2v is required for the T+L cache check")
            with np.load(args.reuse_tp2v, allow_pickle=False) as z:
                T = z[f"k{args.k}"]
        else:
            with np.load(TRAINING / "tp2/runs/TP2V_chemeleon" / f"fold{args.fold}_k{args.k}.npz") as z:
                T = z[f"k{args.k}"]
        result = selection["weights"]["T"] * T + selection["weights"]["L"] * L
    else:
        run(TRAINING / "assemble.py", "teachers", "--seeds", "13-22", "--folds", args.fold, "--ks", args.k,
            "--source-teachers", source)
        run(TRAINING / "v3.py", "--mode", "outer", "--cand", choice, "--fold", args.fold,
            "--k", args.k, "--wt", selection["weights"]["T"], "--wl", selection["weights"]["L"])
        with np.load(TRAINING / "runs" / choice / f"fold{args.fold}_k{args.k}.npz") as z:
            result = z[f"k{args.k}"]
    gap = score(args.fold, args.k, result)
    if args.strict_reference and gap > 1e-9:
        raise SystemExit(f"Refit differs from the frozen result: maximum per-chemical gap {gap:.9g}")


if __name__ == "__main__":
    main()
