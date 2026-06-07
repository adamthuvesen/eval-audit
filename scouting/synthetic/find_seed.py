"""Scan candidate `random_seed` values for the synthetic fixture and report
the first seed (or all seeds) that satisfy every acceptance criterion declared
in `spec.yaml`.

This is a deterministic helper for picking the `random_seed` to commit. It does
not write any canonical files; it generates each candidate in a tempdir via
`generate.run(check_only=True)`-equivalent logic.

Usage:
    cd scouting/synthetic && python find_seed.py
    cd scouting/synthetic && python find_seed.py --start 30000000 --budget 5000
    cd scouting/synthetic && python find_seed.py --all --budget 200
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# Re-use the generator's helpers; this script lives alongside generate.py.
sys.path.insert(0, str(Path(__file__).parent))
import generate  # type: ignore[import-not-found]


def _evaluate_seed(spec_template: dict, seed: int) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Run generation with `seed` against an in-memory spec, return (all_ok, results)."""
    spec = dict(spec_template)
    # Deep-enough copy: design dict is the only place we mutate.
    spec["design"] = {**spec_template["design"], "random_seed": seed}

    # generate._generate_to writes parquet to a real path; use an in-process tempdir.
    import tempfile
    from pathlib import Path as _P

    with tempfile.TemporaryDirectory(prefix=f"seed-{seed}-") as tmp:
        runs_path = _P(tmp) / "runs.parquet"
        truth_path = _P(tmp) / "truth.json"
        rows, truth = generate._generate_to(spec, runs_path, truth_path)
        results = generate._evaluate_criteria(spec, rows, truth)

    return all(ok for _, ok, _ in results), results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=20_260_502, help="first seed to try")
    parser.add_argument("--budget", type=int, default=10_000, help="max seeds to try")
    parser.add_argument(
        "--all",
        action="store_true",
        help="print every passing seed in the budget (instead of stopping at first)",
    )
    args = parser.parse_args()

    spec = yaml.safe_load(generate.SPEC_PATH.read_text())
    # Ensure acceptance_criteria is present (re-uses generator's check).
    missing = [
        k
        for k in generate.REQUIRED_CRITERIA_KEYS
        if k not in (spec.get("acceptance_criteria") or {})
    ]
    if missing:
        sys.stderr.write(f"spec.yaml is missing required acceptance_criteria keys: {missing}\n")
        sys.exit(2)

    print(
        f"Scanning seeds in [{args.start}, {args.start + args.budget}) "
        f"({'all matches' if args.all else 'first match'})..."
    )

    pass_counts = {
        name: 0
        for name in (
            "primary_delta_proximity",
            "primary_bootstrap_ci_crosses_zero",
            "pareto_membership_match",
            "per_agent_rate_proximity",
        )
    }
    found: list[int] = []

    for offset in range(args.budget):
        seed = args.start + offset
        ok, results = _evaluate_seed(spec, seed)
        for name, criterion_ok, _ in results:
            if criterion_ok:
                pass_counts[name] += 1
        if ok:
            found.append(seed)
            if args.all:
                print(f"PASS seed={seed}")
            else:
                print(f"\nFIRST passing seed: {seed}")
                for _name, _ok, msg in results:
                    print(f"  {msg}")
                sys.exit(0)
        if (offset + 1) % 100 == 0 and not args.all:
            print(f"  ...checked {offset + 1} seeds, no full pass yet", file=sys.stderr)

    if args.all:
        print(f"\nScanned {args.budget} seeds; {len(found)} satisfied all criteria.")
        if found:
            print("Passing seeds:", found)
            sys.exit(0)
    else:
        sys.stderr.write(
            f"\nNo seed in [{args.start}, {args.start + args.budget}) satisfied all criteria.\n"
            "Per-criterion pass counts:\n"
        )
        for name, count in pass_counts.items():
            sys.stderr.write(f"  {name}: {count}/{args.budget}\n")
        sys.stderr.write(
            "\nIf the most-binding criterion has a low pass count, consider loosening that "
            "tolerance in spec.yaml (per design.md mitigations).\n"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
