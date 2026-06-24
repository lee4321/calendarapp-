"""Begin/end date inputs with quick presets (this year, quarter, FY, +90d)."""

from __future__ import annotations

from datetime import date, timedelta

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static


def _yyyymmdd(d: date) -> str:
    return d.strftime("%Y%m%d")


class DateRange(Vertical):
    """Two YYYYMMDD inputs plus preset buttons that fill them in."""

    def __init__(self, begin: str = "", end: str = "") -> None:
        super().__init__(classes="daterange")
        self._begin = begin
        self._end = end

    def compose(self) -> ComposeResult:
        with Horizontal(classes="daterow"):
            with Vertical(classes="argfield"):
                yield Label("begin (START_DATE)", classes="arglabel")
                yield Input(value=self._begin, placeholder="YYYYMMDD",
                            id="date-begin", classes="narrow")
            with Vertical(classes="argfield"):
                yield Label("end (END_DATE)", classes="arglabel")
                yield Input(value=self._end, placeholder="YYYYMMDD",
                            id="date-end", classes="narrow")
        with Horizontal(classes="presets"):
            yield Button("This year", id="preset-year", classes="preset")
            yield Button("This quarter", id="preset-quarter", classes="preset")
            yield Button("Next 90 days", id="preset-90", classes="preset")
            yield Button("This month", id="preset-month", classes="preset")
        yield Static("Dates are adjusted to whole weeks by the engine.",
                     classes="arghelp")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        today = date.today()
        if event.button.id == "preset-year":
            b, e = date(today.year, 1, 1), date(today.year, 12, 31)
        elif event.button.id == "preset-quarter":
            q = (today.month - 1) // 3
            b = date(today.year, q * 3 + 1, 1)
            end_month = q * 3 + 3
            e = (date(today.year, end_month + 1, 1) - timedelta(days=1)
                 if end_month < 12 else date(today.year, 12, 31))
        elif event.button.id == "preset-90":
            b, e = today, today + timedelta(days=90)
        elif event.button.id == "preset-month":
            b = date(today.year, today.month, 1)
            nxt = (date(today.year + 1, 1, 1) if today.month == 12
                   else date(today.year, today.month + 1, 1))
            e = nxt - timedelta(days=1)
        else:
            return
        self.query_one("#date-begin", Input).value = _yyyymmdd(b)
        self.query_one("#date-end", Input).value = _yyyymmdd(e)
        event.stop()

    @property
    def begin(self) -> str:
        return self.query_one("#date-begin", Input).value.strip()

    @property
    def end(self) -> str:
        return self.query_one("#date-end", Input).value.strip()
