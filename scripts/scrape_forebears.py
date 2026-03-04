#!/usr/bin/env python3
"""
Scrape forenames and surnames from forebears.io.

For each name collects: top-5 countries by incidence + alternate forms.
Output: flat JSON array with one entry per name (alt forms get their own entry
sharing the parent's countries).

Uses curl-cffi to impersonate real browser TLS fingerprints (bypasses bot detection).

Phases (run independently or all at once):
    discover  – crawl prefix listing pages, collect every name URL
    scrape    – fetch each name's detail page, extract data
    compile   – assemble final JSON from the incremental checkpoint

Fully resumable: re-run safely after interruption.

Usage:
    python scrape_forebears.py                           # full pipeline
    python scrape_forebears.py --phase discover
    python scrape_forebears.py --phase scrape
    python scrape_forebears.py --phase compile
    python scrape_forebears.py --concurrency 3 --delay 1
    python scrape_forebears.py --proxy socks5://127.0.0.1:9050   # Tor
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
import threading
import urllib.parse
from pathlib import Path
from typing import Optional

import socket
import string

from curl_cffi.requests import AsyncSession, Session
from bs4 import BeautifulSoup

# ── Constants ────────────────────────────────────────────────────────────────

BASE = "https://forebears.io"
CKPT = Path("forebears_checkpoint")
OUT = Path("forebears_names.json")

# Browser profiles to rotate through (curl-cffi impersonation targets)
BROWSERS = ["chrome", "chrome", "chrome", "edge", "safari"]

# Single-letter prefixes found on the site (Latin + accented/special)
_ALPHA = list("abcdefghijklmnopqrstuvwxyz")
_SPECIAL = [
    "á", "å", "â", "ä", "à", "æ", "ã",
    "ç", "č", "ć",
    "đ", "ď",
    "é", "è",
    "í",
    "ł", "ľ",
    "ñ", "ň",
    "ö", "ø", "ó", "ő", "õ", "ð",
    "ř",
    "ş", "š", "ș", "ś",
    "ţ", "þ", "ț", "ť",
    "ü", "ú", "ū",
    "ž", "ż",
]
PREFIXES_1 = _ALPHA + _SPECIAL
NAME_TYPES = ("surnames", "forenames")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ── URL helpers ──────────────────────────────────────────────────────────────

def _resolve(href: str, base: str = BASE + "/") -> str:
    """Resolve an href against a base URL, normalising /x/ prefix away."""
    if href.startswith("http"):
        url = href
    else:
        url = urllib.parse.urljoin(base, href)
    url = re.sub(r"(forebears\.io)/x/(surnames|forenames)/", r"\1/\2/", url)
    return url


def _read_set(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {l.strip() for l in path.read_text("utf-8").splitlines() if l.strip()}


def _append(path: Path, lines: list[str]) -> None:
    if not lines:
        return
    with path.open("a", encoding="utf-8") as f:
        for l in lines:
            f.write(l + "\n")


# ── Async HTTP with TLS impersonation and rate-limiting ──────────────────────

# Multiple Tor SOCKS ports (start extra instances for throughput)
TOR_PORTS = [9050, 9060, 9070]


def _tor_proxy(base_proxy: str) -> str:
    """Generate a Tor SOCKS proxy URL with random credentials for circuit isolation.

    Each unique user:pass pair gets a different Tor circuit = different exit IP.
    Distributes across multiple Tor ports if available.
    """
    user = "".join(random.choices(string.ascii_letters, k=10))
    passwd = "".join(random.choices(string.ascii_letters, k=10))
    port = random.choice(TOR_PORTS)
    return f"socks5://{user}:{passwd}@127.0.0.1:{port}"


class TorSession:
    """A persistent Tor session with fixed credentials (= fixed circuit/exit IP).

    Reuses the same circuit for speed. Rotates to a new circuit on 403.
    """
    __slots__ = ("_proxy_base", "_session", "_consecutive_403")

    def __init__(self):
        self._proxy_base = None
        self._session: Optional[Session] = None
        self._consecutive_403 = 0

    def _rotate(self) -> None:
        """Get new credentials = new Tor circuit = new exit IP."""
        user = "".join(random.choices(string.ascii_letters, k=10))
        passwd = "".join(random.choices(string.ascii_letters, k=10))
        port = random.choice(TOR_PORTS)
        self._proxy_base = f"socks5://{user}:{passwd}@127.0.0.1:{port}"
        self._session = Session(
            impersonate=random.choice(BROWSERS),
            proxy=self._proxy_base,
        )
        self._consecutive_403 = 0

    def fetch(self, url: str, retries: int = 10) -> Optional[str]:
        if self._session is None:
            self._rotate()
        for attempt in range(retries):
            try:
                r = self._session.get(url, timeout=30, allow_redirects=True)
                if r.status_code == 200:
                    self._consecutive_403 = 0
                    return r.text
                if r.status_code == 404:
                    self._consecutive_403 = 0
                    return None
                if r.status_code in (403, 429, 503):
                    self._consecutive_403 += 1
                    if self._consecutive_403 >= 2:
                        # This exit IP is banned, rotate
                        self._rotate()
                    continue
            except Exception:
                # Connection error — rotate to new circuit
                self._rotate()
        return None


class Fetcher:
    """HTTP fetcher using curl-cffi with persistent Tor sessions.

    Each worker thread gets its own TorSession with a stable circuit.
    Circuits are rotated only when blocked (403).
    """

    def __init__(self, concurrency: int = 3, delay: float = 1.0, proxy: str | None = None):
        self.sem = asyncio.Semaphore(concurrency)
        self.delay = delay
        self.proxy = proxy
        self.ok = 0
        self.fail = 0
        self._is_tor = proxy is not None and "socks5" in (proxy or "")
        self._local = threading.local()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    def _get_tor_session(self) -> TorSession:
        """Get the TorSession for the current thread (one per worker)."""
        ts = getattr(self._local, "tor_session", None)
        if ts is None:
            ts = TorSession()
            self._local.tor_session = ts
        return ts

    def _fetch_sync(self, url: str, retries: int = 10) -> Optional[str]:
        """Synchronous fetch (called from thread pool)."""
        if self._is_tor:
            ts = self._get_tor_session()
            result = ts.fetch(url, retries)
            if result is not None:
                self.ok += 1
            else:
                self.fail += 1
            return result

        # Non-Tor path
        for attempt in range(retries):
            try:
                s = Session(impersonate=random.choice(BROWSERS), proxy=self.proxy)
                r = s.get(url, timeout=30, allow_redirects=True)
                if r.status_code == 200:
                    self.ok += 1
                    time.sleep(self.delay + random.uniform(0, self.delay * 0.3))
                    return r.text
                if r.status_code == 404:
                    return None
                if r.status_code in (403, 429, 503):
                    time.sleep(4 + random.uniform(2, 6))
                    continue
            except Exception:
                time.sleep(0.5 + attempt * 0.5)
        self.fail += 1
        return None

    async def get(self, url: str) -> Optional[str]:
        """Async wrapper that runs sync fetch in a thread."""
        async with self.sem:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._fetch_sync, url)


# ── HTML parsers ─────────────────────────────────────────────────────────────

def parse_listing(html: str, name_type: str) -> tuple[list[str], list[str]]:
    """Parse a prefix listing page → (sub_prefix_urls, name_detail_urls)."""
    soup = BeautifulSoup(html, "lxml")

    base_tag = soup.find("base", href=True)
    base = urllib.parse.urljoin(BASE + "/", base_tag["href"]) if base_tag else BASE + "/"

    sub_prefixes: list[str] = []
    name_urls: list[str] = []

    for a in soup.find_all("a", href=True):
        if "begining-with" in a["href"]:
            sub_prefixes.append(_resolve(a["href"], base))

    for a in soup.find_all("a", class_="search-result", href=True):
        resolved = _resolve(a["href"], base)
        path = urllib.parse.urlparse(resolved).path
        parts = [p for p in path.split("/") if p]
        if len(parts) == 2 and parts[0] == name_type:
            name_urls.append(resolved)

    return sub_prefixes, name_urls


def parse_detail(html: str, name_type_singular: str) -> tuple[str, list[str], list[str]]:
    """Parse a name detail page → (display_name, top_5_countries, alt_forms)."""
    soup = BeautifulSoup(html, "lxml")

    # ── Display name from <title> ──
    display_name = ""
    title_tag = soup.find("title")
    if title_tag:
        t = title_tag.get_text(strip=True)
        for marker in (" Surname", " Name Meaning", " Forename"):
            if marker in t:
                display_name = t.split(marker)[0].strip()
                break
        if not display_name and " - " in t:
            display_name = t.split(" - ")[0].strip()

    # ── Top-5 countries ──
    countries: list[str] = []
    for table in soup.find_all("table"):
        ths = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if "place" not in ths:
            continue
        place_col = ths.index("place")
        for row in table.find_all("tr"):
            tds = row.find_all("td")
            if not tds or place_col >= len(tds):
                continue
            place = tds[place_col].get_text(strip=True)
            if place:
                countries.append(place)
            if len(countries) >= 5:
                break
        if countries:
            break

    # ── Alternate forms ──
    alt_forms: list[str] = []
    for txt in soup.find_all(string=lambda s: s and "alternate form" in s.lower()):
        parent = txt.parent
        if parent is None:
            continue
        for a in parent.find_all("a", href=True):
            h = a["href"]
            if ("surnames/" in h or "forenames/" in h) and "begining-with" not in h:
                name = a.get_text(strip=True)
                if name and name not in alt_forms:
                    alt_forms.append(name)

    return display_name, countries, alt_forms


# ── Phase 1 – Discover ──────────────────────────────────────────────────────

async def phase_discover(fetcher: Fetcher) -> None:
    CKPT.mkdir(exist_ok=True)

    for ntype in NAME_TYPES:
        urls_file = CKPT / f"{ntype}_urls.txt"
        known = _read_set(urls_file)
        if known:
            log(f"[discover:{ntype}] {len(known)} URLs already on disk — skipping")
            continue

        log(f"[discover:{ntype}] fetching {len(PREFIXES_1)} 1-letter prefix pages …")

        one_letter_urls = [
            f"{BASE}/{ntype}/begining-with/{urllib.parse.quote(ch, safe='')}"
            for ch in PREFIXES_1
        ]

        two_letter_set: set[str] = set()
        new_names: list[str] = []

        # Fetch 1-letter pages (small batch)
        for i in range(0, len(one_letter_urls), 10):
            batch = one_letter_urls[i:i+10]
            pages = await asyncio.gather(*[fetcher.get(u) for u in batch])
            for html in pages:
                if not html:
                    continue
                subs, names = parse_listing(html, ntype)
                two_letter_set.update(subs)
                for n in names:
                    if n not in known:
                        known.add(n)
                        new_names.append(n)

        _append(urls_file, new_names)
        new_names.clear()
        log(f"[discover:{ntype}] found {len(two_letter_set)} 2-letter prefix pages")

        # Fetch 2-letter pages
        two_letter_list = sorted(two_letter_set)
        batch_sz = 10
        for i in range(0, len(two_letter_list), batch_sz):
            batch = two_letter_list[i : i + batch_sz]
            pages = await asyncio.gather(*[fetcher.get(u) for u in batch])
            for html in pages:
                if not html:
                    continue
                _, names = parse_listing(html, ntype)
                for n in names:
                    if n not in known:
                        known.add(n)
                        new_names.append(n)
            _append(urls_file, new_names)
            done = min(i + batch_sz, len(two_letter_list))
            log(
                f"[discover:{ntype}] prefixes {done}/{len(two_letter_list)}  "
                f"names: {len(known)}"
            )
            new_names.clear()

        log(f"[discover:{ntype}] DONE – {len(known)} unique name URLs")


# ── Phase 2 – Scrape ────────────────────────────────────────────────────────

async def phase_scrape(fetcher: Fetcher) -> None:
    """Scrape name detail pages using a worker-queue pattern.

    Unlike batch-gather, workers continuously pull from a queue so all
    concurrency slots stay busy — no idle time waiting for slow retries.
    """
    results_file = CKPT / "results.jsonl"

    processed: set[str] = set()
    if results_file.exists():
        with results_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    processed.add(json.loads(line).get("_url", ""))
                except json.JSONDecodeError:
                    pass
    log(f"[scrape] {len(processed)} already done")

    todo: list[tuple[str, str]] = []
    for ntype in NAME_TYPES:
        urls_file = CKPT / f"{ntype}_urls.txt"
        singular = ntype[:-1]
        for url in _read_set(urls_file):
            if url not in processed:
                todo.append((url, singular))

    random.shuffle(todo)

    log(f"[scrape] {len(todo)} names to scrape")
    if not todo:
        return

    total = len(todo)
    done = 0
    ok_count = 0
    fail_count = 0
    t0 = time.monotonic()
    write_lock = threading.Lock()

    queue: asyncio.Queue[tuple[str, str] | None] = asyncio.Queue()
    for item in todo:
        queue.put_nowait(item)

    async def worker():
        nonlocal done, ok_count, fail_count
        loop = asyncio.get_event_loop()
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if item is None:
                return

            url, singular = item
            html = await loop.run_in_executor(None, fetcher._fetch_sync, url)
            done += 1

            if not html:
                fail_count += 1
                queue.task_done()
                continue

            ok_count += 1
            display_name, countries, alt_forms = parse_detail(html, singular)

            if not display_name:
                slug = urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
                display_name = urllib.parse.unquote(slug)

            line = json.dumps(
                {
                    "_url": url,
                    "name": display_name,
                    "type": singular,
                    "countries": countries,
                    "alt_forms": alt_forms,
                },
                ensure_ascii=False,
            )

            with write_lock:
                with results_file.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")

            if ok_count % 50 == 0:
                elapsed = time.monotonic() - t0
                rate = ok_count / elapsed if elapsed else 0
                remaining = total - done
                eta = remaining / rate if rate else 0
                log(
                    f"[scrape] ok={ok_count} fail={fail_count} "
                    f"done={done}/{total} ({done * 100 // total}%)  "
                    f"{rate:.2f}/s  ETA {eta / 3600:.1f}h"
                )

            queue.task_done()

    # Launch workers (concurrency controlled by fetcher.sem)
    n_workers = fetcher.sem._value  # match concurrency
    log(f"[scrape] launching {n_workers} async workers")
    workers = [asyncio.create_task(worker()) for _ in range(n_workers)]
    await asyncio.gather(*workers)

    elapsed = time.monotonic() - t0
    rate = ok_count / elapsed if elapsed else 0
    log(
        f"[scrape] FINISHED  ok={ok_count} fail={fail_count} "
        f"total_time={elapsed / 3600:.1f}h  rate={rate:.2f}/s"
    )


# ── Phase 3 – Compile ───────────────────────────────────────────────────────

def phase_compile() -> None:
    results_file = CKPT / "results.jsonl"
    if not results_file.exists():
        log("[compile] nothing to compile (run scrape first)")
        return

    log("[compile] streaming output …")
    count = 0
    with OUT.open("w", encoding="utf-8") as out:
        out.write("[\n")
        first = True

        with results_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not r.get("name"):
                    continue

                entry = {
                    "name": r["name"],
                    "type": r["type"],
                    "countries": r["countries"],
                }
                if not first:
                    out.write(",\n")
                out.write(json.dumps(entry, ensure_ascii=False))
                first = False
                count += 1

                for alt in r.get("alt_forms", []):
                    out.write(",\n")
                    out.write(
                        json.dumps(
                            {"name": alt, "type": r["type"], "countries": r["countries"]},
                            ensure_ascii=False,
                        )
                    )
                    count += 1

        out.write("\n]\n")

    size_mb = OUT.stat().st_size / (1024 * 1024)
    log(f"[compile] wrote {count:,} entries → {OUT} ({size_mb:.1f} MB)")


# ── CLI ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape forebears.io names")
    ap.add_argument(
        "--phase", choices=["discover", "scrape", "compile", "all"], default="all",
    )
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--delay", type=float, default=1.0,
                    help="Base delay between requests in seconds (default: 1.0)")
    ap.add_argument("--proxy", type=str, default=None,
                    help="Proxy URL, e.g. socks5://127.0.0.1:9050 for Tor")
    args = ap.parse_args()

    # Set thread pool large enough for concurrency
    import concurrent.futures
    loop = asyncio.get_event_loop()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency + 10)
    loop.set_default_executor(pool)

    if args.phase in ("discover", "scrape", "all"):
        async with Fetcher(args.concurrency, args.delay, args.proxy) as fetcher:
            if args.phase in ("discover", "all"):
                await phase_discover(fetcher)
            if args.phase in ("scrape", "all"):
                await phase_scrape(fetcher)

    if args.phase in ("compile", "all"):
        phase_compile()

    pool.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
