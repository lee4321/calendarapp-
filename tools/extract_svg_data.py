#!/usr/bin/env python3
"""Extract embedded CSV event data from an EventCalendar SVG file.

This script is standalone — it depends only on the Python standard library
and does NOT require the ecalendar package or any of its dependencies.

Usage:
    python extract_svg_data.py calendar.svg              # print CSV to stdout
    python extract_svg_data.py calendar.svg -o data.csv   # write to file
"""

from __future__ import annotations

import argparse
import base64
import sys
import xml.etree.ElementTree as ET
import zlib

ECAL_NS = "https://eventcalendar.local/svg-data"


def extract_csv(svg_path: str) -> str:
    """Parse *svg_path* and return the embedded CSV string.

    Raises ``SystemExit`` with a descriptive message when the SVG does not
    contain embedded event data.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    # Search for <ecal:data> anywhere in the document
    data_elem = root.find(f".//{{{ECAL_NS}}}data")
    if data_elem is None:
        # Also try inside <metadata> with namespace prefix
        for elem in root.iter():
            if elem.tag.endswith("}data") and ECAL_NS in elem.tag:
                data_elem = elem
                break

    if data_elem is None:
        print(
            "Error: No embedded event data found in this SVG.\n"
            "Was it generated with --embed-data?",
            file=sys.stderr,
        )
        raise SystemExit(1)

    encoding = data_elem.get("encoding", "")
    if encoding != "deflate+base64":
        print(
            f"Error: Unsupported encoding '{encoding}'. "
            "Expected 'deflate+base64'.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    payload = (data_elem.text or "").strip()
    if not payload:
        print("Error: Embedded data element is empty.", file=sys.stderr)
        raise SystemExit(1)

    csv_bytes = zlib.decompress(base64.b64decode(payload))
    return csv_bytes.decode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract embedded CSV data from an EventCalendar SVG file."
    )
    parser.add_argument("svg", help="Path to the SVG file")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="Write CSV to FILE instead of stdout",
    )
    args = parser.parse_args()

    csv_text = extract_csv(args.svg)

    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as fh:
            fh.write(csv_text)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(csv_text)


if __name__ == "__main__":
    main()
