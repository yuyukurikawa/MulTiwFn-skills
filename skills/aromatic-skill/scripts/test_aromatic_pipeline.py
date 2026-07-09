#!/usr/bin/env python3
"""Focused tests for aromatic_pipeline.py that do not require Multiwfn."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("aromatic_pipeline.py")
SPEC = importlib.util.spec_from_file_location("aromatic_pipeline", SCRIPT)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


GAUSSIAN_NMR_SNIPPET = """ Entering Gaussian System
 Bq   Isotropic =    12.5000   Anisotropy =     2.0000
    XX=     1.0000   YX=     0.0000   ZX=     0.0000
    XY=     0.0000   YY=     2.0000   ZY=     0.0000
    XZ=     0.0000   YZ=     0.0000   ZZ=     3.0000
 GIAO Magnetic shielding tensor
 Normal termination of Gaussian
"""


class AromaticPipelineTests(unittest.TestCase):
    def test_method_alias_resolution(self) -> None:
        library = pipeline.load_method_library()
        methods = pipeline.resolve_methods("MCI,inics,fipc-nics,lolipop", library)
        self.assertEqual([method["id"] for method in methods], ["mcbo", "nics-1d", "lolipop"])

    def test_gaussian_nmr_detection_and_tensor_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "NICS0001.out"
            path.write_text(GAUSSIAN_NMR_SNIPPET)
            role = pipeline.detect_file_role(path)
            tensors = pipeline.parse_gaussian_nmr_tensors(path)
        self.assertEqual(role["role"], "gaussian_nmr_output")
        self.assertTrue(role["has_bq"])
        self.assertEqual(len(tensors), 1)
        self.assertEqual(tensors[0]["isotropic"], 12.5)
        self.assertEqual(tensors[0]["tensor"][2][2], 3.0)

    def test_parse_int_list_and_override(self) -> None:
        self.assertEqual(pipeline.parse_int_list("1-3,6,8"), [1, 2, 3, 6, 8])
        self.assertEqual(pipeline.format_int_list([1, 2, 3, 6, 8]), "1,2,3,6,8")

    def test_nics_zz_projection(self) -> None:
        tensor = [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 3.0]]
        normal = [0.0, 0.0, 1.0]
        self.assertEqual(pipeline.nics_zz_from_tensor(tensor, normal), -3.0)

    def test_recipe_contains_expected_route(self) -> None:
        library = pipeline.load_method_library()
        method = pipeline.resolve_methods("homa", library)[0]
        recipe = pipeline.recipe_for_method(method, {"ring_atoms": "1,2,3,4,5,6"})
        self.assertIn("25\n6\n0", recipe)
        self.assertIn("1,2,3,4,5,6", recipe)
        self.assertFalse(pipeline.has_placeholders(recipe))

    def test_dry_run_manifest_and_fallback_nics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gaussian = Path(tmpdir) / "scan.out"
            gaussian.write_text(GAUSSIAN_NMR_SNIPPET)
            outdir = Path(tmpdir) / "run"
            with contextlib.redirect_stdout(io.StringIO()):
                code = pipeline.main(
                    [
                        "--aromatic",
                        "--method",
                        "nics-1d",
                        "--input",
                        str(gaussian),
                        "--gaussian-output",
                        str(gaussian),
                        "--ring-atoms",
                        "1-6",
                        "--outdir",
                        str(outdir),
                    ]
                )
            manifest = json.loads((outdir / "manifest.json").read_text())
            fallback_exists = Path(manifest["outputs"]["nics_1d_fallback"]).exists()
        self.assertEqual(code, 0)
        self.assertIn("nics_1d_fallback", manifest["outputs"])
        self.assertTrue(fallback_exists)
        self.assertEqual(manifest["context"]["gaussian_output_role"]["role"], "gaussian_nmr_output")


if __name__ == "__main__":
    unittest.main()
