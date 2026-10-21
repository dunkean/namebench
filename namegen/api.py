"""Public API for the name generator."""

from __future__ import annotations

from typing import Iterator, Optional

from namegen.db import NameDB
from namegen.zones import OnomasticResolver
from namegen.styles import StyleRegistry
from namegen.catalog import Catalog

def _romanize(name: str) -> str:
    """Transliterate non-Latin scripts (Cyrillic, CJK, etc.) while preserving Latin diacritics."""
    import unicodedata
    from anyascii import anyascii

    result = []
    for ch in name:
        if ord(ch) < 0x80:
            result.append(ch)
        else:
            uname = unicodedata.name(ch, "")
            if uname.startswith("LATIN") or uname.startswith("COMBINING"):
                result.append(ch)
            else:
                result.append(anyascii(ch))
    return "".join(result)


# Module-level singletons (lazy-initialized)
_db: Optional[NameDB] = None
_registry: Optional[StyleRegistry] = None
_catalog: Optional[Catalog] = None


def _get_registry() -> StyleRegistry:
    global _db, _registry, _catalog
    if _registry is None:
        if _db is None:
            _db = NameDB()
        if not _db.db_path.is_file():
            raise ValueError("Name database missing. Run `nomnom demo` for the bundled demo, "
                             "or build the full database with `nomnom --build`.")
        zones = OnomasticResolver()
        _catalog = Catalog(_db, zones)
        _registry = StyleRegistry(_db, zones, _catalog)
    return _registry


def generate(
    style: str,
    name_type: str = "forename",
    count: int = 1,
    gender: Optional[str] = None,
    romanize: bool = False,
) -> list[str]:
    """Generate names for a given style.

    Args:
        style: Style name (e.g. 'elf', 'french', 'demons', 'style.japanese')
        name_type: 'forename', 'surname', 'fullname', or 'place'
        count: Number of names to generate
        gender: 'M', 'F', or None
        romanize: If True, transliterate non-Latin characters to ASCII
    Returns:
        List of generated names
    Raises:
        ValueError: If style is not recognized or DB not built
    """
    _validate_request(name_type, count, gender)
    registry = _get_registry()
    spec = registry.resolve(style)

    if spec is None:
        raise ValueError(
            f"Unknown style: {style!r}. Use list_styles() to see available styles."
        )

    if spec.supported_types and name_type not in spec.supported_types:
        raise ValueError(
            f"Style {style!r} does not support type {name_type!r}. "
            f"Supported: {spec.supported_types}"
        )

    strategy = registry.get_strategy(spec)
    if strategy is None:
        raise ValueError(f"No strategy available for style: {style!r}")

    if name_type == "fullname":
        forenames = strategy.generate("forename", count, gender)
        surnames = strategy.generate("surname", count, gender=None)
        names = [f"{fn} {sn}" for fn, sn in zip(forenames, surnames)]
    else:
        names = strategy.generate(name_type, count, gender)

    if romanize:
        names = [_romanize(n) for n in names]

    return names


def generate_bulk(
    style: str,
    name_type: str = "forename",
    count: int = 1000,
    gender: Optional[str] = None,
    romanize: bool = False,
    unique: bool = False,
) -> Iterator[str]:
    """Streaming bulk name generator — yields names one at a time.

    Pre-loads name pools into memory once, then samples from Python,
    making per-name cost near-zero after the initial load.

    Args:
        style: Style name (e.g. 'elf', 'french', 'demons')
        name_type: 'forename', 'surname', 'fullname', or 'place'
        count: Number of names to generate
        gender: 'M', 'F', or None
        romanize: If True, transliterate non-Latin characters
        unique: If True, no duplicate names (capped at pool size)
    Yields:
        One name at a time
    """
    _validate_request(name_type, count, gender)
    registry = _get_registry()
    spec = registry.resolve(style)

    if spec is None:
        raise ValueError(
            f"Unknown style: {style!r}. Use list_styles() to see available styles."
        )

    if spec.supported_types and name_type not in spec.supported_types:
        raise ValueError(
            f"Style {style!r} does not support type {name_type!r}. "
            f"Supported: {spec.supported_types}"
        )

    # Enable bulk SQLite pragmas once
    registry.db.enable_bulk_pragmas()

    strategy = registry.get_strategy(spec)
    if strategy is None:
        raise ValueError(f"No strategy available for style: {style!r}")

    if name_type == "fullname":
        fn_iter = strategy.generate_bulk("forename", count, gender, unique)
        sn_iter = strategy.generate_bulk("surname", count, gender=None, unique=unique)
        for fn, sn in zip(fn_iter, sn_iter):
            name = f"{fn} {sn}"
            yield _romanize(name) if romanize else name
    else:
        for name in strategy.generate_bulk(name_type, count, gender, unique):
            yield _romanize(name) if romanize else name


def list_styles() -> dict[str, list[str]]:
    """List all available styles grouped by category.

    Returns:
        Dict with keys 'curated', 'fantasy', 'onomastic' mapping to style name lists
    """
    return _get_registry().list_styles()


def list_catalog() -> dict:
    """Return the full catalog as JSON-serializable dict for the webapp."""
    _get_registry()
    return _catalog.to_webapp_json()


def configure_database(path):
    """Select a database before starting a server or making generation calls."""
    global _db, _registry, _catalog
    if _db is not None:
        _db.close()
    _db, _registry, _catalog = NameDB(path), None, None


def _validate_request(name_type, count, gender):
    if name_type not in {"forename", "surname", "fullname", "place"}:
        raise ValueError("Unknown name type")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("Count must be a positive integer")
    if gender not in {None, "M", "F"}:
        raise ValueError("Gender must be M, F or null")
