import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# STATIONS
# ============================================================

STATIONS = {
    "BBC Radio 6 - Recently Played":
        "https://onlineradiobox.com/uk/bbcradio6/playlist/",

    "BBC Radio 1 - Recently Played":
        "https://onlineradiobox.com/uk/bbcdance/playlist/",

    "BBC Radio 2 - Recently Played":
        "https://onlineradiobox.com/uk/bbcradio2/playlist/",

    "BBC Radio 3 - Recently Played":
        "https://onlineradiobox.com/uk/bbcradio3/playlist/",
}


# ============================================================
# HTTP SETTINGS
# ============================================================

REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}


def create_session():
    """
    Create a requests session with automatic retries.
    """

    session = requests.Session()

    retry_strategy = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,

        backoff_factor=2,

        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],

        allowed_methods=[
            "GET"
        ],

        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry_strategy
    )

    session.mount(
        "http://",
        adapter
    )

    session.mount(
        "https://",
        adapter
    )

    session.headers.update(
        HEADERS
    )

    return session


# ============================================================
# SCRAPE ONE STATION
# ============================================================

def scrape_playlist(url):
    """
    Scrape a playlist from OnlineRadioBox.

    Returns:

        [
            {
                "title": "...",
                "artist": "...",
                "time": "..."
            }
        ]
    """

    session = create_session()

    print(
        f"Downloading playlist: {url}"
    )

    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    html = response.text

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    tracks = []

    # --------------------------------------------------------
    # Find playlist rows
    # --------------------------------------------------------

    for row in soup.select(
        "table tr"
    ):

        cells = row.find_all(
            "td"
        )

        if len(cells) != 2:
            continue

        time_cell, info_cell = cells

        time_text = (
            time_cell
            .get_text(
                strip=True
            )
        )

        info_text = (
            info_cell
            .get_text(
                strip=True
            )
        )

        if not time_text or not info_text:
            continue

        # ----------------------------------------------------
        # Artist / title
        # ----------------------------------------------------

        if " - " in info_text:

            artist_text, title_text = (
                info_text.split(
                    " - ",
                    1
                )
            )

        else:

            artist_text = ""
            title_text = info_text

        artist_text = (
            artist_text.strip()
        )

        title_text = (
            title_text.strip()
        )

        if not title_text:
            continue

        tracks.append({
            "title": title_text,
            "artist": artist_text,
            "time": time_text,
        })

    print(
        f"Found {len(tracks)} tracks"
    )

    return tracks


# ============================================================
# SCRAPE ALL STATIONS
# ============================================================

def scrape_all_stations(stations):
    """
    Scrape all stations.

    Returns:

        {
            station_name: [
                songs...
            ]
        }
    """

    results = {}

    for name, url in stations.items():

        try:

            results[name] = (
                scrape_playlist(url)
            )

        except requests.RequestException as e:

            print(
                f"FAILED TO SCRAPE "
                f"{name}: {e}"
            )

            results[name] = []

    return results


# ============================================================
# TEST MODE
# ============================================================

if __name__ == "__main__":

    all_songs = (
        scrape_all_stations(
            STATIONS
        )
    )

    for station, songs in (
        all_songs.items()
    ):

        print()
        print(
            f"=== {station} : "
            f"{len(songs)} tracks ==="
        )

        for song in songs[:20]:

            print(
                f"{song['time']} | "
                f"{song['artist']} - "
                f"{song['title']}"
            )
