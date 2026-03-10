#!/usr/bin/env python3
"""Fetch and normalize GeoGuessr duel data."""

import gzip
import http.cookiejar
import json
import os
import random
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

import reverse_geocoder as rg


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

HEADERS = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/144.0.0.0 Safari/537.36"
    ),
    "x-client": "web",
}

def _fetch_build_id() -> str:
    """Fetch the current Next.js build ID from the GeoGuessr homepage."""
    import re
    req = urllib.request.Request(
        "https://www.geoguessr.com/",
        headers={"user-agent": HEADERS["user-agent"]},
    )
    with _opener.open(req) as resp:
        html = resp.read().decode(errors="ignore")
    match = re.search(r'"buildId":"([^"]+)"', html)
    if not match:
        raise SystemExit("Could not find Next.js buildId on GeoGuessr homepage")
    return match.group(1)

HISTORY_URL = "https://www.geoguessr.com/api/v4/game-history/me?gameMode=None&page={page}"
SUMMARY_URL = (
    "https://www.geoguessr.com/_next/data/{build}/en/duels/{game_id}/summary.json"
    "?token={game_id}"
)

# Fetch this many recent games (used during validation; switch to LOOKBACK_DAYS for full run)
NUM_GAMES = 10

# Human-like delay range between requests (seconds)
DELAY_MIN = 2.0
DELAY_MAX = 5.0


# ---------------------------------------------------------------------------
# HTTP — cookie jar tracks rolling _ncfa token automatically
# ---------------------------------------------------------------------------

_cookie_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cookie_jar))


def _seed_cookies():
    for name, value in [("gg_token", GG_TOKEN), ("_ncfa", GG_NCFA)]:
        cookie = http.cookiejar.Cookie(
            version=0, name=name, value=value,
            port=None, port_specified=False,
            domain=".geoguessr.com", domain_specified=True, domain_initial_dot=True,
            path="/", path_specified=True,
            secure=True, expires=None, discard=True,
            comment=None, comment_url=None, rest={},
        )
        _cookie_jar.set_cookie(cookie)


_seed_cookies()

_last_request_time: float = 0.0


def _human_delay():
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    remaining = delay - elapsed
    if remaining > 0:
        time.sleep(remaining)
    _last_request_time = time.monotonic()


def fetch_json(url: str) -> dict:
    _human_delay()
    req = urllib.request.Request(url, headers=HEADERS)
    with _opener.open(req) as resp:
        data = resp.read()
        try:
            data = gzip.decompress(data)
        except OSError:
            pass
        return json.loads(data.decode())


# ---------------------------------------------------------------------------
# History — fetch the N most recent game IDs
# ---------------------------------------------------------------------------

def fetch_recent_game_ids(n: int) -> list:
    game_ids = []
    page = 0

    while len(game_ids) < n:
        history = fetch_json(HISTORY_URL.format(page=page))
        entries = history.get("entries", [])
        if not entries:
            break
        for entry in entries:
            game_ids.append(entry["gameId"])
            if len(game_ids) >= n:
                break
        page += 1

    return game_ids


# ---------------------------------------------------------------------------
# Reverse geocode a guess lat/lng to a country code (offline, no API calls)
# ---------------------------------------------------------------------------

def guess_country(lat, lng) -> str:
    if lat is None or lng is None:
        return ""
    results = rg.search((lat, lng), verbose=False)
    return results[0].get("cc", "").lower() if results else ""


# ---------------------------------------------------------------------------
# Summary — normalize into clean structure
# ---------------------------------------------------------------------------

def _find_my_player_id(game: dict) -> str:
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

    player_guesses = {}
    for team in game.get("teams", []):
        for player in team.get("players", []):
            pid = player["playerId"]
            player_guesses[pid] = {
                g["roundNumber"]: g for g in player.get("guesses", [])
            }

    opponent_id = next((pid for pid in player_guesses if pid != my_id), "")
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

        my_lat = my_guess["lat"] if my_guess else None
        my_lng = my_guess["lng"] if my_guess else None
        opp_lat = opp_guess["lat"] if opp_guess else None
        opp_lng = opp_guess["lng"] if opp_guess else None

        rounds.append({
            "round_number": rn,
            "actual": {
                "lat": panorama.get("lat"),
                "lng": panorama.get("lng"),
                "country_code": panorama.get("countryCode"),
            },
            "my_guess": {
                "lat": my_lat,
                "lng": my_lng,
                "country_code": guess_country(my_lat, my_lng),
                "distance_m": my_guess["distance"] if my_guess else None,
                "score": my_guess["score"] if my_guess else None,
            },
            "opponent_guess": {
                "lat": opp_lat,
                "lng": opp_lng,
                "country_code": guess_country(opp_lat, opp_lng),
                "distance_m": opp_guess["distance"] if opp_guess else None,
                "score": opp_guess["score"] if opp_guess else None,
            },
        })

    start_time = ""
    raw_rounds = game.get("rounds", [])
    if raw_rounds:
        raw_start = raw_rounds[0].get("startTime", "")
        if isinstance(raw_start, (int, float)):
            start_time = datetime.fromtimestamp(raw_start / 1000, tz=timezone.utc).isoformat()
        else:
            start_time = str(raw_start)

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
    build_id = _fetch_build_id()
    print(f"Build ID: {build_id}")

    print(f"Fetching {NUM_GAMES} most recent games ...")
    game_ids = fetch_recent_game_ids(NUM_GAMES)
    print(f"Found {len(game_ids)} game ID(s).\n")

    games = []
    for game_id in game_ids:
        url = SUMMARY_URL.format(build=build_id, game_id=game_id)
        try:
            summary = fetch_json(url)
            normalized = normalize_game(summary)
            if normalized:
                games.append(normalized)
                rounds = normalized["rounds"]
                print(f"  [ok] {game_id} — {len(rounds)} round(s), opponent: {normalized['opponent']['nick']}")
        except urllib.error.HTTPError as e:
            print(f"  [err] {game_id}: HTTP {e.code} {e.reason}")

    output_path = "games.json"
    with open(output_path, "w") as f:
        json.dump(games, f, indent=2)

    total_rounds = sum(len(g["rounds"]) for g in games)
    print(f"\nSaved {len(games)} game(s), {total_rounds} round(s) to {output_path}")


if __name__ == "__main__":
    main()
