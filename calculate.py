#!/usr/bin/env python3
"""Reproduce the published public-evidence comparison from canonical CSV files.

The documented result ranks confirmed public features of selected learning offers,
not the independently observed educational quality of paid courses.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parent
CRITERIA = tuple("ABCDEFG")
WEIGHTS_ORIGINAL_SHA256 = "10076b2a18d120f08d1f5c1071f9750e5cee91801c7f0c49d9bfff498a8da851"


def rows(filename: str) -> list[dict[str, str]]:
    with (ROOT / filename).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main() -> None:
    model = rows("SCORING_MODEL.csv")
    matrix = rows("SCORE_MATRIX.csv")
    weights = rows("WEIGHTS_AND_SENSITIVITY_5000_FROZEN.csv")
    expected = json.loads((ROOT / "SENSITIVITY_AFTER_G1_2026_11_04.json").read_text(encoding="utf-8"))

    base = {r["criterion_id"]: float(r["maximum_points"]) for r in model}
    assert set(base) == set(CRITERIA), base
    assert sum(base.values()) == 100.0

    rubrics = rows("RUBRICS.csv")
    assert len(rubrics) == 22 and len(matrix) == 220 and len(weights) == 5000

    candidates: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in matrix:
        assert r["criterion"] in base, r
        lo, hi, mx = map(float, (r["evidence_floor"], r["theoretical_ceiling"], r["max_points"]))
        assert 0 <= lo <= hi <= mx, r
        candidates[r["candidate_id"]].append(r)
    assert len(candidates) == 10 and all(len(r) == 22 for r in candidates.values())

    totals = {c: sum(float(r["evidence_floor"]) for r in rr) for c, rr in candidates.items()}
    assert totals["C01"] == 93 and totals["C08"] == 80 and totals["C09"] == 74, totals
    assert totals == expected["baseline_points"], totals

    original_hash = hashlib.sha256((ROOT / "WEIGHTS_AND_SENSITIVITY_5000_FROZEN.csv").read_bytes()).hexdigest()
    if original_hash != WEIGHTS_ORIGINAL_SHA256:
        raise AssertionError(f"Frozen weights hash mismatch: {original_hash}")

    winners: Counter[str] = Counter()
    runners_up: Counter[str] = Counter()
    minimum_gap = float("inf")
    robust_all = robust_top3 = robust_lektorium = robust_level_one = 0

    for w in weights:
        weighted: dict[str, tuple[float, float]] = {}
        factors = {c: float(w["weight_" + c]) / base[c] for c in CRITERIA}
        assert abs(sum(float(w["weight_" + c]) for c in CRITERIA) - 100) < 1e-3
        for cid, rr in candidates.items():
            lo = sum(float(r["evidence_floor"]) * factors[r["criterion"]] for r in rr)
            hi = sum(float(r["theoretical_ceiling"]) * factors[r["criterion"]] for r in rr)
            weighted[cid] = (lo, hi)

        ordered = sorted(weighted, key=lambda c: (-weighted[c][0], c))
        winners[ordered[0]] += 1
        runners_up[ordered[1]] += 1
        minimum_gap = min(minimum_gap, weighted[ordered[0]][0] - weighted[ordered[1]][0])
        sync = weighted["C01"][0]
        ceiling_other = max(hi for c, (_, hi) in weighted.items() if c != "C01")
        robust_all += int(sync > ceiling_other)
        robust_top3 += int(sync > max(weighted["C08"][1], weighted["C09"][1]))
        robust_lektorium += int(sync > weighted["C08"][1])
        robust_level_one += int(sync > weighted["C09"][1])

    actual = {
        "vector_count": len(weights),
        "component_count": len(matrix),
        "confirmed_winner_counts": dict(winners),
        "confirmed_second_place_counts": dict(runners_up),
        "min_confirmed_winner_margin": round(minimum_gap, 4),
        "robust_leader_across_all_10": robust_all,
        "robust_leader_against_C08_C09": robust_top3,
        "robust_leader_against_C08": robust_lektorium,
        "robust_leader_against_C09": robust_level_one,
    }
    for key, value in actual.items():
        assert value == expected[key], (key, value, expected[key])

    public = json.loads((ROOT / "RESULTS.json").read_text(encoding="utf-8"))
    assert len(public["offer_comparisons"]) == 10
    assert public["principal_result"]["confirmed_points"] == totals["C01"]
    assert public["full_market_top10_status"] == "HOLD"
    print(json.dumps({"PASS": True, "scores": totals, "sensitivity": actual}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
