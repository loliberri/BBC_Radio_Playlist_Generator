import os
import sys
import csv
from time import sleep
from datetime import date

from bbc6_scraper import STATIONS, scrape_playlist
from deezer_lookup import search_deezer_track

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# ============================================================
# YOUTUBE SETTINGS
# ============================================================

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube"
]


# ============================================================
# YOUTUBE AUTHENTICATION
# ============================================================

def get_youtube_service():
    """Authenticate with YouTube using GitHub Secrets."""

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


# ============================================================
# OUTPUT SETTINGS
# ============================================================

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__),
    "output"
)

FIELDNAMES = [
    "date",
    "time",
    "artist",
    "title",
    "genre",
    "deezer_link"
]


# ============================================================
# CSV FUNCTIONS
# ============================================================

def get_csv_path(station_name):
    """Build the CSV file path for a station."""

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    return os.path.join(
        OUTPUT_DIR,
        f"{station_name}.csv"
    )


def load_existing_keys(path):
    """
    Read existing songs from the CSV.

    This is used to determine whether a song is new.
    """

    existing_keys = set()

    if not os.path.exists(path):
        return existing_keys

    with open(
        path,
        "r",
        encoding="utf-8",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            key = (
                f"{row.get('artist', '')}|"
                f"{row.get('title', '')}"
            ).lower().strip()

            existing_keys.add(key)

    return existing_keys


def append_track_to_csv(station_name, track):
    """
    Add a new track to the station CSV.

    Returns:
        True  -> song was new and added
        False -> song already existed
    """

    path = get_csv_path(station_name)

    key = (
        f"{track['artist']}|"
        f"{track['title']}"
    ).lower().strip()

    existing_keys = load_existing_keys(path)

    if key in existing_keys:
        return False

    file_exists = os.path.exists(path)

    with open(
        path,
        "a",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=FIELDNAMES
        )

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

    return True


# ============================================================
# YOUTUBE PLAYLIST FUNCTIONS
# ============================================================

def get_or_create_playlist(youtube, station_name):
    """
    Find a YouTube playlist matching the station name.

    If it does not exist, create it.

    Returns:
        playlist_id, playlist_was_created
    """

    playlist_title = station_name

    print(
        f"Checking YouTube playlist: "
        f"{playlist_title}"
    )

    request = youtube.playlists().list(
        part="snippet",
        mine=True,
        maxResults=50
    )

    while request:

        response = request.execute()

        for playlist in response.get(
            "items",
            []
        ):

            title = playlist[
                "snippet"
            ][
                "title"
            ]

            if title.lower() == playlist_title.lower():

                playlist_id = playlist["id"]

                print(
                    f" -> Found playlist: "
                    f"{title} ({playlist_id})"
                )

                return playlist_id, False

        request = youtube.playlists().list_next(
            request,
            response
        )

    # --------------------------------------------------------
    # Playlist doesn't exist
    # --------------------------------------------------------

    print(
        f" -> Creating playlist: "
        f"{playlist_title}"
    )

    playlist_body = {
        "snippet": {
            "title": playlist_title,
            "description": (
                f"Songs played on {station_name}, "
                "automatically generated by the "
                "radio scraper."
            )
        },
        "status": {
            "privacyStatus": "public"
        }
    }

    response = youtube.playlists().insert(
        part="snippet,status",
        body=playlist_body
    ).execute()

    playlist_id = response["id"]

    print(
        f" -> Created playlist: "
        f"{playlist_title} ({playlist_id})"
    )

    return playlist_id, True


def get_playlist_video_ids(youtube, playlist_id):
    """Get all video IDs currently in a playlist."""

    video_ids = set()

    request = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=playlist_id,
        maxResults=50
    )

    while request:

        response = request.execute()

        for item in response.get(
            "items",
            []
        ):

            video_ids.add(
                item[
                    "contentDetails"
                ][
                    "videoId"
                ]
            )

        request = youtube.playlistItems().list_next(
            request,
            response
        )

    return video_ids


def search_youtube_video(
    youtube,
    artist,
    title
):
    """
    Search YouTube for the best matching song.

    Returns:
        video ID or None
    """

    query = f"{artist} {title}"

    print(
        f"  Searching YouTube: "
        f"{query}"
    )

    response = youtube.search().list(
        part="snippet",
        q=query,
        type="video",
        videoCategoryId="10",
        maxResults=1
    ).execute()

    items = response.get(
        "items",
        []
    )

    if not items:

        print(
            "  -> No YouTube result found"
        )

        return None

    video_id = items[0][
        "id"
    ][
        "videoId"
    ]

    video_title = items[0][
        "snippet"
    ][
        "title"
    ]

    print(
        f"  -> Found: "
        f"{video_title}"
    )

    return video_id


def add_video_to_playlist(
    youtube,
    playlist_id,
    video_id
):
    """Add a YouTube video to a playlist."""

    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id
            }
        }
    }

    youtube.playlistItems().insert(
        part="snippet",
        body=body
    ).execute()


# ============================================================
# PROCESS ONE STATION
# ============================================================

def process_station(
    youtube,
    station_name,
    url
):
    """
    Scrape one station, add new songs to CSV,
    and add new songs to its YouTube playlist.
    """

    print()
    print("=" * 70)
    print(
        f"PROCESSING STATION: "
        f"{station_name}"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Log
    # --------------------------------------------------------

    log_path = os.path.join(
        OUTPUT_DIR,
        f"{station_name}_log.txt"
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    with open(
        log_path,
        "a",
        encoding="utf-8"
    ) as log:

        log.write(
            f"Script started for "
            f"{station_name}\n"
        )

    # --------------------------------------------------------
    # Scrape
    # --------------------------------------------------------

    try:

        songs = scrape_playlist(url)

    except Exception as e:

        print(
            f"Failed to scrape "
            f"{station_name}: {e}"
        )

        return

    print(
        f"Scraped {len(songs)} tracks "
        f"from {station_name}"
    )

    # --------------------------------------------------------
    # YouTube playlist
    # --------------------------------------------------------

    try:

        playlist_id, playlist_was_created = (
            get_or_create_playlist(
                youtube,
                station_name
            )
        )

    except Exception as e:

        print(
            f"Failed to access YouTube "
            f"playlist for {station_name}: {e}"
        )

        return

    # --------------------------------------------------------
    # Get videos already in playlist
    # --------------------------------------------------------

    if playlist_was_created:

        existing_video_ids = set()

        print(
            "Playlist was just created, "
            "so it is empty."
        )

    else:

        try:

            existing_video_ids = (
                get_playlist_video_ids(
                    youtube,
                    playlist_id
                )
            )

            print(
                f"Playlist contains "
                f"{len(existing_video_ids)} "
                f"videos."
            )

        except Exception as e:

            print(
                f"Could not read playlist "
                f"contents: {e}"
            )

            return

    # --------------------------------------------------------
    # Load existing CSV songs once
    # --------------------------------------------------------

    csv_path = get_csv_path(
        station_name
    )

    existing_csv_keys = (
        load_existing_keys(
            csv_path
        )
    )

    # --------------------------------------------------------
    # Counters
    # --------------------------------------------------------

    new_songs = 0
    already_existing = 0
    youtube_added = 0
    youtube_skipped = 0
    failed = 0

    # --------------------------------------------------------
    # Process scraped songs
    # --------------------------------------------------------

    for index, song in enumerate(
        songs,
        start=1
    ):

        artist = song.get(
            "artist",
            ""
        ).strip()

        title = song.get(
            "title",
            ""
        ).strip()

        if not artist or not title:

            print(
                f"[{index}/{len(songs)}] "
                "Skipping empty artist/title"
            )

            continue

        key = (
            f"{artist}|{title}"
        ).lower().strip()

        # ----------------------------------------------------
        # Existing song
        # ----------------------------------------------------

        if key in existing_csv_keys:

            already_existing += 1

            continue

        # ----------------------------------------------------
        # New song
        # ----------------------------------------------------

        print()
        print(
            f"[{index}/{len(songs)}] "
            f"NEW SONG: "
            f"{artist} - {title}"
        )

        # ----------------------------------------------------
        # Deezer lookup
        # ----------------------------------------------------

        try:

            deezer_info = (
                search_deezer_track(
                    artist,
                    title
                )
            )

        except Exception as e:

            print(
                f" -> Deezer lookup failed: "
                f"{e}"
            )

            failed += 1
            continue

        if deezer_info is None:

            print(
                " -> No Deezer match found"
            )

            failed += 1
            continue

        # ----------------------------------------------------
        # Enrich song
        # ----------------------------------------------------

        song_with_deezer = {
            **song,
            "deezer_id": deezer_info["id"],
            "deezer_link": deezer_info["link"],
            "deezer_title": deezer_info["title"],
            "deezer_artist": deezer_info["artist"],
            "genre": deezer_info.get(
                "genre",
                "Unknown"
            ),
        }

        # ----------------------------------------------------
        # Add to CSV
        # ----------------------------------------------------

        try:

            with open(
                csv_path,
                "a",
                encoding="utf-8",
                newline=""
            ) as f:

                writer = csv.DictWriter(
                    f,
                    fieldnames=FIELDNAMES
                )

                if not os.path.exists(
                    csv_path
                ) or os.path.getsize(
                    csv_path
                ) == 0:

                    writer.writeheader()

                writer.writerow({
                    "date": date.today().isoformat(),
                    "time": song_with_deezer.get(
                        "time",
                        ""
                    ),
                    "artist": song_with_deezer.get(
                        "artist",
                        ""
                    ),
                    "title": song_with_deezer.get(
                        "title",
                        ""
                    ),
                    "genre": song_with_deezer.get(
                        "genre",
                        "Unknown"
                    ),
                    "deezer_link": song_with_deezer.get(
                        "deezer_link",
                        ""
                    ),
                })

            existing_csv_keys.add(
                key
            )

            new_songs += 1

            print(
                f" -> Added to CSV"
            )

        except Exception as e:

            print(
                f" -> Failed to write CSV: "
                f"{e}"
            )

            failed += 1
            continue

        # ----------------------------------------------------
        # Search YouTube
        # ----------------------------------------------------

        try:

            video_id = search_youtube_video(
                youtube,
                artist,
                title
            )

        except Exception as e:

            print(
                f" -> YouTube search failed: "
                f"{e}"
            )

            failed += 1
            continue

        if not video_id:

            failed += 1
            continue

        # ----------------------------------------------------
        # Check if video is already in playlist
        # ----------------------------------------------------

        if video_id in existing_video_ids:

            print(
                " -> Already in YouTube playlist"
            )

            youtube_skipped += 1

            continue

        # ----------------------------------------------------
        # Add to YouTube playlist
        # ----------------------------------------------------

        try:

            add_video_to_playlist(
                youtube,
                playlist_id,
                video_id
            )

            existing_video_ids.add(
                video_id
            )

            youtube_added += 1

            print(
                " -> ADDED to YouTube playlist"
            )

        except Exception as e:

            print(
                f" -> Failed to add to "
                f"YouTube playlist: {e}"
            )

            failed += 1

        # ----------------------------------------------------
        # Small delay
        # ----------------------------------------------------

        sleep(0.3)

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(
        f"FINISHED: {station_name}"
    )
    print("=" * 70)

    print(
        f"Scraped:              {len(songs)}"
    )

    print(
        f"Already in CSV:       {already_existing}"
    )

    print(
        f"New songs:            {new_songs}"
    )

    print(
        f"Added to YouTube:     {youtube_added}"
    )

    print(
        f"Already on YouTube:   {youtube_skipped}"
    )

    print(
        f"Failed:               {failed}"
    )

    # --------------------------------------------------------
    # Log
    # --------------------------------------------------------

    with open(
        log_path,
        "a",
        encoding="utf-8"
    ) as log:

        log.write(
            f"Script finished for "
            f"{station_name}. "
            f"New songs: {new_songs}, "
            f"YouTube added: {youtube_added}, "
            f"Failed: {failed}\n"
        )


# ============================================================
# RUN ALL STATIONS
# ============================================================

def run_daily():
    """
    Process every station in STATIONS.
    """

    # --------------------------------------------------------
    # Authenticate once
    # --------------------------------------------------------

    print(
        "Authenticating with YouTube..."
    )

    try:

        youtube = get_youtube_service()

    except Exception as e:

        print(
            f"YouTube authentication failed: "
            f"{e}"
        )

        return

    print(
        "Successfully authenticated "
        "with YouTube."
    )

    # --------------------------------------------------------
    # Process every station
    # --------------------------------------------------------

    for station_name, url in STATIONS.items():

        process_station(
            youtube,
            station_name,
            url
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Optional single-station mode
    #
    # Example:
    #
    # python main.py bbc6
    #
    # --------------------------------------------------------

    if (
        len(sys.argv) > 1
        and sys.argv[1] in STATIONS
    ):

        print(
            f"Running only station: "
            f"{sys.argv[1]}"
        )

        try:

            youtube = get_youtube_service()

            process_station(
                youtube,
                sys.argv[1],
                STATIONS[sys.argv[1]]
            )

        except Exception as e:

            print(
                f"Error: {e}"
            )

    else:

        run_daily()
