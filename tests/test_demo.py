"""A clean clone works without any world dataset or source checkout."""
import json

import pytest

from namegen.api import configure_database, generate, generate_bulk
from namegen.demo import build_demo
from webapp.app import create_app


@pytest.fixture
def demo(tmp_path):
    path = build_demo(tmp_path / "demo.db")
    configure_database(path)
    yield path
    import namegen.api as api
    api._db.close()
    api._db = api._registry = api._catalog = None


def test_demo_build_is_separate_and_idempotent(demo):
    import sqlite3
    with sqlite3.connect(demo) as db:
        before = db.execute("SELECT COUNT(*) FROM names").fetchone()[0]
    assert build_demo(demo) == demo
    with sqlite3.connect(demo) as db:
        assert db.execute("SELECT COUNT(*) FROM names").fetchone()[0] == before
    assert before > 50


@pytest.mark.parametrize("style,kind", [
    ("FR", "fullname"), ("french", "surname"), ("GB", "place"),
    ("JP", "forename"), ("elf", "fullname"), ("demons", "forename"),
])
def test_demo_styles(demo, style, kind):
    names = generate(style, kind, 3)
    assert len(names) == 3
    assert all(isinstance(name, str) and name.strip() for name in names)


def test_place_allowed_for_culture_also_in_names_catalogue(demo):
    assert len(generate("french", "place", 3)) == 3


def test_bulk_and_transliteration(demo):
    names = list(generate_bulk("FR", "surname", 1000))
    assert len(names) == 1000
    unique = list(generate_bulk("FR", "surname", 1000, unique=True))
    assert len(unique) == len(set(unique)) == 12
    assert all(name.isascii() for name in generate("JP", "forename", 3, romanize=True))


def test_web_catalogue_and_generation(demo):
    app = create_app(demo, demo=True)
    client = app.test_client()
    assert b"Nomnom" in client.get("/").data
    catalog = client.get("/api/catalog").get_json()
    assert {d["id"] for d in catalog["domains"]} == {"names", "places"}
    for domain in catalog["domains"]:
        for group in domain["groups"]:
            for entry in group["entries"]:
                if entry["id"].startswith(("style.", "macro.", "overlay.", "script.")) or entry["id"] == "demons":
                    assert entry["count"] > 0
    response = client.post("/api/generate", json={"requests": [
        {"style": "FR", "type": "fullname", "count": 5},
        {"style": "FR", "type": "place", "count": 5},
    ]})
    assert response.status_code == 200
    assert all(r["returned_count"] == len(r["names"]) == 5 for r in response.json["results"])


@pytest.mark.parametrize("payload", [
    None, [], {}, {"requests": {}}, {"requests": []}, {"requests": [None]},
    {"requests": [{"style": "FR", "count": "lots"}]},
    {"requests": [{"style": "FR", "count": -1}]},
    {"requests": [{"style": "FR", "count": 101}]},
    {"requests": [{"style": [], "count": 1}]},
    {"requests": [{"style": "FR", "type": []}]},
    {"requests": [{"style": "FR", "gender": []}]},
    {"requests": [{"style": "FR", "romanize": "false"}]},
])
def test_invalid_http_requests_are_400(demo, payload):
    client = create_app(demo).test_client()
    response = client.post("/api/generate", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert "error" in response.json


def test_unknown_style_does_not_crash_batch(demo):
    response = create_app(demo).test_client().post("/api/generate", json={"requests": [
        {"style": "does-not-exist"}, {"style": "FR", "count": 1},
    ]})
    assert response.status_code == 200
    assert "error" in response.json["results"][0]
    assert response.json["results"][1]["returned_count"] == 1


def test_missing_database_has_actionable_error(tmp_path):
    configure_database(tmp_path / "absent.db")
    with pytest.raises(ValueError, match="nomnom demo"):
        generate("FR")
    assert not (tmp_path / "absent.db").exists()


def test_full_build_honours_database_override(tmp_path, monkeypatch):
    import namegen.importers as importers
    destination = tmp_path / "new" / "names.db"
    monkeypatch.setenv("NOMNOM_DB_PATH", str(destination))
    for name in ("import_curated", "import_fantasy", "import_forebears",
                 "import_philipperemy", "import_geonames"):
        monkeypatch.setattr(importers, name, lambda db, data_dir: None)
    importers.build_all(data_dir=tmp_path)
    assert destination.is_file()


def test_full_build_refuses_existing_database(tmp_path):
    from namegen.importers import build_all
    existing = tmp_path / "existing.db"
    existing.write_bytes(b"leave this file alone")
    with pytest.raises(FileExistsError, match="Refusing to rebuild"):
        build_all(db_path=existing)
    assert existing.read_bytes() == b"leave this file alone"
