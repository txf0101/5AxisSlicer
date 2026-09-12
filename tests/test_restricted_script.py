from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.restricted_script import (
    ScriptParseError,
    parse_script,
)


class RestrictedScriptTests(unittest.TestCase):
    def test_parses_calls_and_json_like_literals(self) -> None:
        groups = parse_script(
            """
tube.set_nozzle(
    "nozzle-04",
    interface="M6x1",
    length_mm=-12.5,
    use_collision_envelope=True,
)
tube.set_model_cs(origin=(0, 0, 0), z=[0, 0, 1], x={"axis": None})
"""
        )

        self.assertEqual(len(groups), 2)
        self.assertFalse(groups[0].atomic)
        self.assertEqual(groups[0].calls[0].name, "set_nozzle")
        self.assertEqual(groups[0].calls[0].args, ("nozzle-04",))
        self.assertEqual(
            groups[0].calls[0].kwargs,
            {
                "interface": "M6x1",
                "length_mm": -12.5,
                "use_collision_envelope": True,
            },
        )
        self.assertEqual(groups[1].calls[0].kwargs["origin"], (0, 0, 0))
        self.assertEqual(groups[1].calls[0].kwargs["z"], [0, 0, 1])
        self.assertEqual(groups[1].calls[0].kwargs["x"], {"axis": None})

    def test_parses_rotary_axis_word_mapping_without_executing_python(self) -> None:
        call = parse_script("tube.set_machine_axis_words({'A': 'u', 'C': 'w'}, name='DIY U/W')")[
            0
        ].calls[0]

        self.assertEqual(call.name, "set_machine_axis_words")
        self.assertEqual(call.args, ({"A": "u", "C": "w"},))
        self.assertEqual(call.kwargs, {"name": "DIY U/W"})

    def test_maps_every_chinese_alias_to_canonical_name(self) -> None:
        aliases = {
            "帮助": "help",
            "状态": "state",
            "问题": "issues",
            "校验": "validate",
            "创建操作": "create_operation",
            "设置操作": "set_operation",
            "确认零件": "confirm_part",
            "设置机床": "set_machine",
            "设置旋转轴字": "set_machine_axis_words",
            "设置喷嘴": "set_nozzle",
            "设置材料": "set_material",
            "设置模型坐标": "set_model_cs",
            "设置构建坐标": "set_build_cs",
            "设置装夹": "set_placement",
            "撤销": "undo",
            "重做": "redo",
        }
        source = "\n".join(f"管状.{alias}()" for alias in aliases)

        groups = parse_script(source)

        self.assertEqual([group.calls[0].name for group in groups], list(aliases.values()))

    def test_parses_english_and_chinese_transactions(self) -> None:
        groups = parse_script(
            """
with tube.transaction():
    tube.set_machine("machine")
    管状.设置材料("pla", review_confirmed=True)
with 管状.事务():
    tube.set_placement("plate")
"""
        )

        self.assertEqual(len(groups), 2)
        self.assertTrue(groups[0].atomic)
        self.assertEqual([call.name for call in groups[0].calls], ["set_machine", "set_material"])
        self.assertTrue(groups[1].atomic)
        self.assertEqual(groups[1].calls[0].name, "set_placement")

    def test_reports_one_based_character_locations(self) -> None:
        group = parse_script("管状.状态()\n")[0]

        self.assertEqual((group.calls[0].line, group.calls[0].column), (1, 1))
        with self.assertRaises(ScriptParseError) as caught:
            parse_script("管状.设置机床(未知)")
        self.assertEqual((caught.exception.line, caught.exception.column), (1, 9))

    def test_accepts_blank_or_comment_only_script(self) -> None:
        self.assertEqual(parse_script("# 设置脚本\n\n"), ())

    def test_rejects_unknown_or_mixed_commands(self) -> None:
        for source in ("tube.unknown()", "tube.设置机床()", "管状.set_machine()"):
            with self.subTest(source=source):
                self.assert_error(source, "E_COMMAND_UNKNOWN")

    def test_rejects_python_execution_surfaces(self) -> None:
        samples = (
            "import os",
            "value = 1",
            "eval('1')",
            "tube.__class__()",
            "tube.set_machine(value)",
            "tube.set_machine(items[0])",
            "tube.set_machine(lambda: 1)",
            "tube.set_machine([x for x in []])",
            "for x in []:\n    tube.state()",
            "if True:\n    tube.state()",
            "try:\n    tube.state()\nexcept:\n    tube.state()",
            "tube.state(); tube.state()",
            "tube.set_machine(*['machine'])",
            "tube.set_machine(**{'resource_id': 'machine'})",
        )
        for source in samples:
            with self.subTest(source=source):
                with self.assertRaises(ScriptParseError) as caught:
                    parse_script(source)
                self.assertIn(
                    caught.exception.code,
                    {"E_SCRIPT_FORBIDDEN", "E_ARGUMENT_INVALID"},
                )

    def test_rejects_invalid_literal_values(self) -> None:
        samples = (
            "tube.set_machine(1e999)",
            "tube.set_machine(-1e999)",
            "tube.set_machine(+1)",
            "tube.set_machine(--1)",
            "tube.set_machine(1 + 2)",
            "tube.set_machine({1: 'value'})",
            "tube.set_machine({'id': 1, 'id': 2})",
            "tube.set_machine({**{'id': 1}})",
        )
        for source in samples:
            with self.subTest(source=source):
                self.assert_error(source, "E_ARGUMENT_INVALID")

    def test_rejects_transaction_misuse(self) -> None:
        samples = (
            "tube.transaction()",
            "管状.事务()",
            "with tube.transaction(1):\n    tube.set_machine('machine')",
            "with tube.transaction() as tx:\n    tube.set_machine('machine')",
            "with tube.transaction():\n    tube.state()",
            "with tube.transaction():\n    tube.undo()",
            "with tube.transaction():\n    with tube.transaction():\n        tube.set_machine('x')",
        )
        for source in samples:
            with self.subTest(source=source):
                with self.assertRaises(ScriptParseError) as caught:
                    parse_script(source)
                self.assertIn(
                    caught.exception.code,
                    {"E_SCRIPT_FORBIDDEN", "E_ARGUMENT_INVALID"},
                )

    def test_enforces_source_call_and_depth_limits(self) -> None:
        self.assert_error("#" + ("x" * (256 * 1024)), "E_SCRIPT_FORBIDDEN")
        self.assert_error("\n".join("tube.state()" for _ in range(501)), "E_SCRIPT_FORBIDDEN")
        nested = "[" * 40 + "0" + "]" * 40
        self.assert_error(f"tube.set_machine({nested})", "E_SCRIPT_FORBIDDEN")

    def test_syntax_error_has_stable_location(self) -> None:
        with self.assertRaises(ScriptParseError) as caught:
            parse_script("tube.state(\n")

        error = caught.exception
        self.assertEqual(error.code, "E_SCRIPT_SYNTAX")
        self.assertGreaterEqual(error.line, 1)
        self.assertGreaterEqual(error.column, 1)
        self.assertIn("E_SCRIPT_SYNTAX", str(error))

    def assert_error(self, source: str, code: str) -> None:
        with self.assertRaises(ScriptParseError) as caught:
            parse_script(source)
        self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()
