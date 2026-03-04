#!/usr/bin/env python3
"""Flask webapp for the RPG Name Generator."""

from __future__ import annotations

import io
import sys

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add project root to path so we can import namegen
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request, render_template

from namegen.api import generate, list_styles, list_catalog

app = Flask(__name__)

# Cached style catalog — built once on first request
_style_catalog: list[dict] | None = None


def _build_catalog() -> list[dict]:
    """Build grouped style catalog from list_styles()."""
    raw = list_styles()
    groups: list[dict] = []

    for category, names in sorted(raw.items()):
        if category.startswith("fantasy/"):
            cat_prefix = category.split("/", 1)[1]
            display_names = [f"{cat_prefix}.{n}" for n in names]
            label = f"Fantasy — {cat_prefix.replace('_', ' ').title()}"
        elif category == "curated":
            display_names = list(names)
            label = "Curated"
        elif category == "onomastic":
            display_names = list(names)
            label = "Onomastic (Real-World)"
        else:
            display_names = list(names)
            label = category.replace("_", " ").title()

        groups.append({"label": label, "styles": sorted(display_names)})

    return groups


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/styles")
def api_styles():
    global _style_catalog
    if _style_catalog is None:
        _style_catalog = _build_catalog()
    return jsonify(_style_catalog)


@app.route("/api/catalog")
def api_catalog():
    return jsonify(list_catalog())


@app.route("/api/generate", methods=["POST"])
def api_generate():
    body = request.get_json(force=True)
    requests_list = body.get("requests", [])
    results = []

    for req in requests_list:
        style = req.get("style", "")
        name_type = req.get("type", "forename")
        count = min(int(req.get("count", 1)), 100)
        gender = req.get("gender") or None
        romanize = bool(req.get("romanize", False))

        try:
            if name_type == "fullname":
                forenames = generate(style, "forename", count, gender, romanize=romanize)
                try:
                    surnames = generate(style, "surname", count, None, romanize=romanize)
                except Exception:
                    surnames = []
                if surnames:
                    names = [f"{f} {s}" for f, s in zip(forenames, surnames)]
                else:
                    names = forenames
            else:
                names = generate(style, name_type, count, gender, romanize=romanize)
            results.append({
                "style": style,
                "type": name_type,
                "count": count,
                "gender": gender,
                "romanize": romanize,
                "names": names,
            })
        except (ValueError, Exception) as e:
            results.append({
                "style": style,
                "type": name_type,
                "count": count,
                "gender": gender,
                "error": str(e),
            })

    return jsonify({"results": results})


if __name__ == "__main__":
    print("Loading style catalog...")
    _style_catalog = _build_catalog()
    total = sum(len(g["styles"]) for g in _style_catalog)
    print(f"Loaded {total} styles in {len(_style_catalog)} groups.")
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=False)
