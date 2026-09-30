"""The style trace explains which rules applied, what they overrode, and which were skipped."""

import logging
import unittest

from shared import style_trace
from shared.data_models import Event
from shared.rule_engine import DayContext, StyleEngine


class StyleTraceTest(unittest.TestCase):
    def setUp(self):
        style_trace.TRACE.setLevel(logging.DEBUG)

    def tearDown(self):
        style_trace.TRACE.setLevel(logging.NOTSET)

    def test_day_trace_names_applied_overriding_and_skipped_rules(self):
        rules = [
            {"name": "base", "apply_to": "day_box", "select": {"workday": True}, "style": {"fill": "red"}},
            {"name": "over", "apply_to": "day_box", "select": {"workday": True}, "style": {"fill": "blue"}},
            {"name": "hol", "apply_to": "day_box", "select": {"federal_holiday": True}, "style": {"fill": "gold"}},
        ]
        with self.assertLogs(style_trace.TRACE, level="DEBUG") as cm:
            StyleEngine(rules).evaluate_day(DayContext(date="20260601", workday=True))
        text = "\n".join(cm.output)
        self.assertIn("rule 'base'  APPLY  fill_color='red'", text)
        self.assertIn("fill_color='blue' (was 'red' from rule 'base')", text)
        self.assertIn("rule 'hol'  SKIP", text)
        self.assertIn("RESULT  fill_color='blue' [rule 'over']", text)

    def test_no_match_reports_defaults(self):
        rules = [{"name": "r", "apply_to": "event", "select": {"task_name": "zzz"}, "style": {"fill": "red"}}]
        ev = Event(task_name="Launch", start="20260601", end="20260601")
        with self.assertLogs(style_trace.TRACE, level="DEBUG") as cm:
            StyleEngine(rules).evaluate_event(ev)
        self.assertIn("SKIP", cm.output[0])
        self.assertIn("renderer/theme defaults apply", cm.output[-1])


if __name__ == "__main__":
    unittest.main()
