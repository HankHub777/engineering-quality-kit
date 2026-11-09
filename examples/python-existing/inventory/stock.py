"""Stock arithmetic for a small inventory tool."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    sku: str
    on_hand: int
    reserved: int = 0


def available(item: Item) -> int:
    """Units that can still be promised to a customer."""
    return max(item.on_hand - item.reserved, 0)


def needs_reorder(item: Item, threshold: int) -> bool:
    return available(item) < threshold
