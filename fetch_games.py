#!/usr/bin/env python3
"""Fetch and normalize GeoGuessr duel data for the past 7 days."""

import gzip
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_env(path: str = ".env") -> None:
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

GG_TOKEN = os.environ.get("GG_TOKEN", "")
GG_NCFA = os.environ.get("GG_NCFA", "")
MY_PLAYER_ID = os.environ.get("MY_PLAYER_ID", "")

if not GG_TOKEN or not GG_NCFA:
    raise SystemExit("Missing GG_TOKEN or GG_NCFA — set them in .env")

COOKIES = f"gg_token={GG_TOKEN}; _ncfa={GG_NCFA}"
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
    "x-client": "web",
}

# Next.js build ID embedded in the site — update if requests 404
NEXT_BUILD_ID = "XR9EfDQbg4KGrjm-PcLai"

HISTORY_URL = "https://www.geoguessr.com/api/v4/game-history/me?gameMode=None&page={page}"
SUMMARY_URL = (
    "https://www.geoguessr.com/_next/data/{build}/en/duels/{game_id}/summary.json"
    "?token={game_id}"
)

LOOKBACK_DAYS = 7
REQUEST_DELAY = 0.1  # seconds between API calls


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_last_request_time: float = 0.0


def fetch_json(url: str) -> dict:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    _last_request_time = time.monotonic()
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
        try:
            data = gzip.decompress(data)
        except OSError:
            pass
        return json.loads(data.decode())


# ---------------------------------------------------------------------------
# History — paginate until entries older than cutoff
# ---------------------------------------------------------------------------

def fetch_recent_game_ids(cutoff: datetime) -> list:
    """Return game IDs for games started on or after cutoff."""
    game_ids = []
    page = 0

    while True:
        history = fetch_json(HISTORY_URL.format(page=page))
        entries = history.get("entries", [])
        if not entries:
            break

        found_older = False
        for entry in entries:
            rounds = entry.get("duel", {}).get("rounds", [])
            if not rounds:
                continue
            start_str = rounds[0].get("startTime", "")
            if not start_str:
                continue
            start = datetime.strptime(start_str[:26], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
            if start < cutoff:
                found_older = True
                break
            game_ids.append(entry["gameId"])

        if found_older:
            break
        page += 1

    return game_ids


# ---------------------------------------------------------------------------
# Summary — normalize into clean structure
# ---------------------------------------------------------------------------

def _find_my_player_id(game: dict) -> str:
    """
    Detect the current user's player ID from the summary.
    The authenticated player has a non-null progressChange field.
    Falls back to MY_PLAYER_ID env var if set.
    """
    if MY_PLAYER_ID:
        return MY_PLAYER_ID

    for team in game.get("teams", []):
        for player in team.get("players", []):
            if player.get("progressChange") is not None:
                return player["playerId"]

    return ""


def normalize_game(summary: dict) -> dict:
    game = summary.get("pageProps", {}).get("game")
    if not game:
        return None

    my_id = _find_my_player_id(game)

    # Build a flat lookup: player_id -> list of guesses keyed by round
    player_guesses = {}
    for team in game.get("teams", []):
        for player in team.get("players", []):
            pid = player["playerId"]
            player_guesses[pid] = {
                g["roundNumber"]: g for g in player.get("guesses", [])
            }

    # Identify opponent
    opponent_id = next(
        (pid for pid in player_guesses if pid != my_id), ""
    )

    # Resolve opponent nick from players list
    opponent_nick = ""
    for team in game.get("teams", []):
        for player in team.get("players", []):
            if player["playerId"] == opponent_id:
                opponent_nick = player.get("nick", "")

    rounds = []
    for r in game.get("rounds", []):
        rn = r["roundNumber"]
        panorama = r.get("panorama", {})

        my_guess = player_guesses.get(my_id, {}).get(rn)
        opp_guess = player_guesses.get(opponent_id, {}).get(rn)

        rounds.append({
            "round_number": rn,
            "actual": {
                "lat": panorama.get("lat"),
                "lng": panorama.get("lng"),
                "country_code": panorama.get("countryCode"),
            },
            "my_guess": {
                "lat": my_guess["lat"] if my_guess else None,
                "lng": my_guess["lng"] if my_guess else None,
                "distance_m": my_guess["distance"] if my_guess else None,
                "score": my_guess["score"] if my_guess else None,
            },
            "opponent_guess": {
                "lat": opp_guess["lat"] if opp_guess else None,
                "lng": opp_guess["lng"] if opp_guess else None,
                "distance_m": opp_guess["distance"] if opp_guess else None,
                "score": opp_guess["score"] if opp_guess else None,
            },
        })

    start_time = ""
    raw_rounds = game.get("rounds", [])
    if raw_rounds:
        start_time = str(raw_rounds[0].get("startTime", ""))

    return {
        "game_id": game["gameId"],
        "date": start_time,
        "my_player_id": my_id,
        "opponent": {"id": opponent_id, "nick": opponent_nick},
        "rounds": rounds,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    print(f"Fetching games since {cutoff.date()} ...")

    game_ids = fetch_recent_game_ids(cutoff)
    print(f"Found {len(game_ids)} game(s) in the last {LOOKBACK_DAYS} days.\n")

    games = []
    for game_id in game_ids:
        url = SUMMARY_URL.format(build=NEXT_BUILD_ID, game_id=game_id)
        try:
            summary = fetch_json(url)
            normalized = normalize_game(summary)
            if normalized:
                games.append(normalized)
                print(f"  [ok] {game_id} — {len(normalized['rounds'])} round(s)")
        except urllib.error.HTTPError as e:
            print(f"  [err] {game_id}: HTTP {e.code} {e.reason}")

    output_path = "games.json"
    with open(output_path, "w") as f:
        json.dump(games, f, indent=2)

    print(f"\nSaved {len(games)} game(s) to {output_path}")


if __name__ == "__main__":
    main()
