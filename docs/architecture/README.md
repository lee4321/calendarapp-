# Architecture documentation

Reading order for a developer new to EventCalendar:

1. **[overview.md](overview.md)** — the system in one diagram: CLI → config →
   theme → DB → visualizer → SVG/XLSX.
2. **[render-pipeline.md](render-pipeline.md)** — one `weekly` run end to end;
   the sequence every other visualizer maps onto.
3. **[theme-resolution.md](theme-resolution.md)** — how a YAML theme becomes
   styles at draw time: tokens, rules, elements, and the precedence chain.
4. **[data-model.md](data-model.md)** — calendar.db tables, the `Event`
   dataclass, and who consumes what.
5. **[visualizers.md](visualizers.md)** — one section per visualizer: layout
   strategy, renderer shape, quirks.
6. **[importers.md](importers.md)** — the CSV/XLSX import framework.
7. **[../../ARCHITECTURE_ecalendar.md](../../ARCHITECTURE_ecalendar.md)** —
   detailed CLI-layer reference (call graph, atfile grammar, subcommand
   dispatch). Written before the `cli/` split; its section-to-module map is
   at the top of the file.

Vocabulary (token / ctx / rule / element / nwd / weekend styles /
CoordinateDict / atfile) lives in [CONTRIBUTING.md](../../CONTRIBUTING.md),
along with the layering rules and the verification workflow
(`tools/refcorpus.sh`, test suite).
