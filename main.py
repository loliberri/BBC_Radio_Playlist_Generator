import os
import sys
import csv
from time import sleep
from datetime import date

from bbc6_scraper import STATIONS, scrape_playlist

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
]


# ============================================================
# YOUTUBE AUTHENTICATION
# ============================================================

def get_youtube_service():
    """
    Authenticate with YouTube using GitHub Secrets.
    """

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
# CSV FUNCTIONS
# ============================================================

def get_csv_path(station_name):
    """
    Return the CSV path for a station.
    """

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    return os.path.join(
        OUTPUT_DIR,
        f"{station_name}.csv"
    )


def make_song_key(artist, title):
    """
    Create a normalized key used to identify duplicate songs.
    """

    artist = (artist or "").strip().lower()
    title = (title or "").strip().lower()

    return f"{artist}|{title}"


def load_existing_keys(path):
    """
    Load every artist/title combination already present
    in the station CSV.
    """

    existing_keys = set()

    if not os.path.exists(path):
        return existing_keys

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
            newline=""
        ) as f:

            reader = csv.DictReader(f)

            for row in reader:

                artist = row.get("artist", "")
                title = row.get("title", "")

                key = make_song_key(
                    artist,
                    title
                )

                if artist.strip() and title.strip():
                    existing_keys.add(key)

    except Exception as e:

        print(
            f"WARNING: Could not read CSV "
            f"{path}: {e}"
        )

    return existing_keys


def append_track_to_csv(
    station_name,
    track
):
    """
    Add a song to the CSV.

    This function does NOT depend on YouTube
    or any external music database.

    Returns:
        True  = song was added
        False = song already existed
    """

    path = get_csv_path(
        station_name
    )

    artist = track.get(
        "artist",
        ""
    ).strip()

    title = track.get(
        "title",
        ""
    ).strip()

    if not artist or not title:
        return False

    key = make_song_key(
        artist,
        title
    )

    existing_keys = load_existing_keys(
        path
    )

    if key in existing_keys:
        return False

    file_exists = os.path.exists(
        path
    )

    file_empty = (
        not file_exists
        or os.path.getsize(path) == 0
    )

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

        if file_empty:
            writer.writeheader()

        writer.writerow({
            "date": date.today().isoformat(),
            "time": track.get(
                "time",
                ""
            ),
            "artist": artist,
            "title": title,
        })

    return True


# ============================================================
# YOUTUBE PLAYLIST FUNCTIONS
# ============================================================

def get_or_create_playlist(
    youtube,
    station_name
):
    """
    Find the YouTube playlist matching the
    station name.

    If it doesn't exist, create it.

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

            title = (
                playlist
                .get("snippet", {})
                .get("title", "")
            )

            if (
                title.lower()
                == playlist_title.lower()
            ):

                playlist_id = playlist["id"]

                print(
                    f" -> Found playlist: "
                    f"{title} "
                    f"({playlist_id})"
                )

                return (
                    playlist_id,
                    False
                )

        request = (
            youtube.playlists()
            .list_next(
                request,
                response
            )
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
                f"Songs played on "
                f"{station_name}, "
                "automatically generated "
                "by the radio scraper."
            )
        },
        "status": {
            "privacyStatus": "public"
        }
    }

    response = (
        youtube.playlists()
        .insert(
            part="snippet,status",
            body=playlist_body
        )
        .execute()
    )

    playlist_id = response["id"]

    print(
        f" -> Created playlist: "
        f"{playlist_title} "
        f"({playlist_id})"
    )

    return (
        playlist_id,
        True
    )


def get_playlist_video_ids(
    youtube,
    playlist_id
):
    """
    Get every YouTube video currently
    contained in a playlist.
    """

    video_ids = set()

    request = (
        youtube.playlistItems()
        .list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50
        )
    )

    while request:

        response = request.execute()

        for item in response.get(
            "items",
            []
        ):

            content = item.get(
                "contentDetails",
                {}
            )

            video_id = content.get(
                "videoId"
            )

            if video_id:
                video_ids.add(
                    video_id
                )

        request = (
            youtube.playlistItems()
            .list_next(
                request,
                response
            )
        )

    return video_ids


def search_youtube_video(
    youtube,
    artist,
    title
):
    """
    Search YouTube for a music video.

    Returns:
        video ID
        or None if no result exists.
    """

    query = f"{artist} {title}"

    print(
        f"  Searching YouTube: "
        f"{query}"
    )

    response = (
        youtube.search()
        .list(
            part="snippet",
            q=query,
            type="video",
            videoCategoryId="10",
            maxResults=1
        )
        .execute()
    )

    items = response.get(
        "items",
        []
    )

    if not items:

        print(
            "  -> No YouTube result found"
        )

        return None

    first_item = items[0]

    video_id = (
        first_item
        .get("id", {})
        .get("videoId")
    )

    video_title = (
        first_item
        .get("snippet", {})
        .get("title", "")
    )

    if not video_id:

        print(
            "  -> YouTube result "
            "did not contain a video ID"
        )

        return None

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
    """
    Add a YouTube video to a playlist.
    """

    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id
            }
        }
    }

    (
        youtube
        .playlistItems()
        .insert(
            part="snippet",
            body=body
        )
        .execute()
    )


# ============================================================
# PROCESS ONE STATION
# ============================================================

def process_station(
    youtube,
    station_name,
    url
):
    """
    Scrape one station.

    For each song:

    1. Check CSV.
    2. If already present, ignore it.
    3. If new, immediately add it to CSV.
    4. Search YouTube.
    5. Add YouTube video to playlist.
    6. Continue even if YouTube fails.
    """

    print()
    print("=" * 70)
    print(
        f"PROCESSING STATION: "
        f"{station_name}"
    )
    print("=" * 70)

    log_path = os.path.join(
        OUTPUT_DIR,
        f"{station_name}_log.txt"
    )

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Start log
    # --------------------------------------------------------

    with open(
        log_path,
        "a",
        encoding="utf-8"
    ) as log:

        log.write(
            f"\nScript started for "
            f"{station_name}\n"
        )

    # --------------------------------------------------------
    # Scrape station
    # --------------------------------------------------------

    try:

        songs = scrape_playlist(
            url
        )

    except Exception as e:

        message = (
            f"FAILED TO SCRAPE "
            f"{station_name}: {e}"
        )

        print(message)

        with open(
            log_path,
            "a",
            encoding="utf-8"
        ) as log:

            log.write(
                message + "\n"
            )

        return

    print(
        f"Scraped {len(songs)} tracks "
        f"from {station_name}"
    )

    # --------------------------------------------------------
    # Get/create YouTube playlist
    # --------------------------------------------------------

    try:

        (
            playlist_id,
            playlist_was_created
        ) = get_or_create_playlist(
            youtube,
            station_name
        )

    except Exception as e:

        message = (
            f"FAILED TO ACCESS YOUTUBE "
            f"PLAYLIST FOR "
            f"{station_name}: {e}"
        )

        print(message)

        with open(
            log_path,
            "a",
            encoding="utf-8"
        ) as log:

            log.write(
                message + "\n"
            )

        return

    # --------------------------------------------------------
    # Get existing YouTube videos
    # --------------------------------------------------------

    if playlist_was_created:

        existing_video_ids = set()

        print(
            "Playlist was just created."
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

            message = (
                f"FAILED TO READ YOUTUBE "
                f"PLAYLIST FOR "
                f"{station_name}: {e}"
            )

            print(message)

            with open(
                log_path,
                "a",
                encoding="utf-8"
            ) as log:

                log.write(
                    message + "\n"
                )

            return

    # --------------------------------------------------------
    # Load CSV once
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
    youtube_failed = 0

    csv_failed = 0

    # --------------------------------------------------------
    # Process songs
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

        # ----------------------------------------------------
        # Ignore invalid rows
        # ----------------------------------------------------

        if not artist or not title:

            print(
                f"[{index}/{len(songs)}] "
                "Skipping empty artist/title"
            )

            continue

        key = make_song_key(
            artist,
            title
        )

        # ----------------------------------------------------
        # Already in CSV
        # ----------------------------------------------------

        if key in existing_csv_keys:

            already_existing += 1

            continue

        # ----------------------------------------------------
        # NEW SONG
        # ----------------------------------------------------

        print()
        print(
            f"[{index}/{len(songs)}] "
            f"NEW SONG: "
            f"{artist} - {title}"
        )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Add to CSV BEFORE YouTube.
        #
        # This means YouTube failures can never prevent
        # the song being recorded.
        # ----------------------------------------------------

        try:

            csv_added = append_track_to_csv(
                station_name,
                song
            )

            if csv_added:

                existing_csv_keys.add(
                    key
                )

                new_songs += 1

                print(
                    " -> Added to CSV"
                )

            else:

                print(
                    " -> Song already existed "
                    "in CSV"
                )

                existing_csv_keys.add(
                    key
                )

                already_existing += 1

                continue

        except Exception as e:

            csv_failed += 1

            print(
                f" -> FAILED TO WRITE CSV: "
                f"{e}"
            )

            # Do not attempt YouTube if the CSV
            # could not be written.

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

            youtube_failed += 1

            print(
                f" -> YouTube search failed: "
                f"{e}"
            )

            # IMPORTANT:
            # Song remains safely stored in CSV.

            continue

        # ----------------------------------------------------
        # No YouTube result
        # ----------------------------------------------------

        if not video_id:

            youtube_failed += 1

            print(
                " -> No suitable YouTube "
                "video found"
            )

            continue

        # ----------------------------------------------------
        # YouTube duplicate check
        # ----------------------------------------------------

        if video_id in existing_video_ids:

            youtube_skipped += 1

            print(
                " -> Already in YouTube "
                "playlist"
            )

            continue

        # ----------------------------------------------------
        # Add YouTube video
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
                " -> ADDED to YouTube "
                "playlist"
            )

        except Exception as e:

            youtube_failed += 1

            print(
                f" -> FAILED to add to "
                f"YouTube playlist: {e}"
            )

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
        f"CSV failures:         {csv_failed}"
    )

    print(
        f"Added to YouTube:     {youtube_added}"
    )

    print(
        f"Already on YouTube:   {youtube_skipped}"
    )

    print(
        f"YouTube failures:     {youtube_failed}"
    )

    # --------------------------------------------------------
    # Write log
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
            f"YouTube added: "
            f"{youtube_added}, "
            f"YouTube failures: "
            f"{youtube_failed}, "
            f"CSV failures: "
            f"{csv_failed}\n"
        )


# ============================================================
# RUN ALL STATIONS
# ============================================================

def run_daily():
    """
    Process every station in STATIONS.
    """

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
    # Process all stations
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
    # python main.py "BBC Radio 6 - Recently Played"
    #
    # --------------------------------------------------------

    if len(sys.argv) > 1:

        station_name = sys.argv[1]

        if station_name in STATIONS:

            print(
                f"Running only station: "
                f"{station_name}"
            )

            try:

                youtube = (
                    get_youtube_service()
                )

                process_station(
                    youtube,
                    station_name,
                    STATIONS[
                        station_name
                    ]
                )

            except Exception as e:

                print(
                    f"Error: {e}"
                )

        else:

            print(
                "Unknown station."
            )

            print(
                "Available stations:"
            )

            for station in STATIONS:
                print(
                    f" - {station}"
                )

            sys.exit(1)

    else:

        run_daily()
