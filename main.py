import os
import sys
import csv
from time import sleep
from datetime import date

from bbc6_scraper import STATIONS, scrape_playlist
from deezer_lookup import search_deezer_track

# creates an output directory
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

FIELDNAMES = ["date", "time", "artist", "title", "genre", "deezer_link"]


def get_csv_path(station_name):
    """Build the CSV file path for a given station."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return os.path.join(OUTPUT_DIR, f"{station_name}.csv")


def load_existing_keys(path):
    """Read existing rows from a station's CSV to avoid duplicate entries."""
    existing_keys = set()
    if not os.path.exists(path):
        return existing_keys
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = f"{row.get('artist','')}|{row.get('title','')}".lower().strip()
            existing_keys.add(key)
    return existing_keys


def append_track_to_csv(station_name, track):
    """Append a single track row to that station's CSV file."""
    path = get_csv_path(station_name)
    key = f"{track['artist']}|{track['title']}".lower().strip()
    existing_keys = load_existing_keys(path)
    if key in existing_keys:
        return

    file_exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "date": date.today().isoformat(),
            "time": track.get("time", ""),
            "artist": track.get("artist", ""),
            "title": track.get("title", ""),
            "genre": track.get("genre", "Unknown"),
            "deezer_link": track.get("deezer_link", ""),
        })


def process_station(station_name, url):
    """Scrape one station's playlist, enrich with Deezer info, write to its own CSV."""
    print(f"\n=== Processing {station_name} ===")

    log_path = os.path.join(OUTPUT_DIR, f"{station_name}_log.txt")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"Script started (daily) for {station_name}\n")

    try:
        songs = scrape_playlist(url)
    except Exception as e:
        print(f"Failed to scrape {station_name}: {e}")
        return []

    print(f"Scraped {len(songs)} tracks from {station_name}")

    enriched = []

    for idx, song in enumerate(songs, start=1):
        artist = song["artist"]
        title = song["title"]

        print(f"[{idx}/{len(songs)}] ({station_name}) Searching on Deezer: {artist} - {title}")

        deezer_info = search_deezer_track(artist, title)

        if deezer_info is None:
            print(" -> No Deezer match found")
            continue

        song_with_deezer = {
            **song,
            "deezer_id": deezer_info["id"],
            "deezer_link": deezer_info["link"],
            "deezer_title": deezer_info["title"],
            "deezer_artist": deezer_info["artist"],
            "genre": deezer_info.get("genre", "Unknown"),
        }

        enriched.append(song_with_deezer)
        append_track_to_csv(station_name, song_with_deezer)

        print(
            f" -> Found: {deezer_info['artist']} - {deezer_info['title']} "
            f"[{deezer_info.get('genre', 'Unknown')}]"
        )
        print(f"    Link: {deezer_info['link']}")

        sleep(0.3)

    print(f"\nSuccessfully matched {len(enriched)} tracks on Deezer for {station_name}")
    for track in enriched[:10]:
        print(
            f"{track['time']} - {track['artist']} - {track['title']} "
            f"({track.get('genre', 'Unknown')}) -> {track['deezer_link']}"
        )

    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"Script finished (daily) for {station_name}. Matched {len(enriched)} tracks.\n")

    return enriched


def run_daily():
    """Loop through every station in STATIONS and process each one separately."""
    for station_name, url in STATIONS.items():
        process_station(station_name, url)


if __name__ == "__main__":
    # optionally run a single station by name, e.g. `python script.py bbc6`
    if len(sys.argv) > 1 and sys.argv[1] in STATIONS:
        process_station(sys.argv[1], STATIONS[sys.argv[1]])
    else:
        run_daily()
