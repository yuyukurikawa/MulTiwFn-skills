#!/usr/bin/env python3
"""Focused tests for input_pipeline.py that do not require RDKit."""

from __future__ import annotations

import importlib.util
import argparse
from pathlib import Path
import tempfile
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

    def test_noninteractive_program_default(self) -> None:
        args = argparse.Namespace(
            interactive=False,
            smiles="O",
            program=None,
            task="sp",
            cores=2,
            memory="2GB",
            charge=0,
            multiplicity=1,
        )
        prepared = pipeline.prepare_generation_args(args)
        self.assertEqual(prepared.program, "both")

    def test_prompt_missing_args(self) -> None:
        args = argparse.Namespace(
            interactive=True,
            smiles=None,
            program=None,
            task=None,
            cores=None,
            memory=None,
            charge=None,
            multiplicity=None,
            name="molecule",
        )
        answers = iter(["c1ccccc1", "2", "4", "8", "16GB", "0", "1", "benzene"])
        prepared = pipeline.prompt_missing_args(args, input_func=lambda _prompt: next(answers))
        self.assertEqual(prepared.smiles, "c1ccccc1")
        self.assertEqual(prepared.program, "gaussian")
        self.assertEqual(prepared.task, "opt-freq")
        self.assertEqual(prepared.cores, 8)
        self.assertEqual(prepared.memory, "16GB")
        self.assertEqual(prepared.charge, 0)
        self.assertEqual(prepared.multiplicity, 1)
        self.assertEqual(prepared.name, "benzene")

    def test_recommendation_keywords_are_selective(self) -> None:
        rule = pipeline.select_rule("opt-freq", pipeline.load_benchmark_library())
        args = argparse.Namespace(
            smiles="c1ccccc1",
            task="opt-freq",
            charge=0,
            multiplicity=1,
            cores=4,
            program="gaussian",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "recommendation.md"
            pipeline.write_recommendation(path, args, rule, 8192, 1536, [], {"gaussian": "benzene.gjf"})
            text = path.read_text()
        self.assertIn("Gaussian:", text)
        self.assertNotIn("ORCA:", text)
        self.assertNotIn("ORCA maxcore", text)

    def test_resource_summary_is_selective(self) -> None:
        gaussian_resources = pipeline.resource_summary("gaussian", 8192, 1536)
        orca_resources = pipeline.resource_summary("orca", 8192, 1536)
        self.assertEqual(gaussian_resources, {"gaussian_memory": "8GB"})
        self.assertEqual(orca_resources["orca_maxcore_mb"], 1536)

    def test_orca_only_caveats_skip_gaussian_fallback(self) -> None:
        rule = pipeline.select_rule("opt-freq", pipeline.load_benchmark_library())
        caveats = pipeline.caveats_for_program(rule, "orca")
        self.assertFalse(any("Gaussian fallback" in caveat for caveat in caveats))


if __name__ == "__main__":
    unittest.main()
