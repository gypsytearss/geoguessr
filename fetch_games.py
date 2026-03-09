#!/usr/bin/env python3
"""Fetch recent GeoGuessr duel summaries."""

import gzip
import json
import os
import urllib.request
import urllib.error


def _load_env(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())
    except FileNotFoundError:
        pass


_load_env()

gg_token = os.environ.get("GG_TOKEN", "")
gg_ncfa = os.environ.get("GG_NCFA", "")
if not gg_token or not gg_ncfa:
    raise SystemExit("Missing GG_TOKEN or GG_NCFA — set them in .env")

COOKIES = f"gg_token={gg_token}; _ncfa={gg_ncfa}"

# Next.js build ID embedded in the site — update if requests 404
NEXT_BUILD_ID = "XR9EfDQbg4KGrjm-PcLai"

HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "cookie": COOKIES,
}

HISTORY_URL = "https://www.geoguessr.com/api/v4/game-history/me?gameMode=None"
SUMMARY_URL = (
    "https://www.geoguessr.com/_next/data/{build}/en/duels/{game_id}/summary.json"
    "?token={game_id}"
)

NUM_GAMES = 4


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
        try:
            data = gzip.decompress(data)
        except OSError:
            pass
        return json.loads(data.decode())


def main():
    print("Fetching game history...")
    history = fetch_json(HISTORY_URL)
    entries = history["entries"]
    game_ids = [e["gameId"] for e in entries[:NUM_GAMES]]
    print(f"Most recent {NUM_GAMES} game IDs: {game_ids}\n")

    for game_id in game_ids:
        print(f"=== Game {game_id} ===")
        url = SUMMARY_URL.format(build=NEXT_BUILD_ID, game_id=game_id)
        try:
            summary = fetch_json(url)
            print(json.dumps(summary, indent=2))
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code}: {e.reason} — {url}")
        print()


if __name__ == "__main__":
    main()
