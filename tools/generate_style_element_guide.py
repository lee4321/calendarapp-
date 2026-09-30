#!/usr/bin/env python3
"""
Generate the visual guide to style-rule elements: docs/StyleElementGuide.html.

A ``style_rules`` rule styles a *token* (``text:event_name``, ``box:day`` ...).
Each drawn element carries an ``ec-*`` class, and ``config/element_catalog.yaml``
binds that class to a token.  This script renders every SVG view, reads the
``ec-*`` classes the view really emitted, joins them to the catalog and writes
one self-contained HTML page.  Clicking an element in the page highlights every
place it is drawn in that view, so the page is always in step with the code.

Usage::

    uv run python tools/generate_style_element_guide.py
    uv run python tools/generate_style_element_guide.py 20260601 20260831 --theme default
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.element_catalog import load_catalog  # noqa: E402

VIEWS: list[tuple[str, str]] = [
    ("weekly", "Weekly calendar"),
    ("mini", "Mini calendar"),
    ("mini-icon", "Mini calendar (icons)"),
    ("candybar", "Candybar"),
    ("timeline", "Timeline"),
    ("pit", "Points in time"),
    ("compactplan", "Compact plan"),
    ("blockplan", "Block plan"),
    ("gantt", "Gantt"),
]
_EXTRA_FLAGS: dict[str, list[str]] = {
    v: ["--header", "--footer", "--headerleft", "Header", "--footerleft", "Footer"]
    for v in ("weekly", "timeline", "pit", "compactplan", "blockplan", "gantt")
}
_EXTRA_FLAGS.update({v: ["--header", "--footer"] for v in ("mini", "mini-icon", "candybar")})
for _v in ("weekly", "timeline", "pit", "compactplan", "blockplan", "gantt"):
    _EXTRA_FLAGS[_v] += ["--includenotes"]

# Findings from a colour probe (every text token given its own colour, theme
# bindings removed), 2026-09-30.  They describe where a token's *colour* did
# not reach the element; font and size were not probed.
_FIXED = "Colour did not follow its token in a probe (fixed or derived colour)."
NOTES: dict[tuple[str, str], str] = {
    ("*", "ec-header-text"): _FIXED,
    ("*", "ec-footer-text"): _FIXED,
    ("weekly", "ec-label"): _FIXED,
    (
        "weekly",
        "ec-duration-date",
    ): "Probe coloured the one continuation date with text:event_notes, not text:duration_date.",
    ("mini", "ec-day-number"): "Holiday / today days take their colour from day rules (red in the probe).",
    ("candybar", "ec-day-number"): "Holiday / today days take their colour from day rules (red in the probe).",
    ("candybar", "ec-month-box-label"): _FIXED,
    ("candybar", "ec-label"): "One label (the week column heading) took text:week_number in the probe.",
    ("timeline", "ec-label"): "Axis date labels took text:event_date in the probe, not text:label.",
    ("timeline", "ec-duration-date"): _FIXED,
    ("timeline", "ec-event-date"): _FIXED,
    ("timeline", "ec-holiday-date"): _FIXED,
    ("pit", "ec-event-name"): "Callout text uses the PIT ink colour, not the token's colour.",
    ("pit", "ec-event-notes"): "Callout text uses the PIT ink colour, not the token's colour.",
    ("pit", "ec-event-date"): _FIXED,
    ("pit", "ec-label"): _FIXED,
    ("compactplan", "ec-event-name"): "Colour is chosen black / white / navy for contrast with the bar under it.",
    ("compactplan", "ec-duration-date"): "Colour is chosen black / white for contrast with the bar under it.",
    ("compactplan", "ec-label"): _FIXED,
}

# Where a view draws an element with a different token than the catalog binds,
# the token the probe observed (same probe as NOTES).
OBSERVED_TOKEN: dict[tuple[str, str], str] = {
    ("blockplan", "ec-label"): "text:band_label",
    ("gantt", "ec-tick-label"): "text:band_label",
    ("timeline", "ec-label"): "text:event_date",
}


def render(view: str, start: str, end: str, theme: str) -> str:
    """Render *view* with the CLI and return the SVG text (output is removed)."""
    stem = f"_styleguide_{view}"
    cmd = [
        "uv", "run", "python", "ecalendar.py", view, "--theme", theme,
        "--outputfile", f"{stem}.svg", "--no-details-md", "--no-icons", "--no-csv",
        *_EXTRA_FLAGS.get(view, []), start, end,
    ]  # fmt: skip
    subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
    out_dir = ROOT / "output" / stem
    svg = (out_dir / f"{stem}.svg").read_text()
    shutil.rmtree(out_dir, ignore_errors=True)
    svg = re.sub(r"<desc>.*?</desc>", "", svg, flags=re.S)
    svg = re.sub(r'^(<svg[^>]*?)\swidth="[^"]*"\s+height="[^"]*"', r"\1", svg, count=1, flags=re.S)
    return svg


def emitted_classes(svg: str) -> Counter:
    counts: Counter = Counter()
    for m in re.finditer(r'class="([^"]*)"', svg):
        for c in m.group(1).split():
            if c.startswith("ec-"):
                counts[c] += 1
    return counts


def theme_rebindings(theme: str) -> dict[str, str]:
    path = ROOT / "config" / "themes" / f"{theme}.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    return {
        k: v["use"] for k, v in (data.get("element_overrides") or {}).items() if isinstance(v, dict) and v.get("use")
    }


def build_data(start: str, end: str, theme: str) -> dict:
    catalog = load_catalog()
    rebound = theme_rebindings(theme)
    views = []
    for view, title in VIEWS:
        svg = render(view, start, end, theme)
        rows = []
        for cls, n in sorted(emitted_classes(svg).items()):
            entry = catalog.get(cls)
            if entry is None:
                continue  # modifier / structural class: not a styling target
            rows.append({
                "cls": cls,
                "kind": entry.kind,
                "token": OBSERVED_TOKEN.get((view, cls), f"{entry.kind}:{entry.token}"),
                "catalog": f"{entry.kind}:{entry.token}" if (view, cls) in OBSERVED_TOKEN else "",
                "desc": entry.description,
                "count": n,
                "rebound": rebound.get(cls, ""),
                "note": NOTES.get((view, cls)) or NOTES.get(("*", cls), ""),
            })  # fmt: skip
        views.append({"id": view, "title": title, "svg": svg, "rows": rows})
    return {"views": views, "theme": theme, "range": f"{start}–{end}"}


def matrix(views: list[dict]) -> str:
    """Text-token × view table listing which elements draw with each token."""
    tokens: dict[str, dict[str, list[str]]] = {}
    for v in views:
        for r in v["rows"]:
            if r["kind"] == "text":
                tokens.setdefault(r["token"], {}).setdefault(v["id"], []).append(r["cls"][3:])
    head = "".join(f"<th>{html.escape(v['title'])}</th>" for v in views)
    body = []
    for tok in sorted(tokens):
        cells = []
        for v in views:
            els = tokens[tok].get(v["id"])
            cells.append(
                "<td>" + "".join(f"<code>{html.escape(e)}</code>" for e in els) + "</td>"
                if els
                else "<td class=no>–</td>"
            )
        body.append(f"<tr><th scope=row><code>{html.escape(tok)}</code></th>{''.join(cells)}</tr>")
    return (
        f"<div class=mx><table><thead><tr><th>Token</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Style Rule Element Guide</title>
<style>
:root{--bg:#fff;--fg:#1d2733;--mut:#5d6b7a;--line:#d9e0e7;--card:#f5f7fa;--acc:#d6246e;
--text:#1f6feb;--box:#1a8f4c;--line-k:#c8680a;--icon:#8250df}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#14181d;--fg:#e4e9ee;--mut:#9aa7b4;--line:#2c3540;--card:#1c222a;--acc:#ff5c9d;
--text:#6ea8ff;--box:#4cc38a;--line-k:#f0a04b;--icon:#b392f0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
.w{max-width:1500px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:32px 0 8px}p{margin:6px 0;color:var(--mut);max-width:80ch}
code{font:12.5px ui-monospace,Menlo,monospace;background:var(--card);border:1px solid var(--line);border-radius:4px;padding:0 4px;margin:1px 2px 1px 0;display:inline-block}
.flow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:14px 0}.flow span.b{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px}.flow i{color:var(--mut);font-style:normal}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;font-size:12.5px}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0}.tabs button{font:inherit;padding:6px 12px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:18px;cursor:pointer}
.tabs button[aria-selected=true]{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.cols{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(320px,1fr);gap:20px;align-items:start}
@media(max-width:1000px){.cols{grid-template-columns:1fr}}
.pane{border:1px solid var(--line);border-radius:10px;background:#fff;overflow:auto;max-height:78vh;position:sticky;top:8px}
.pane svg{display:block;width:100%;height:auto}
.leg{border:1px solid var(--line);border-radius:10px;background:var(--card);max-height:78vh;overflow:auto}
.leg h3{margin:0;padding:8px 12px;font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--card)}
.row{display:block;width:100%;text-align:left;font:inherit;color:inherit;background:none;border:0;border-bottom:1px solid var(--line);padding:8px 12px 8px 10px;cursor:pointer;border-left:4px solid var(--k)}
.row:hover,.row[aria-pressed=true]{background:color-mix(in srgb,var(--k) 12%,transparent)}
.row .n{font-weight:600}.row .t{font:12.5px ui-monospace,Menlo,monospace;color:var(--k)}.row .d{color:var(--mut);font-size:13px}
.row .c{float:right;color:var(--mut);font-size:12px}.row .w2{display:block;margin-top:3px;font-size:12.5px;color:var(--fg)}
.k-text{--k:var(--text)}.k-box{--k:var(--box)}.k-line{--k:var(--line-k)}.k-icon{--k:var(--icon)}
.tog{margin:0 0 8px;color:var(--mut);font-size:13px}
.mx{overflow:auto;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;font-size:13px;width:100%}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}thead th{background:var(--card);position:sticky;top:0}td.no{color:var(--mut)}
.hint{color:var(--mut);font-size:13px}
</style></head><body><div class="w">
<h1>Style Rule Element Guide</h1>
<p>Which drawn element a style rule reaches, in which visualization. Generated from the real SVG output of the <code>__THEME__</code> theme (__RANGE__) and <code>config/element_catalog.yaml</code>.</p>

<h2>How a style rule reaches an element</h2>
<div class="flow"><span class="b">Element drawn in a view<br><code>ec-event-name</code></span><i>→ catalog →</i><span class="b">Token<br><code>text:event_name</code></span><i>← <code>apply_to</code> ←</i><span class="b">Your style rule</span></div>
<pre>style_rules:
  - name: bigger event names
    apply_to: text:event_name      # the token, not the ec- class
    style: {size: 11, color: navy}</pre>
<p>A rule names a <b>token</b>; every element bound to that token in every view changes together. To restyle a single element without touching the others, rebind it with <code>element_overrides: {ec-foo: {use: text:other}}</code>. A theme may already rebind some elements — those rows are marked below.</p>

<h2>Text tokens across visualizations</h2>
<p>Each cell lists the elements (<code>ec-</code> prefix dropped) that draw with that token in that view. Empty means the view never uses it.</p>
__MATRIX__

<h2>See it in each view</h2>
<p class="hint">Pick a view, then click (or hover) an element in the list to highlight every place it is drawn. Colour of the left bar: <b style="color:var(--text)">text</b>, <b style="color:var(--box)">box</b>, <b style="color:var(--line-k)">line</b>, <b style="color:var(--icon)">icon</b>.</p>
<div class="tabs" role="tablist" id="tabs"></div>
<div class="cols"><div class="pane" id="pane"></div><div class="leg" id="leg"></div></div>

<h2>Not covered here</h2>
<p><code>text-mini</code> is plain text and <code>excelblockplan</code> writes an Excel workbook; neither draws SVG elements. <code>excelblockplan</code> reads <code>text:heading</code> and <code>text:band_label</code> for its header rows.</p>
<p>Not visible in the sample pages above: <code>text:swimlane_label</code> (block plan lane headings, drawn when swimlanes are configured), <code>text:today_label</code> (today marker label, timeline / block plan / compact plan / gantt when a today line is on) and <code>text:fiscal_label</code> (fiscal period labels when <code>--fiscal</code> is on).</p>
</div>
<script>
const DATA=__DATA__;
const tabs=document.getElementById('tabs'),pane=document.getElementById('pane'),leg=document.getElementById('leg');
let cur=null,pinned=null;
function show(i){cur=DATA.views[i];pinned=null;
 [...tabs.children].forEach((b,j)=>b.setAttribute('aria-selected',j===i));
 pane.innerHTML=cur.svg;
 leg.innerHTML='';
 for(const kind of ['text','box','line','icon']){
  const rows=cur.rows.filter(r=>r.kind===kind);if(!rows.length)continue;
  const h=document.createElement('h3');h.textContent=kind+' elements ('+rows.length+')';leg.append(h);
  for(const r of rows){
   const b=document.createElement('button');b.className='row k-'+kind;b.setAttribute('aria-pressed','false');
   let extra='';
   if(r.rebound)extra+='<span class=w2>Theme rebinds this to <code>'+r.rebound+'</code>.</span>';
   if(r.catalog)extra+='<span class=w2>Catalog binds this to <code>'+r.catalog+'</code>, but this view draws it with <code>'+r.token+'</code>.</span>';
   if(r.note)extra+='<span class=w2>Observed: '+r.note+'</span>';
   b.innerHTML='<span class=c>×'+r.count+'</span><span class=n>'+r.cls+'</span><br><span class=t>'+r.token+'</span><br><span class=d>'+r.desc+'</span>'+extra;
   b.onmouseenter=()=>hl(r.cls);b.onmouseleave=()=>hl(pinned);
   b.onclick=()=>{pinned=pinned===r.cls?null:r.cls;[...leg.querySelectorAll('.row')].forEach(x=>x.setAttribute('aria-pressed','false'));if(pinned)b.setAttribute('aria-pressed','true');hl(pinned)};
   leg.append(b);}}
}
function hl(cls){
 const svg=pane.querySelector('svg');if(!svg)return;
 svg.querySelector('#ov')?.remove();if(!cls)return;
 const NS='http://www.w3.org/2000/svg',vb=svg.viewBox.baseVal;
 const ov=document.createElementNS(NS,'g');ov.id='ov';ov.style.pointerEvents='none';
 const veil=document.createElementNS(NS,'rect');
 for(const [k,v] of Object.entries({x:vb.x,y:vb.y,width:vb.width,height:vb.height,fill:'#fff','fill-opacity':.78}))veil.setAttribute(k,v);
 ov.append(veil);
 const inv=svg.getScreenCTM().inverse();
 svg.querySelectorAll('.'+CSS.escape(cls)).forEach(el=>{
  if(!el.getBBox)return;
  let bb;try{bb=el.getBBox()}catch(e){return}
  const g=document.createElementNS(NS,'g'),m=inv.multiply(el.getScreenCTM());
  g.setAttribute('transform','matrix('+[m.a,m.b,m.c,m.d,m.e,m.f].join(' ')+')');
  const c=el.cloneNode(true);c.removeAttribute('transform');g.append(c);
  const r=document.createElementNS(NS,'rect'),p=1.5;
  for(const [k,v] of Object.entries({x:bb.x-p,y:bb.y-p,width:bb.width+2*p,height:bb.height+2*p,fill:'#d6246e','fill-opacity':.14,stroke:'#d6246e','stroke-width':1,'vector-effect':'non-scaling-stroke'}))r.setAttribute(k,v);
  g.append(r);ov.append(g);});
 svg.append(ov);
}
DATA.views.forEach((v,i)=>{const b=document.createElement('button');b.textContent=v.title;b.role='tab';b.onclick=()=>show(i);tabs.append(b)});
show(0);
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("start", nargs="?", default="20260601")
    ap.add_argument("end", nargs="?", default="20260831")
    ap.add_argument("--theme", default="default")
    ap.add_argument("--out", default=str(ROOT / "docs" / "StyleElementGuide.html"))
    args = ap.parse_args()

    data = build_data(args.start, args.end, args.theme)
    page = (
        PAGE.replace("__THEME__", html.escape(data["theme"]))
        .replace("__RANGE__", html.escape(data["range"]))
        .replace("__MATRIX__", matrix(data["views"]))
        .replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    )
    Path(args.out).write_text(page)
    print(f"wrote {args.out} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    main()
