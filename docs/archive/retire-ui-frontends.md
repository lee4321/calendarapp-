# Retire the Textual TUI and the Slint UI

**Status:** proposed (2026-09-18)
**Goal:** remove both alternative front-ends from the working tree, the
dependency set and the virtualenv, while leaving behind everything needed to
rebuild either one later.

Neither front-end reimplements any rendering logic: both introspect
`_create_argument_parser()`, assemble an argv and shell out to
`ecalendar.py`. Nothing in the render pipeline depends on them, so this is a
pure subtraction — `tools/refcorpus.sh check` must stay byte-identical.

---

## 1. Inventory

| Package | Tracked files | Lines | Entry point |
|---|---|---|---|
| `tui/` | 17 | 1,422 | `uv run python -m tui` |
| `slint_ui/` | 7 | 2,163 | `uv run python slint_ui/ecalendar_app.py` (+ `import_app.py` POC) |

**Dependencies to drop** (`pyproject.toml` → `[project.dependencies]`):
`textual>=8.2.7`, `slint>=1.17.0b2`.

**Packages that leave the venv** once the lock is regenerated — `textual` and
`slint` plus their exclusive transitives:

```
slint  textual  rich  markdown-it-py  mdurl  mdit-py-plugins
linkify-it-py  uc-micro-py  platformdirs  typing-extensions
```

`pygments` **stays** — `pytest` depends on it. Site-packages goes 72 → 52.
(`mdurl` and `typing-extensions` were not in the first reading of the lock;
`uv lock` found them. 10 packages in total.)

**References in the rest of the tree** (everything that must be touched):

| File | Line(s) | What it says |
|---|---|---|
| `pyproject.toml` | 16–17 | the two dependency pins |
| `uv.lock` | 33–34, 55–56, + package blocks | resolved graph |
| `docs/USER_GUIDE.md` | 11–57 | the whole "## Textual UI" section |
| `tools/check_user_guide.py` | 7, 43 | docstring + comment naming the TUI as a skipped example |
| `docs/architecture/importers.md` | 39 | "The TUI (`tui/importers_spec.py`) drives the same CLIs…" |
| `cli/args.py` | 196–198 | docstring: parser registration order is walked by "the Slint UI, the TUI and tools/generate_option_catalog.py" |
| `deploy_copy.sh` | 13, 38–47 | `slint_ui` in the copy loop, `--include='*.slint'`, and the "Deliberately excluded: … tui/ …" comment |
| `docs/changelog.md` | top | needs a new entry |

**Deliberately left alone** — dated records of what was true when written:
`docs/archive/MarkdownDetailsPlan.md`, `docs/archive/CONSOLIDATION_PLAN.md`,
`docs/archive/textualUI.html`, `.claude/plans/uv-check-cleanup.md`.

No tests reference either package; ruff and `uv check` currently lint both, so
the checked surface shrinks too.

---

## 2. How the front-ends stay recreatable

Three options were considered:

1. **Delete + tag + written restoration record** ← *recommended*
2. Keep the code in-tree but unwired (dependencies still needed → fails the
   "remove from the venv" requirement)
3. Move to a sibling repository (real maintenance cost for code nobody is
   using)

Option 1 matches the convention this repo already uses for large subtractions
(`pre-consolidation` / `consolidation-complete` tags, `docs/archive/`).

### 2a. Tag the last commit that still has them

Before deleting anything, from a clean tree:

```bash
git tag -a pre-ui-retirement -m "Last commit carrying tui/ and slint_ui/" && git push origin pre-ui-retirement
```

Restoring later is then one command per package:

```bash
git checkout pre-ui-retirement -- tui slint_ui
```

### 2b. Write `docs/archive/UI_FRONTENDS.md`

The tag preserves the code; this file preserves the *context* a future rebuild
needs — what the packages did, and every contract they leaned on that has
since been free to drift. It must contain:

- **What they were.** The two entry points, the screens/windows each offered,
  and the one-sentence architecture (thin shell over argparse → argv → `uv run
  ecalendar.py …`; no rendering logic duplicated).
- **The restore command** and the tag name from §2a.
- **The coupling contracts**, each with the file it lived in, because these are
  the things that will have moved by the time anyone rebuilds:
  - `_create_argument_parser(default_output)` — defined in `cli/args.py:348`,
    re-exported from `ecalendar.py`. Both UIs walked its subparsers to learn
    each subcommand's long-option and positional set. Registration order is the
    contract (`cli/args.py:190`); `_SortedSubcommandsHelpFormatter` sorts only
    the printed help.
  - `import ecalendar` is side-effect free (execution guarded by
    `if __name__ == "__main__"`), which is what makes the introspection safe.
  - Picker sources (`tui/registry.py`): `ThemeEngine.list_available_themes()`,
    `config.config.FONT_REGISTRY`, and `shared.db_access.CalendarDB` for paper
    sizes, patterns, icons, colors and palettes.
  - Importer adapters (`tui/importers_spec.py`) shelled out to
    `importers/import_events.py`, `import_specialdays.py` and the content
    importers — the flag surfaces `docs/architecture/importers.md` describes.
  - Output-path assumption: the Slint preview resolved
    `output/<stem>/<stem>.svg`. This already changed once (the run-folder
    commit `d02e6b92`); a rebuild must re-derive it, not trust the old code.
- **Why they were retired**, so the decision is not re-litigated blind.
- **What a rebuild would cost today**: the parser walk is still the cheapest
  path, and `tools/generate_option_catalog.py` is a live, tested example of
  walking the same parser — the best starting reference.

Add one line to `docs/architecture/README.md`'s reading order? **No** — it is a
new-developer path, and the archive note is not part of it. A pointer belongs
in the changelog entry instead.

---

## 3. Execution order

Each step is verifiable on its own; commit as one change.

1. **Tag** (§2a) from a clean tree, before touching files.
2. **Write** `docs/archive/UI_FRONTENDS.md` (§2b) — authored *from* the code
   while it is still present.
3. **Delete** `git rm -r tui slint_ui`, then remove the leftover untracked
   `tui/.DS_Store`, `slint_ui/.DS_Store` and `__pycache__/` directories.
4. **Documentation:**
   - `docs/USER_GUIDE.md` — drop the "## Textual UI (interactive terminal app)"
     section whole (heading through the `tui/README.md` link). The guide has no
     TOC, so no anchor to repair; `## Commands` becomes the first section.
   - `tools/check_user_guide.py` — reword the docstring and the line-43 comment
     so they describe the skip rule ("importer examples and shell prose") without
     naming the TUI. The logic does not change.
   - `docs/architecture/importers.md` — delete the TUI sentence at line 39.
   - `cli/args.py` — the `_SortedSubcommandsHelpFormatter` docstring now names
     only `tools/generate_option_catalog.py` as the consumer of registration
     order. (Docstring only; the option catalog is unaffected.)
   - `docs/changelog.md` — new top entry naming both packages, the two dropped
     dependencies, the tag, and `docs/archive/UI_FRONTENDS.md`.
5. **`deploy_copy.sh`** — drop `slint_ui` from the `for pkg in …` loop, drop the
   `--include='*.slint'` line, and rewrite the two comments (the header's
   "Deliberately excluded" list, and the `slint_ui (the GUI) also needs its
   *.slint markup` paragraph above the loop).
6. **Dependencies:**
   ```bash
   # remove the two lines from [project.dependencies] in pyproject.toml first
   uv lock
   uv sync
   ```
   `uv sync` makes the environment match the lock exactly, so it removes the
   eight packages listed in §1 — no manual `uv pip uninstall` needed. Both
   `pyproject.toml` and `uv.lock` must be committed together: the pre-commit
   hook runs `uv check --locked` and fails on a stale lock.

   *Watch:* `[tool.uv] no-binary-package = ["pillow"]` means any reinstall of
   Pillow builds from source against libraqm. `uv sync` should not touch
   Pillow here, but step 7's `test_text_layout_engine.py` is the guard that
   proves it.

---

## 4. Verification

```bash
uv check --locked
uv run ruff check . && uv run ruff format --check .
uv run python -m pytest tests/ -q
uv run python tools/generate_option_catalog.py --check
uv run python tools/check_user_guide.py
tools/refcorpus.sh check          # must be byte-identical — no renderer touched
```

Then confirm the removal is complete and the deploy script still works:

```bash
grep -rin "slint\|textual" --include="*.py" --include="*.toml" --include="*.sh" --include="*.md" . | grep -v "^./.venv\|^./docs/archive\|^./docs/MarkdownDetailsPlan.md\|^./.claude/plans"
```

```bash
./deploy_copy.sh /tmp/ec-deploy-check && cd /tmp/ec-deploy-check && uv run python ecalendar.py --help
```

Expected end state: site-packages at ~64 entries with none of the eight
removed names, `python -c "import textual"` failing inside the venv, and the
`pre-ui-retirement` tag on the remote.

---

## 5. Out of scope (flagged, not folded in)

- `pyproject.toml` sets `readme = "README.md"`, but no `README.md` exists at
  the repo root. Pre-existing and unrelated to this change; worth its own fix.
