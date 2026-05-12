from __future__ import annotations

import math
import random


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def bootstrap_ci(
    values: list[float],
    samples: int = 1000,
    seed: int | None = None,
) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])
    rng = random.Random(seed)
    boots: list[float] = []
    for _ in range(samples):
        draw = [rng.choice(values) for _ in values]
        boots.append(mean(draw))
    boots.sort()
    lo = boots[int(0.025 * len(boots))]
    hi = boots[int(0.975 * len(boots))]
    return (lo, hi)
