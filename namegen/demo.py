"""Offline, hand-authored demo database, kept separate from the world dataset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from namegen.db import NameDB


def build_demo(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return path
    fixture = json.loads((Path(__file__).parent / "data/demo.json").read_text(encoding="utf-8"))
    db = NameDB(path)
    db.init_schema()
    for country, content in fixture["countries"].items():
        rows = []
        for gender in ("M", "F"):
            rows.extend((name, "forename", country, gender, rank, "demo")
                        for rank, name in enumerate(content[gender], 1))
        rows.extend((name, "surname", country, None, rank, "demo")
                    for rank, name in enumerate(content["surnames"], 1))
        db.conn.executemany("INSERT INTO names VALUES (?,?,?,?,?,?)", rows)
        for name in content["places"]:
            db.conn.execute("INSERT INTO places(name,country_iso,feature_class,feature_code) VALUES (?,?,'P','PPL')", (name, country))
    key = "fantasy.elfs"
    pattern = {"has_type_param": True, "variants": [{"concat": ["nm1", "nm2", "nm3", "nm4"], "space": True, "space_pos": 2}]}
    db.conn.execute("INSERT INTO fantasy_meta VALUES (?,?,?,?)", (key, json.dumps(pattern), "fantasy", "Elfs"))
    db.conn.executemany("INSERT INTO fantasy_arrays VALUES (?,?,?)", [(key, k, json.dumps(v)) for k, v in fixture["fantasy"].items()])
    db.conn.executemany("INSERT INTO curated_lists VALUES (?,?)", [("demons", n) for n in ["Biscornu", "Chafouin", "Grignote", "Patatras", "Zigouigoui"]])
    db.conn.commit()
    db.close()
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="nomnom demo")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--database", type=Path, help="Use a full database instead of the bundled demo")
    parser.add_argument("--demo-database", type=Path, default=Path.home() / ".nomnom" / "demo-v1.db")
    args = parser.parse_args(argv)
    path = args.database.resolve() if args.database else build_demo(args.demo_database)
    if not path.is_file():
        parser.error(f"Database not found: {path}")
    from webapp.app import create_app
    app = create_app(path, demo=args.database is None)
    print(f"Nomnom: http://127.0.0.1:{args.port} ({'demo' if args.database is None else 'full database'})")
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=False)


if __name__ == "__main__":
    main()
