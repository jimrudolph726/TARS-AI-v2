"""Security and behavior tests for the bounded calculator skill."""

import unittest

from skills import skill_sandbox_exec
from skills.skill_calculator import CalculationError, evaluate_expression


class CalculatorSkillTests(unittest.TestCase):
    def test_arithmetic_and_parentheses(self):
        self.assertEqual(evaluate_expression("(15 / 100) * 240"), 36)

    def test_math_function_and_constant(self):
        self.assertAlmostEqual(evaluate_expression("sin(pi / 2)"), 1.0)

    def test_statistics(self):
        self.assertEqual(evaluate_expression("mean([12, 17, 21, 30])"), 20)

    def test_import_statement_is_rejected(self):
        with self.assertRaises(CalculationError):
            evaluate_expression("import random")

    def test_attribute_escape_is_rejected(self):
        with self.assertRaises(CalculationError):
            evaluate_expression("random._os.getcwd()")

    def test_comprehension_is_rejected(self):
        with self.assertRaises(CalculationError):
            evaluate_expression("sum([x for x in [1, 2, 3]])")

    def test_strings_are_rejected(self):
        with self.assertRaises(CalculationError):
            evaluate_expression("'secret'")

    def test_excessive_power_is_rejected_before_evaluation(self):
        with self.assertRaisesRegex(CalculationError, "power exponent"):
            evaluate_expression("10 ** 10000000")

    def test_excessive_factorial_is_rejected(self):
        with self.assertRaisesRegex(CalculationError, "between 0 and 500"):
            evaluate_expression("factorial(1000000)")

    def test_legacy_executor_never_runs_code(self):
        marker = []
        reply = skill_sandbox_exec.execute(
            {"code": "marker.append('executed')"},
            {"marker": marker},
        )
        self.assertEqual(marker, [])
        self.assertIn("disabled for safety", reply)
        self.assertFalse(skill_sandbox_exec.SKILL["enabled_by_default"])


if __name__ == "__main__":
    unittest.main()
