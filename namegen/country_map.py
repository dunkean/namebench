"""Country name ↔ ISO 3166-1 alpha-2 mapping.

Handles forebears' non-standard country names plus edge cases.
"""

from __future__ import annotations

import pycountry

# Manual overrides for names that pycountry can't resolve or gets wrong.
# Forebears country name -> ISO alpha-2
_OVERRIDES: dict[str, str] = {
    # Sub-national / constituent countries
    "England": "GB",
    "Scotland": "GB",
    "Wales": "GB",
    "Northern Ireland": "GB",
    # Common name vs official name
    "Russia": "RU",
    "Iran": "IR",
    "Syria": "SY",
    "South Korea": "KR",
    "North Korea": "KP",
    "Bolivia": "BO",
    "Venezuela": "VE",
    "Vietnam": "VN",
    "Laos": "LA",
    "Moldova": "MD",
    "Tanzania": "TZ",
    "Brunei": "BN",
    "Ivory Coast": "CI",
    "East Timor": "TL",
    "Congo": "CG",
    "DR Congo": "CD",
    "Czechia": "CZ",
    "Micronesia": "FM",
    "Gambia": "GM",
    "Swaziland": "SZ",
    "Cape Verde": "CV",
    "Palestine": "PS",
    "Taiwan": "TW",
    "Hong Kong": "HK",
    "Macau": "MO",
    "Kosovo": "XK",
    "Myanmar": "MM",
    "Bahamas": "BS",
    # Disputed / unrecognized territories
    "Abkhazia": "GE",
    "South Ossetia": "GE",
    "Transnistria": "MD",
    "Northern Cyprus": "CY",
    "Somaliland": "SO",
    "Akrotiri and Dhekelia": "CY",
    # Territories
    "Puerto Rico": "PR",
    "Guam": "GU",
    "American Samoa": "AS",
    "United States Virgin Islands": "VI",
    "British Virgin Islands": "VG",
    "Northern Mariana Islands": "MP",
    "French Polynesia": "PF",
    "New Caledonia": "NC",
    "Wallis and Futuna": "WF",
    "Saint Martin": "MF",
    "Saint Barthelemy": "BL",
    "Saint Pierre and Miquelon": "PM",
    "Cook Islands": "CK",
    "Niue": "NU",
    "Norfolk Island": "NF",
    "Falkland Islands": "FK",
    "Montserrat": "MS",
    "Turks and Caicos Islands": "TC",
    "Cayman Islands": "KY",
    "Bermuda": "BM",
    "Gibraltar": "GI",
    "Faroe Islands": "FO",
    "Greenland": "GL",
    "Isle of Man": "IM",
    "Guernsey": "GG",
    "Jersey": "JE",
    "Aruba": "AW",
    "Curaçao": "CW",
    "Curacao": "CW",
    "Cura\u00e7ao": "CW",
    "Turkey": "TR",
    "North Macedonia": "MK",
    "Saint Helena, Ascension and Tristan da Cunha": "SH",
    "São Tomé and Príncipe": "ST",
    "S\u00e3o Tom\u00e9 and Pr\u00edncipe": "ST",
}

# Build reverse map: ISO -> primary English name
_ISO_TO_NAME: dict[str, str] = {}

# Cache for resolved lookups
_CACHE: dict[str, str | None] = {}


def name_to_iso(country_name: str) -> str | None:
    """Convert a country name (as used by forebears) to ISO alpha-2 code.

    Returns None if unmappable.
    """
    if country_name in _CACHE:
        return _CACHE[country_name]

    # Check overrides first
    if country_name in _OVERRIDES:
        code = _OVERRIDES[country_name]
        _CACHE[country_name] = code
        return code

    # Try pycountry exact match
    try:
        c = pycountry.countries.lookup(country_name)
        code = c.alpha_2
        _CACHE[country_name] = code
        return code
    except LookupError:
        pass

    # Try fuzzy search
    try:
        results = pycountry.countries.search_fuzzy(country_name)
        if results:
            code = results[0].alpha_2
            _CACHE[country_name] = code
            return code
    except LookupError:
        pass

    _CACHE[country_name] = None
    return None


def iso_to_name(code: str) -> str | None:
    """Convert ISO alpha-2 to English country name."""
    code = code.upper()
    try:
        return pycountry.countries.get(alpha_2=code).name
    except (LookupError, AttributeError):
        return None
