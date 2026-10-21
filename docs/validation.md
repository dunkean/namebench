# Validation

Standalone checks use Windows and Python 3.12.13. The runtime versions are pinned in `requirements.lock`.

- 27 Python tests cover the separate sample database, name/place/fantasy generation, transliteration, bulk generation, catalogue, HTTP validation and safe full-data rebuilds.
- Edge browser checks cover generation, JSON downloads, desktop/mobile layouts, JavaScript errors and horizontal overflow at 390 px.
- Wheel and source distributions are built. The wheel is installed and exercised in a fresh environment outside the checkout, including its bundled data and web assets.
- The full local world database is optional and is never required by these tests.

Use the commands in README.md. GitHub Actions runs the Python tests and distribution build. The browser demo is served locally, without public hosting.
