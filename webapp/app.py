"""Namebench local web application."""
from __future__ import annotations

from flask import Flask, jsonify, request, render_template
from werkzeug.exceptions import BadRequest

from namegen.api import configure_database, generate, list_styles, list_catalog


def create_app(database=None, demo=False):
    if database is not None:
        configure_database(database)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000

    @app.get("/")
    def index():
        return render_template("index.html", demo=demo)

    @app.get("/api/styles")
    def api_styles():
        return jsonify(list_styles())

    @app.get("/api/catalog")
    def api_catalog():
        return jsonify(list_catalog())

    @app.post("/api/generate")
    def api_generate():
        try:
            body = request.get_json()
            if not isinstance(body, dict) or not isinstance(body.get("requests"), list):
                raise ValueError("Expected an object with a requests array")
            if not 1 <= len(body["requests"]) <= 20:
                raise ValueError("Send between 1 and 20 requests")
            for item in body["requests"]:
                if not isinstance(item, dict):
                    raise ValueError("Each request must be an object")
                count = item.get("count", 1)
                if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
                    raise ValueError("Count must be an integer between 1 and 100")
                if not isinstance(item.get("style"), str):
                    raise ValueError("Style must be a string")
                if item.get("type", "forename") not in ("forename", "surname", "fullname", "place"):
                    raise ValueError("Unknown name type")
                if item.get("gender") not in (None, "", "M", "F"):
                    raise ValueError("Gender must be M, F or null")
                if not isinstance(item.get("romanize", False), bool):
                    raise ValueError("Romanize must be a boolean")
        except (BadRequest, ValueError) as exc:
            return jsonify(error=str(exc)), 400
        results = []
        for item in body["requests"]:
            style = item["style"]
            name_type = item.get("type", "forename")
            count = item.get("count", 1)
            gender = item.get("gender") or None
            romanize = item.get("romanize", False)
            result = dict(style=style, type=name_type, count=count, gender=gender, romanize=romanize)
            try:
                names = generate(style, name_type, count, gender, romanize=romanize)
                if not names:
                    raise ValueError("No names available for this selection in the active database")
                result.update(names=names, returned_count=len(names))
            except ValueError as exc:
                result["error"] = str(exc)
            results.append(result)
        return jsonify(results=results)

    return app


app = create_app()

if __name__ == "__main__":
    from namegen.demo import main
    main()
