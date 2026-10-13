"""tools/icon_pattern_gallery.py must stay standalone and in step with renderers.svg_patterns."""

import ast
import importlib.util
import inspect
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from renderers import svg_patterns

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "icon_pattern_gallery.py"

SHARED = (
    "parse_svg_tile_size",
    "normalize_tile_scale",
    "extract_pattern_inner",
    "scope_pattern_ids",
    "colorize_pattern_svg",
    "pattern_is_recolorable",
    "pattern_def_id",
    "root_paint_attrs",
    "pattern_def_xml",
)

ICON = (
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<path d="M3 3h18v18H3z"/></svg>'
)


@pytest.fixture(scope="module")
def gallery():
    spec = importlib.util.spec_from_file_location("icon_pattern_gallery", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass looks the module up by name
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_only_standard_library_imports():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= set(sys.stdlib_module_names), roots - set(sys.stdlib_module_names)


@pytest.mark.parametrize("name", SHARED)
def test_embedded_helper_matches_the_package(gallery, name):
    assert inspect.getsource(getattr(gallery, name)) == inspect.getsource(getattr(svg_patterns, name))


def test_default_target_size_matches_the_package(gallery):
    assert gallery.DEFAULT_PATTERN_TARGET_SIZE == svg_patterns.DEFAULT_PATTERN_TARGET_SIZE


def test_script_runs_alone_on_a_folder_of_svgs(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    shutil.copy(SCRIPT, work / "gallery.py")  # only the script: nothing else of the codebase
    svgs = tmp_path / "my svgs"
    svgs.mkdir()
    (svgs / "box.svg").write_text(ICON, encoding="utf-8")
    (svgs / "dot.svg").write_text(ICON.replace("M3 3h18v18H3z", "M12 12h.01"), encoding="utf-8")
    (svgs / "notes.txt").write_text("ignored", encoding="utf-8")
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "-I", str(work / "gallery.py"), str(out), "--svg-dir", str(svgs), "--svg-style", "icon"],
        cwd=work,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    page = out / "folder-my_svgs" / "page_001.svg"
    text = page.read_text(encoding="utf-8")
    assert "box" in text and "dot" in text and "notes" not in text
    assert (out / "index.html").read_text(encoding="utf-8").count("page_001.svg") == 1
    assert not (out / "icons").exists()  # folders only when --svg-dir is given


def test_missing_database_is_an_error_not_a_new_file(tmp_path):
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(tmp_path / "out"), "--db", str(tmp_path / "nope.db")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "database not found" in result.stderr
    assert not (tmp_path / "nope.db").exists()
