import requests
from bs4 import BeautifulSoup

import os

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube"
]


def get_youtube_service():
    credentials = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=YOUTUBE_SCOPES,
    )

    credentials.refresh(Request())

    return build(
        "youtube",
        "v3",
        credentials=credentials
    )

# Dictionary of station name -> playlist URL
STATIONS = {
    "BBC Radio 6 - Recently Played": "https://onlineradiobox.com/uk/bbcradio6/playlist/",
    "BBC Radio 1 - Recently Played": "https://onlineradiobox.com/uk/bbcdance/playlist/",
    "BBC Radio 2 - Recently Played": "https://onlineradiobox.com/uk/bbcradio2/playlist/",
    "BBC Radio 3 - Recently Played": "https://onlineradiobox.com/uk/bbcradio3/playlist/",
}


def scrape_playlist(url):
    """
    Scrape a playlist from OnlineRadioBox for a given station URL.
    Returns a list of dicts: {"title": ..., "artist": ..., "time": ...}.
    """

    # Sends a HTML get request to website
    resp = requests.get(url)

    # Raises an error if the request has failed
    resp.raise_for_status()

    # Gives raw HTML as a string
    html = resp.text

    # Parses the HTML
    soup = BeautifulSoup(html, "html.parser")

    # Creates an empty list to store tracks
    tracks = []

    # Format of table is as follows:
    # | time | "Artist - Title" |
    # Loop through each table row on the website
    for row in soup.select("table tr"):

        # Find all table cells in that row
        cells = row.find_all("td")

        # 2 cells are expected, if not, skip
        if len(cells) != 2:
            continue  # skip header or weird rows

        # Assign time to the 1st cell, info to the 2nd cell
        time_cell, info_cell = cells

        # Extract info and exclude whitespace
        time_text = time_cell.get_text(strip=True)
        info_text = info_cell.get_text(strip=True)

        # If the cell is empty, ignore it
        if not time_text or not info_text:
            continue

        # info_text typically looks like "Artist - Song Title"
        if " - " in info_text:
            artist_text, title_text = info_text.split(" - ", 1)
        else:
            artist_text = ""
            title_text = info_text

        artist_text = artist_text.strip()
        title_text = title_text.strip()

        if not title_text:
            continue

        tracks.append(
            {
                "title": title_text,
                "artist": artist_text,
                "time": time_text,
            }
        )

    return tracks


def scrape_all_stations(stations):
    """
    Loop through a dict of {station_name: url} and scrape each one.
    Returns a dict of {station_name: list_of_tracks}.
    """
    results = {}
    for name, url in stations.items():
        try:
            results[name] = scrape_playlist(url)
        except requests.RequestException as e:
            print(f"Failed to scrape {name}: {e}")
            results[name] = []
    return results


# Only run if executed directly
if __name__ == "__main__":

    all_songs = scrape_all_stations(STATIONS)

    for station, songs in all_songs.items():
        print(f"\n=== {station} : {len(songs)} tracks ===")
        for song in songs[:20]:
            print(f"{song['time']} - {song['artist']} – {song['title']}")
