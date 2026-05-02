"""Dagster repository — loads all generated per-product asset definitions."""
import importlib.util
import sys
from pathlib import Path

from dagster import Definitions, load_assets_from_modules


def _load_generated_assets() -> list:
    generated_dir = Path(__file__).parent / "generated"
    assets = []
    for py_file in sorted(generated_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[py_file.stem] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            if hasattr(mod, "assets"):
                assets.extend(mod.assets)
    return assets


defs = Definitions(assets=_load_generated_assets())
