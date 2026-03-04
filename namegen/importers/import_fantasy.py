"""Import fantasy name generators from Snake4life JS files.

Extracts arrays and generation patterns via regex parsing.
"""

from __future__ import annotations

import json
import re
import glob
from pathlib import Path

from namegen.db import NameDB


def _extract_arrays(js_code: str) -> dict[str, list[str]]:
    """Extract all var nmX = [...] arrays from JS source."""
    arrays = {}
    pattern = re.compile(
        r'var\s+(nm\d+)\s*=\s*\[(.*?)\];',
        re.DOTALL,
    )
    for match in pattern.finditer(js_code):
        name = match.group(1)
        raw = match.group(2)
        values = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
        arrays[name] = values
    return arrays


def _classify_generator(js_code: str, arrays: dict[str, list[str]]) -> dict:
    """Classify a generator and extract its concatenation patterns.

    Handles intermediate variables like:
        nameLast = nm3[rnd2] + nm4[rnd3];
        names = nm1[rnd] + " " + nameLast;
    by resolving variable references.
    """
    has_type = 'type ===' in js_code or 'type ==' in js_code

    # Step 1: Find all intermediate variable assignments that reference nm arrays
    # e.g. nameLast = nm3[rnd2] + nm4[rnd3];
    #      nameFirst = nm1[rnd];
    var_defs: dict[str, list[str]] = {}
    var_pattern = re.compile(
        r'(\w+)\s*=\s*((?:nm\d+\[\w+\]\s*\+?\s*)+);',
    )
    for m in var_pattern.finditer(js_code):
        var_name = m.group(1)
        expr = m.group(2)
        if var_name in ("names", "i", "rnd", "rnd2", "rnd3", "rnd4", "rnd5", "rnd6"):
            continue
        used = re.findall(r'(nm\d+)\[', expr)
        if used:
            var_defs[var_name] = used

    # Step 2: Parse `names = ...` assignments, resolving variable references
    assign_pattern = re.compile(r'names\s*=\s*(.+?);', re.DOTALL)
    variants = []

    for m in assign_pattern.finditer(js_code):
        expr = m.group(1).strip()
        has_space = '" "' in expr or "' '" in expr

        # Parse the expression in order to find nm refs and variables,
        # tracking where the space literal appears
        tokens = re.findall(r'nm\d+\[\w+\]|"[^"]*"|\b[a-zA-Z_]\w*\b', expr)

        resolved_nms = []
        space_pos = -1

        for token in tokens:
            if token == '" "' or token == "' '":
                if has_space and space_pos < 0:
                    space_pos = len(resolved_nms)
            elif token.startswith("nm") and "[" in token:
                arr_name = token.split("[")[0]
                resolved_nms.append(arr_name)
            elif token in var_defs:
                resolved_nms.extend(var_defs[token])

        if resolved_nms:
            variants.append({
                "concat": resolved_nms,
                "space": has_space,
                "space_pos": space_pos if has_space else -1,
            })

    # Deduplicate variants
    seen = set()
    unique_variants = []
    for v in variants:
        key = (tuple(v["concat"]), v["space"], v["space_pos"])
        if key not in seen:
            seen.add(key)
            unique_variants.append(v)

    # Classify pattern type
    num_arrays = len(arrays)
    avg_item_len = 0
    if arrays:
        all_items = [item for arr in arrays.values() for item in arr]
        if all_items:
            avg_item_len = sum(len(x) for x in all_items) / len(all_items)

    is_name_list = avg_item_len > 4 and num_arrays <= 4

    if is_name_list and num_arrays <= 2 and not has_type:
        pattern_type = "flat_pick"
    elif has_type:
        pattern_type = "type_split"
    else:
        pattern_type = "phonetic_concat"

    return {
        "type": pattern_type,
        "variants": unique_variants,
        "num_arrays": num_arrays,
        "has_type_param": has_type,
    }


def import_fantasy(db: NameDB, data_dir: Path):
    """Import fantasy name generators from Snake4life JS files."""
    gen_dir = data_dir / "Snake4life__fantasy-names" / "generators"
    if not gen_dir.exists():
        print(f"[fantasy] SKIP: {gen_dir} not found")
        return

    print(f"[fantasy] Scanning {gen_dir}...")

    # Clear existing fantasy data
    db.conn.execute("DELETE FROM fantasy_arrays")
    db.conn.execute("DELETE FROM fantasy_meta")

    js_files = sorted(glob.glob(str(gen_dir / "**" / "*.js"), recursive=True))
    js_files = [f for f in js_files if ".min." not in f]

    imported = 0
    skipped = 0

    for filepath in js_files:
        filepath = Path(filepath)
        rel = filepath.relative_to(gen_dir)
        category = rel.parent.name
        name = rel.stem
        style_key = f"{category}.{name}"

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                js_code = f.read()
        except Exception as e:
            print(f"  WARN: Could not read {rel}: {e}")
            skipped += 1
            continue

        arrays = _extract_arrays(js_code)
        if not arrays:
            skipped += 1
            continue

        pattern = _classify_generator(js_code, arrays)

        for arr_name, values in arrays.items():
            db.conn.execute(
                "INSERT INTO fantasy_arrays (style_key, array_name, values_json) VALUES (?, ?, ?)",
                (style_key, arr_name, json.dumps(values, ensure_ascii=False)),
            )

        db.conn.execute(
            "INSERT INTO fantasy_meta (style_key, pattern, category, label) VALUES (?, ?, ?, ?)",
            (
                style_key,
                json.dumps(pattern, ensure_ascii=False),
                category,
                f"{category}/{name}",
            ),
        )

        imported += 1

    db.conn.commit()
    print(f"[fantasy] Imported {imported} generators ({skipped} skipped)")
