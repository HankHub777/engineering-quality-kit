from inventory.stock import Item, available, needs_reorder


def test_available_never_negative() -> None:
    assert available(Item("A", on_hand=2, reserved=5)) == 0


def test_available() -> None:
    assert available(Item("A", on_hand=10, reserved=3)) == 7


def test_reorder() -> None:
    assert needs_reorder(Item("A", on_hand=4), threshold=5)
    assert not needs_reorder(Item("A", on_hand=9), threshold=5)
