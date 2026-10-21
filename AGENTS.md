# Namebench

Standalone name sandbox. Preserve its original Git history and ignored local datasets. No dependency on sibling projects. Start `python -m namegen demo` for the hand-authored small dataset; never replace the world database with the demo.
Run `python -m pytest` after changes; verify packaged assets using a wheel outside the checkout for packaging changes. Full data rebuilds are opt-in and must target a new database. Do not commit generated databases, raw source datasets, secrets, caches or environments.

Keep all user-facing text, accessibility labels, errors and documentation in English. Preserve original-language names in datasets and scenario proper names.
