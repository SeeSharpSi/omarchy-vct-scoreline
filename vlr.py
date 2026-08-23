#!/usr/bin/env python3
"""Fetch live and upcoming top-tier VCT matches from VLR.gg."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


BASE_URL = "https://www.vlr.gg/"
MATCHES_URL = urljoin(BASE_URL, "matches/")
USER_AGENT = "cassian.vct-scoreline/1.0 (+https://www.vlr.gg/)"
MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_LIVE_MATCHES = 8
MAX_UPCOMING = 8
MAX_WARNINGS = 6
MAX_TEXT_CHARS = 200
MAX_SHORT_TEXT_CHARS = 32
MAX_WARNING_CHARS = 400

VLR_MATCH_URL_RE = re.compile(r"^https://(?:www\.)?vlr\.gg/\d+(?:/|$)")

EXCLUDED_EVENT_RE = re.compile(
    r"(?:challengers|\bvcl\b|ascension|game[- ]?changers|academy|collegiate|"
    r"college|off\s*//?\s*season|offseason)",
    re.IGNORECASE,
)
TOP_TIER_EVENT_RE = re.compile(
    r"^(?:"
    r"VCT\s+\d{4}:\s*(?:Americas|EMEA|Pacific|China)\b|"
    r"(?:Valorant\s+)?Champions\s+Tour\s+\d{4}:\s*"
    r"(?:Americas|EMEA|Pacific|China|LOCK\s*//?\s*IN)\b|"
    r"(?:Valorant\s+|VCT\s+)?Masters\b|"
    r"Valorant\s+Champions\s+\d{4}\b"
    r")",
    re.IGNORECASE,
)
TOP_TIER_PATH_RE = re.compile(
    r"(?:^|-)vct-\d{4}-(?:americas|emea|pacific|china)(?:-|$)|"
    r"(?:^|-)(?:valorant-)?masters(?:-|$)|"
    r"(?:^|-)valorant-champions-\d{4}(?:-|$)|"
    r"(?:^|-)lock-in(?:-|$)",
    re.IGNORECASE,
)


def clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def parse_int(value: str | None) -> int | None:
    match = re.search(r"-?\d+", clean_text(value or ""))
    return int(match.group(0)) if match else None


class Node:
    """Minimal DOM node for VLR's server-rendered HTML."""

    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: list[tuple[str, str | None]] | None = None) -> None:
        self.tag = tag
        self.attrs = {key: value or "" for key, value in (attrs or [])}
        self.children: list[Node | str] = []
        self.parent: Node | None = None

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()

    def attr(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    def nodes(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.nodes()

    def find_all(self, predicate):
        return [node for node in self.nodes() if predicate(node)]

    def find_first(self, predicate) -> Node | None:
        for node in self.nodes():
            if predicate(node):
                return node
        return None

    def text(self) -> str:
        return "".join(child.text() if isinstance(child, Node) else child for child in self.children)

    def direct_text(self) -> str:
        return "".join(child for child in self.children if isinstance(child, str))


class DocumentParser(HTMLParser):
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), attrs)
        node.parent = self.stack[-1]
        self.stack[-1].children.append(node)
        if tag.lower() not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def parse_document(html: str) -> Node:
    parser = DocumentParser()
    parser.feed(html)
    parser.close()
    return parser.root


def class_node(node: Node, name: str) -> Node | None:
    return node.find_first(lambda item: item.has_class(name))


def class_nodes(node: Node, name: str) -> list[Node]:
    return node.find_all(lambda item: item.has_class(name))


def text_without_classes(node: Node, excluded: set[str]) -> str:
    if any(node.has_class(name) for name in excluded):
        return ""
    return "".join(
        text_without_classes(child, excluded) if isinstance(child, Node) else child
        for child in node.children
    )


def absolute_vlr_url(href: str) -> str:
    candidate = urljoin(BASE_URL, href.strip())
    parsed = urlparse(candidate)
    if parsed.scheme != "https" or parsed.netloc not in {"vlr.gg", "www.vlr.gg"}:
        return ""
    return candidate


def match_id(url: str) -> str:
    match = re.match(r"^/(\d+)(?:/|$)", urlparse(url).path)
    return match.group(1) if match else ""


def is_top_tier_vct(event: str, href: str = "") -> bool:
    event_name = clean_text(event)
    path = urlparse(urljoin(BASE_URL, href)).path.lower().strip("/")
    searchable = f"{event_name} {path}"
    if EXCLUDED_EVENT_RE.search(searchable):
        return False
    return bool(TOP_TIER_EVENT_RE.search(event_name) or TOP_TIER_PATH_RE.search(path))


def parse_team_from_listing(node: Node) -> dict:
    name_node = class_node(node, "match-item-vs-team-name")
    score_node = class_node(node, "match-item-vs-team-score")
    return {
        "name": clean_text(name_node.text() if name_node else ""),
        "seriesScore": parse_int(score_node.text() if score_node else ""),
    }


def parse_match_node(node: Node, date_label: str) -> dict:
    href = absolute_vlr_url(node.attr("href"))
    event_node = class_node(node, "match-item-event")
    series_node = class_node(node, "match-item-event-series")
    status_node = class_node(node, "ml-status")
    eta_node = class_node(node, "ml-eta")
    teams = [parse_team_from_listing(team) for team in class_nodes(node, "match-item-vs-team")[:2]]
    while len(teams) < 2:
        teams.append({"name": "", "seriesScore": None})

    return {
        "id": match_id(href),
        "url": href,
        "event": clean_text(event_node.direct_text() if event_node else ""),
        "series": clean_text(series_node.text() if series_node else ""),
        "date": clean_text(date_label),
        "time": clean_text((class_node(node, "match-item-time") or Node("empty")).text()),
        "eta": clean_text(eta_node.text() if eta_node else ""),
        "status": clean_text(status_node.text() if status_node else "").lower(),
        "teams": teams,
    }


def parse_matches(html: str) -> list[dict]:
    root = parse_document(html)
    matches: list[dict] = []
    date_label = ""
    for node in root.nodes():
        if node.tag == "div" and node.has_class("wf-label") and node.has_class("mod-large"):
            date_label = clean_text(node.direct_text())
        if node.tag != "a" or not node.has_class("match-item"):
            continue
        match = parse_match_node(node, date_label)
        if match["url"] and match["id"]:
            matches.append(match)
    return matches


def side_from_classes(classes: str) -> str | None:
    tokens = set(classes.split())
    if "mod-t" in tokens:
        return "t"
    if "mod-ct" in tokens:
        return "ct"
    return None


def opposite(side: str | None) -> str | None:
    if side == "t":
        return "ct"
    if side == "ct":
        return "t"
    return None


def complete_sides(sides: list[str | None]) -> list[str | None]:
    result = list(sides[:2])
    while len(result) < 2:
        result.append(None)
    if result[0] is None and result[1] is not None:
        result[0] = opposite(result[1])
    elif result[1] is None and result[0] is not None:
        result[1] = opposite(result[0])
    return result


def parse_rounds(game: Node) -> list[dict]:
    rounds: list[dict] = []
    for column in class_nodes(game, "vlr-rounds-row-col"):
        number_node = class_node(column, "rnd-num")
        number = parse_int(number_node.text() if number_node else "")
        if number is None:
            continue
        squares = [
            child for child in column.children
            if isinstance(child, Node) and child.has_class("rnd-sq")
        ]
        sides = complete_sides([side_from_classes(square.attr("class")) for square in squares[:2]])
        if any(side is not None for side in sides):
            rounds.append({"number": number, "sides": sides})
    rounds.sort(key=lambda item: item["number"])
    return rounds


def infer_attacking_team(
    scores: list[int | None],
    initial_sides: list[str | None],
    rounds: list[dict],
) -> int | None:
    if len(scores) < 2 or any(score is None for score in scores):
        return None
    initial = complete_sides(initial_sides)
    if any(side is None for side in initial):
        return None

    current_round = sum(score for score in scores if score is not None) + 1
    if current_round <= 12:
        current_sides = initial
    elif current_round <= 24:
        current_sides = [opposite(side) for side in initial]
    elif rounds:
        current_sides = [opposite(side) for side in complete_sides(rounds[-1]["sides"])]
    else:
        current_sides = initial if (current_round - 25) % 2 == 0 else [opposite(side) for side in initial]

    for index, side in enumerate(current_sides):
        if side == "t":
            return index
    return None


def parse_game_team(node: Node) -> dict:
    name_node = class_node(node, "team-name")
    score_node = class_node(node, "score")
    side_spans = [
        child for child in node.nodes()
        if child.tag == "span" and side_from_classes(child.attr("class")) is not None
    ]
    return {
        "name": clean_text(name_node.text() if name_node else ""),
        "mapScore": parse_int(score_node.text() if score_node else ""),
        "initialSide": side_from_classes(side_spans[0].attr("class")) if side_spans else None,
    }


def find_active_game(root: Node) -> Node | None:
    live_nav = root.find_first(
        lambda node: node.has_class("vm-stats-gamesnav-item")
        and node.has_class("mod-live")
        and node.attr("data-game-id") not in {"", "all"}
    )
    if live_nav:
        game_id = live_nav.attr("data-game-id")
        return root.find_first(
            lambda node: node.has_class("vm-stats-game") and node.attr("data-game-id") == game_id
        )

    candidates = root.find_all(
        lambda node: node.has_class("vm-stats-game")
        and node.attr("data-game-id") not in {"", "all"}
        and class_node(node, "vm-stats-game-header") is not None
    )
    active = [game for game in candidates if game.has_class("mod-active")]
    return active[-1] if active else (candidates[-1] if candidates else None)


def parse_detail(html: str) -> dict:
    root = parse_document(html)
    game = find_active_game(root)
    if game is None:
        raise ValueError("VLR did not expose active map data")
    header = class_node(game, "vm-stats-game-header")
    if header is None:
        raise ValueError("VLR active map has no score header")

    team_nodes = [
        child for child in header.children
        if isinstance(child, Node) and child.has_class("team")
    ]
    teams = [parse_game_team(team) for team in team_nodes[:2]]
    if len(teams) != 2:
        raise ValueError("VLR active map has incomplete teams")

    map_node = class_node(header, "map")
    map_name = clean_text(text_without_classes(map_node, {"picked", "map-duration"})) if map_node else ""
    map_name = re.sub(r"\bPICK\b", "", map_name, flags=re.IGNORECASE).strip(" -")
    scores = [team["mapScore"] for team in teams]
    rounds = parse_rounds(game)
    current_round = sum(score for score in scores if score is not None) + 1 if all(
        score is not None for score in scores
    ) else None

    return {
        "gameId": game.attr("data-game-id"),
        "map": map_name,
        "teams": [{"name": team["name"], "mapScore": team["mapScore"]} for team in teams],
        "attackingTeam": infer_attacking_team(
            scores,
            [team["initialSide"] for team in teams],
            rounds,
        ),
        "round": current_round,
    }


def merge_detail(match: dict, detail: dict) -> dict:
    result = dict(match)
    listing_teams = match.get("teams", [])
    detail_teams = detail.get("teams", [])
    result["teams"] = []
    for index in range(2):
        listing = listing_teams[index] if index < len(listing_teams) else {}
        live = detail_teams[index] if index < len(detail_teams) else {}
        result["teams"].append({
            "name": live.get("name") or listing.get("name", ""),
            "seriesScore": listing.get("seriesScore"),
            "mapScore": live.get("mapScore"),
        })
    result.update({
        "map": detail.get("map", ""),
        "attackingTeam": detail.get("attackingTeam"),
        "round": detail.get("round"),
        "gameId": detail.get("gameId", ""),
    })
    return result


def fetch_html(url: str, timeout: float = 10) -> str:
    request = Request(url, headers={
        "Accept": "text/html,application/xhtml+xml",
        "Cache-Control": "no-cache",
        "User-Agent": USER_AGENT,
    })
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"VLR returned HTTP {response.status}")
        charset = response.headers.get_content_charset() or "utf-8"
        payload = response.read(MAX_HTML_BYTES + 1)
    if len(payload) > MAX_HTML_BYTES:
        raise RuntimeError(f"VLR response exceeded {MAX_HTML_BYTES} byte limit")
    return payload.decode(charset, errors="replace")


def clamp_text(value, limit: int = MAX_TEXT_CHARS) -> str:
    text = clean_text(value)
    return text[:limit]


def bounded_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def bounded_team(team) -> dict:
    team = team if isinstance(team, dict) else {}
    return {
        "name": clamp_text(team.get("name")),
        "seriesScore": bounded_int(team.get("seriesScore")),
        "mapScore": bounded_int(team.get("mapScore")),
    }


def bounded_match(match) -> dict:
    match = match if isinstance(match, dict) else {}
    url = match.get("url")
    url = url if isinstance(url, str) and VLR_MATCH_URL_RE.match(url) else ""
    teams = [bounded_team(team) for team in (match.get("teams") or [])[:2]]
    while len(teams) < 2:
        teams.append({"name": "", "seriesScore": None, "mapScore": None})
    attacking = match.get("attackingTeam")
    return {
        "id": clamp_text(match.get("id"), MAX_SHORT_TEXT_CHARS),
        "url": url,
        "event": clamp_text(match.get("event")),
        "series": clamp_text(match.get("series")),
        "date": clamp_text(match.get("date")),
        "time": clamp_text(match.get("time")),
        "eta": clamp_text(match.get("eta"), MAX_SHORT_TEXT_CHARS),
        "status": clamp_text(match.get("status"), MAX_SHORT_TEXT_CHARS),
        "teams": teams,
        "map": clamp_text(match.get("map"), MAX_SHORT_TEXT_CHARS),
        "attackingTeam": attacking if attacking in (0, 1) else None,
        "round": bounded_int(match.get("round")),
        "gameId": clamp_text(match.get("gameId"), MAX_SHORT_TEXT_CHARS),
    }


def build_snapshot(fetcher=fetch_html) -> dict:
    matches = parse_matches(fetcher(MATCHES_URL))
    vct_matches = [match for match in matches if is_top_tier_vct(match["event"], match["url"])]
    live_matches = [match for match in vct_matches if match["status"] == "live"]
    upcoming = [match for match in vct_matches if match["status"] == "upcoming"]
    live: list[dict] = []
    warnings: list[str] = []

    for match in live_matches:
        try:
            live.append(merge_detail(match, parse_detail(fetcher(match["url"]))))
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as error:
            live.append(match)
            warnings.append(f"{match['id']}: {clean_text(str(error))}")

    warning_text = ""
    if warnings:
        warning_text = "Live map details unavailable for " + ", ".join(warnings[:MAX_WARNINGS])
        warning_text = warning_text[:MAX_WARNING_CHARS]
        if len(warnings) > MAX_WARNINGS:
            suffix = f" (+{len(warnings) - MAX_WARNINGS} more)"
            warning_text = warning_text[:MAX_WARNING_CHARS - len(suffix)] + suffix

    return {
        "ok": True,
        "source": "VLR.gg",
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "live": [bounded_match(match) for match in live[:MAX_LIVE_MATCHES]],
        "upcoming": [bounded_match(match) for match in upcoming[:MAX_UPCOMING]],
        "warning": warning_text,
    }


def friendly_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        return f"VLR returned HTTP {error.code}"
    if isinstance(error, URLError):
        return "VLR connection failed: " + clean_text(str(error.reason))
    return clean_text(str(error)) or error.__class__.__name__


def main() -> int:
    try:
        snapshot = build_snapshot()
    except Exception as error:
        print(json.dumps({"ok": False, "error": friendly_error(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
