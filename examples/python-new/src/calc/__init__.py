"""Tiny calculator used to prove eqk adoption on a brand-new project."""


def add(a: float, b: float) -> float:
    return a + b


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean() of empty list")
    return sum(values) / len(values)
