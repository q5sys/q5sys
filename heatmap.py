#!/usr/bin/env python3
"""
heatmap.py - draw every year of a GitHub user's contribution calendar into one SVG.

Writes heatmap-dark.svg and heatmap-light.svg to the current directory.
Needs a GitHub token: set TOKEN below, or the HEATMAP_TOKEN environment variable.
Uses only the Python standard library.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

LOGIN = "q5sys"
API_URL = "https://api.github.com/graphql"

# Paste your token here for local runs. Leave it empty in the copy you commit;
# the GitHub Action will supply it through HEATMAP_TOKEN instead.
TOKEN = "REDACTED"

# Layout, in pixels
CELL = 10                                   # size of one day square
GAP = 3                                     # space between squares
STEP = CELL + GAP                           # distance from one square to the next
LEFT = 32                                   # room for the Mon/Wed/Fri labels
GRID_TOP = 40                               # where the squares start inside a year block
BLOCK_HEIGHT = GRID_TOP + 7 * STEP + 24     # height of one year, including space below it
HEADER_HEIGHT = 56                          # all-time total at the very top
WIDTH = LEFT + 54 * STEP                    # a calendar year can touch 54 week columns

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

COLORS = {
    "dark": {
        "NONE": "#161b22",
        "FIRST_QUARTILE": "#0e4429",
        "SECOND_QUARTILE": "#006d32",
        "THIRD_QUARTILE": "#26a641",
        "FOURTH_QUARTILE": "#39d353",
    },
    "light": {
        "NONE": "#ebedf0",
        "FIRST_QUARTILE": "#9be9a8",
        "SECOND_QUARTILE": "#40c463",
        "THIRD_QUARTILE": "#30a14e",
        "FOURTH_QUARTILE": "#216e39",
    },
}

TEXT_COLORS = {
    "dark": {"main": "#e6edf3", "muted": "#9198a1", "rule": "#30363d"},
    "light": {"main": "#1f2328", "muted": "#59636e", "rule": "#d1d9e0"},
}

YEARS_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionYears
    }
  }
}
"""

CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            weekday
            contributionCount
            contributionLevel
          }
        }
      }
    }
  }
}
"""


def get_token():
    """Use TOKEN from the top of this file if set, otherwise the HEATMAP_TOKEN environment variable."""
    if TOKEN:
        return TOKEN

    token = os.environ.get("HEATMAP_TOKEN")
    if not token:
        print("No token: set TOKEN in heatmap.py or the HEATMAP_TOKEN environment variable", file=sys.stderr)
        sys.exit(1)
    return token


def run_query(token, query, variables):
    """POST one GraphQL query to api.github.com and return the parsed JSON."""
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")

    request = urllib.request.Request(API_URL, data=body, method="POST")
    request.add_header("Authorization", "bearer " + token)
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "heatmap.py")

    with urllib.request.urlopen(request) as response:
        result = json.loads(response.read().decode("utf-8"))

    if "errors" in result:
        print(json.dumps(result["errors"], indent=2), file=sys.stderr)
        sys.exit(1)

    return result["data"]


def get_contribution_years(token, login):
    """Return the list of years that have contributions, newest first."""
    data = run_query(token, YEARS_QUERY, {"login": login})
    years = data["user"]["contributionsCollection"]["contributionYears"]
    years.sort(reverse=True)
    return years


def get_year_calendar(token, login, year):
    """Return the calendar (total + weeks/days) for Jan 1 - Dec 31 of one year.
    The current year stops at right now."""
    start = f"{year}-01-01T00:00:00Z"

    now = datetime.now(timezone.utc)
    if year == now.year:
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        end = f"{year}-12-31T23:59:59Z"

    variables = {"login": login, "from": start, "to": end}
    data = run_query(token, CALENDAR_QUERY, variables)
    return data["user"]["contributionsCollection"]["contributionCalendar"]


def level_to_color(level, theme):
    """Map GitHub's contribution level to a hex color for 'dark' or 'light'."""
    return COLORS[theme][level]


def render_header(grand_total, first_year):
    """Return the SVG fragment for the top line, e.g. "12,345 contributions since 2010"."""
    lines = []
    lines.append(
        f'<text x="0" y="26">'
        f'<tspan class="total">{grand_total:,}</tspan>'
        f'<tspan class="count" dx="8">contributions since {first_year}</tspan>'
        f'</text>'
    )
    lines.append(f'<line x1="0" y1="40" x2="{WIDTH}" y2="40" class="rule"/>')
    return "\n".join(lines)


def render_year(calendar, year, y_offset, theme):
    """Return the SVG fragment for one year: header, labels, and squares."""
    lines = []
    lines.append(f'<g transform="translate(0,{y_offset})">')

    # Header, e.g. "2026  1,234 contributions"
    total = calendar["totalContributions"]
    lines.append(
        f'<text x="0" y="16">'
        f'<tspan class="year">{year}</tspan>'
        f'<tspan class="count" dx="10">{total:,} contributions</tspan>'
        f'</text>'
    )

    # Day labels on the left
    for row, name in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        y = GRID_TOP + row * STEP + CELL - 1
        lines.append(f'<text x="0" y="{y}" class="label">{name}</text>')

    # One column per week
    last_month = 0
    for column, week in enumerate(calendar["weeks"]):
        x = LEFT + column * STEP
        days = week["contributionDays"]

        # Month label goes above the first week that starts in a new month
        month = int(days[0]["date"][5:7])
        if month != last_month:
            label_y = GRID_TOP - 6
            lines.append(f'<text x="{x}" y="{label_y}" class="label">{MONTHS[month - 1]}</text>')
            last_month = month

        # One square per day, row is the weekday (0 = Sunday)
        for day in days:
            y = GRID_TOP + day["weekday"] * STEP
            color = level_to_color(day["contributionLevel"], theme)
            lines.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{color}"/>'
            )

    lines.append("</g>")
    return "\n".join(lines)


def render_document(fragments, total_height, theme):
    """Wrap all year fragments in the <svg> root element."""
    main_color = TEXT_COLORS[theme]["main"]
    muted_color = TEXT_COLORS[theme]["muted"]
    rule_color = TEXT_COLORS[theme]["rule"]

    lines = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{WIDTH}" height="{total_height}" '
        f'viewBox="0 0 {WIDTH} {total_height}">'
    )
    lines.append("<style>")
    lines.append('text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }')
    lines.append(f".total {{ font-size: 24px; font-weight: 600; fill: {main_color}; }}")
    lines.append(f".rule {{ stroke: {rule_color}; stroke-width: 1; }}")
    lines.append(f".year {{ font-size: 15px; font-weight: 600; fill: {main_color}; }}")
    lines.append(f".count {{ font-size: 12px; fill: {muted_color}; }}")
    lines.append(f".label {{ font-size: 10px; fill: {muted_color}; }}")
    lines.append("</style>")
    lines.extend(fragments)
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def write_file(path, text):
    """Write the SVG to disk."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    token = get_token()
    years = get_contribution_years(token, LOGIN)

    # Fetch every year once
    calendars = []
    for year in years:
        print(f"Fetching {year}")
        calendars.append(get_year_calendar(token, LOGIN, year))

    # All-time total across every year
    grand_total = 0
    for calendar in calendars:
        grand_total += calendar["totalContributions"]
    first_year = years[-1]
    print(f"Total: {grand_total:,} contributions since {first_year}")

    total_height = HEADER_HEIGHT + len(years) * BLOCK_HEIGHT

    # Draw it once per theme
    for theme in ["dark", "light"]:
        fragments = []
        fragments.append(render_header(grand_total, first_year))
        for index, year in enumerate(years):
            y_offset = HEADER_HEIGHT + index * BLOCK_HEIGHT
            fragments.append(render_year(calendars[index], year, y_offset, theme))

        svg = render_document(fragments, total_height, theme)
        path = f"heatmap-{theme}.svg"
        write_file(path, svg)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
