#!/usr/bin/env python3
"""Focused tests for input_pipeline.py that do not require RDKit."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("input_pipeline.py")
SPEC = importlib.util.spec_from_file_location("input_pipeline", SCRIPT)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class InputPipelineTests(unittest.TestCase):
    def test_memory_parsing(self) -> None:
        self.assertEqual(pipeline.parse_memory_to_mb("8GB"), 8192)
        self.assertEqual(pipeline.parse_memory_to_mb("64000MB"), 64000)
        self.assertEqual(pipeline.parse_memory_to_mb("1.5GB"), 1536)

    def test_orca_maxcore(self) -> None:
        self.assertEqual(pipeline.orca_maxcore_mb(8192, 4), 1536)
        self.assertEqual(pipeline.orca_maxcore_mb(1024, 8), 96)

    def test_rule_selection(self) -> None:
        library = pipeline.load_benchmark_library()
        rule = pipeline.select_rule("opt-freq", library)
        self.assertEqual(rule["id"], "optfreq-r2scan3c")

    def test_template_rendering(self) -> None:
        rule = pipeline.select_rule("opt-freq", pipeline.load_benchmark_library())
        gaussian = pipeline.render_gaussian_template(rule, 4, 8192, 0, 1, "benzene")
        orca = pipeline.render_orca_template(rule, 4, 8192, 0, 1)
        self.assertIn("%nprocshared=4", gaussian)
        self.assertIn("%mem=8GB", gaussian)
        self.assertIn("[geometry]", gaussian)
        self.assertIn("%maxcore 1536", orca)
        self.assertIn("%pal nprocs 4 end", orca)
        self.assertIn("* xyz 0 1", orca)

    def test_geometry_injection(self) -> None:
        atoms = [{"symbol": "H", "x": 0.0, "y": 0.0, "z": 0.0}]
        rendered = pipeline.inject_geometry("before\n[geometry]\nafter\n", atoms)
        self.assertIn("H      0.00000000", rendered)
        self.assertNotIn("[geometry]", rendered)


if __name__ == "__main__":
    unittest.main()
