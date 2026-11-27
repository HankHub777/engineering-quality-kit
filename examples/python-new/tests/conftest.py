import sys
from pathlib import Path

# src layout without packaging: make `calc` importable for the tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
