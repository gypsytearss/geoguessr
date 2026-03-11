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
from datetime import datetime, timezone, timedelta

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

FEED_URL = "https://www.geoguessr.com/api/v4/feed/private?count=50"
SUMMARY_URL = (
    "https://www.geoguessr.com/_next/data/{build}/en/duels/{game_id}/summary.json"
    "?token={game_id}"
)

# Human-like delay between requests (seconds)
DELAY_MIN = 1.0
DELAY_MAX = 4.0
# Every this many requests, take a longer reading pause
LONG_PAUSE_EVERY = 10
LONG_PAUSE_MIN = 12.0
LONG_PAUSE_MAX = 22.0


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
_request_count: int = 0


def _human_delay():
    global _last_request_time, _request_count
    _request_count += 1

    if _request_count > 1 and _request_count % LONG_PAUSE_EVERY == 0:
        pause = random.uniform(LONG_PAUSE_MIN, LONG_PAUSE_MAX)
        print(f"  [pause] Taking a {pause:.0f}s break after {_request_count} requests ...")
        time.sleep(pause)
    else:
        elapsed = time.monotonic() - _last_request_time
        delay = random.uniform(DELAY_MIN, DELAY_MAX)
        remaining = delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    _last_request_time = time.monotonic()


class RateLimitError(Exception):
    pass


def fetch_json(url: str) -> dict:
    _human_delay()
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with _opener.open(req) as resp:
            data = resp.read()
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
            return json.loads(data.decode())
    except urllib.error.HTTPError as e:
        if e.code in (400, 429):
            raise RateLimitError(f"HTTP {e.code} — possible rate limit. Stopping to protect session.")
        raise


# ---------------------------------------------------------------------------
# History — fetch game IDs by count or by days
# ---------------------------------------------------------------------------

def _parse_feed_game_ids(entries: list) -> list:
    """Extract (game_id, time) pairs for duel games from feed entries."""
    results = []
    seen = set()
    for entry in entries:
        payload_str = entry.get("payload", "")
        if not payload_str:
            continue
        try:
            items = json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            p = item.get("payload", {})
            if not isinstance(p, dict):
                continue
            if p.get("gameMode") == "Duels" and p.get("gameId"):
                gid = p["gameId"]
                if gid not in seen:
                    seen.add(gid)
                    results.append((gid, item.get("time", "")))
    return results


def _fetch_feed_page(pagination_token: str = "") -> tuple:
    """Fetch one page of the private feed. Returns (pairs, next_token)."""
    url = FEED_URL + (f"&paginationToken={pagination_token}" if pagination_token else "")
    resp = fetch_json(url)
    pairs = _parse_feed_game_ids(resp.get("entries", []))
    return pairs, resp.get("paginationToken", "")


def fetch_game_ids_by_count(n: int) -> list:
    game_ids = []
    token = ""
    while len(game_ids) < n:
        pairs, token = _fetch_feed_page(token)
        if not pairs:
            break
        for gid, _ in pairs:
            game_ids.append(gid)
            if len(game_ids) >= n:
                break
        if not token:
            break
    return game_ids


def fetch_game_ids_by_days(days: int) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    game_ids = []
    token = ""
    while True:
        pairs, token = _fetch_feed_page(token)
        if not pairs:
            break
        found_older = False
        for gid, time_str in pairs:
            if time_str:
                t = datetime.fromisoformat(time_str.rstrip("Z").split(".")[0]).replace(tzinfo=timezone.utc)
                if t < cutoff:
                    found_older = True
                    break
            game_ids.append(gid)
        if found_older or not token:
            break
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

def _prompt_query_mode():
    """Ask user how to scope the fetch. Returns (mode, value, label)."""
    while True:
        mode = input("Fetch by (g)ames or (d)ays? [g/d]: ").strip().lower()
        if mode in ("g", "d"):
            break
        print("  Enter 'g' or 'd'.")

    if mode == "g":
        while True:
            try:
                n = int(input("How many games? ").strip())
                if n > 0:
                    return "games", n, f"{n}-games"
            except ValueError:
                pass
            print("  Enter a positive integer.")
    else:
        while True:
            try:
                n = int(input("How many days? ").strip())
                if n > 0:
                    return "days", n, f"{n}-days"
            except ValueError:
                pass
            print("  Enter a positive integer.")


def main():
    mode, value, label = _prompt_query_mode()

    build_id = _fetch_build_id()
    print(f"Build ID: {build_id}")

    if mode == "games":
        print(f"\nFetching {value} most recent games ...")
        game_ids = fetch_game_ids_by_count(value)
    else:
        print(f"\nFetching games from the past {value} day(s) ...")
        game_ids = fetch_game_ids_by_days(value)

    print(f"Found {len(game_ids)} game ID(s).\n")

    games = []
    aborted = False
    for game_id in game_ids:
        url = SUMMARY_URL.format(build=build_id, game_id=game_id)
        try:
            summary = fetch_json(url)
            normalized = normalize_game(summary)
            if normalized:
                games.append(normalized)
                rounds = normalized["rounds"]
                print(f"  [ok] {game_id} — {len(rounds)} round(s), opponent: {normalized['opponent']['nick']}")
        except RateLimitError as e:
            print(f"\n  [abort] {e}")
            print(f"  Saving {len(games)} game(s) collected so far ...")
            aborted = True
            break
        except urllib.error.HTTPError as e:
            print(f"  [err] {game_id}: HTTP {e.code} {e.reason}")

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = os.path.join("outputs", f"{date_str}_{label}")
    os.makedirs(out_dir, exist_ok=True)

    games_path = os.path.join(out_dir, "games.json")
    with open(games_path, "w") as f:
        json.dump(games, f, indent=2)

    total_rounds = sum(len(g["rounds"]) for g in games)
    status = "PARTIAL — rate limited" if aborted else "complete"
    print(f"\nSaved {len(games)} game(s), {total_rounds} round(s) to {games_path} [{status}]")
    print(f"Run dashboard:  python dashboard.py {out_dir}")


if __name__ == "__main__":
    main()
