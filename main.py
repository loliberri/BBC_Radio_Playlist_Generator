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
    "genre",
    "deezer_link",
    "youtube_added",
    "youtube_video_id",
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


def load_csv_rows(path):
    """
    Load all existing CSV rows.

    Returns a list of dictionaries.
    """

    if not os.path.exists(path):
        return []

    try:

        with open(
            path,
            "r",
            encoding="utf-8",
            newline=""
        ) as f:

            reader = csv.DictReader(f)

            return list(reader)

    except Exception as e:

        print(
            f"WARNING: Could not read CSV "
            f"{path}: {e}"
        )

        return []


def load_existing_keys(path):
    """
    Load every artist/title combination already present
    in the station CSV.
    """

    existing_keys = set()

    rows = load_csv_rows(path)

    for row in rows:

        artist = row.get(
            "artist",
            ""
        )

        title = row.get(
            "title",
            ""
        )

        if artist.strip() and title.strip():

            existing_keys.add(
                make_song_key(
                    artist,
                    title
                )
            )

    return existing_keys


def ensure_csv_format(path):
    """
    Make sure an existing CSV has the new YouTube columns.

    Existing data is preserved.

    This is important because older CSV files may only have:

        date
        time
        artist
        title
        genre
        deezer_link

    The new version adds:

        youtube_added
        youtube_video_id
    """

    if not os.path.exists(path):
        return

    rows = load_csv_rows(path)

    if not rows:
        return

    # Check whether the new columns already exist.
    needs_update = False

    for row in rows:

        if "youtube_added" not in row:
            needs_update = True

        if "youtube_video_id" not in row:
            needs_update = True

    if not needs_update:
        return

    print(
        f"Updating CSV format: {path}"
    )

    for row in rows:

        if "genre" not in row:
            row["genre"] = ""

        if "deezer_link" not in row:
            row["deezer_link"] = ""

        if "youtube_added" not in row:
            row["youtube_added"] = "pending"

        if "youtube_video_id" not in row:
            row["youtube_video_id"] = ""

    with open(
        path,
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=FIELDNAMES
        )

        writer.writeheader()

        writer.writerows(rows)


def append_track_to_csv(
    station_name,
    track
):
    """
    Add a NEW song to the CSV.

    The song is written immediately.

    It does NOT depend on:
        - Deezer
        - YouTube
        - YouTube search
        - YouTube playlist

    New songs start with:

        youtube_added = pending

    Returns:

        True  = song was added
        False = song already existed
    """

    path = get_csv_path(
        station_name
    )

    # Make sure an old CSV gets the new columns.
    ensure_csv_format(path)

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

            "genre": "",

            "deezer_link": "",

            "youtube_added": "pending",

            "youtube_video_id": "",
        })

    return True


def update_csv_youtube_status(
    station_name,
    artist,
    title,
    status,
    video_id=""
):
    """
    Update the YouTube status for a song already
    stored in the CSV.

    status examples:

        pending
        yes
        failed
    """

    path = get_csv_path(
        station_name
    )

    ensure_csv_format(path)

    rows = load_csv_rows(path)

    target_key = make_song_key(
        artist,
        title
    )

    changed = False

    for row in rows:

        row_key = make_song_key(
            row.get("artist", ""),
            row.get("title", "")
        )

        if row_key == target_key:

            row["youtube_added"] = status
            row["youtube_video_id"] = video_id

            changed = True

            break

    if not changed:
        return False

    with open(
        path,
        "w",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=FIELDNAMES
        )

        writer.writeheader()

        writer.writerows(rows)

    return True


def get_pending_youtube_songs(
    station_name
):
    """
    Return songs already in the CSV that have not
    successfully been added to YouTube.
    """

    path = get_csv_path(
        station_name
    )

    ensure_csv_format(path)

    rows = load_csv_rows(path)

    pending = []

    for row in rows:

        status = (
            row.get(
                "youtube_added",
                "pending"
            )
            .strip()
            .lower()
        )

        if status != "yes":

            artist = row.get(
                "artist",
                ""
            ).strip()

            title = row.get(
                "title",
                ""
            ).strip()

            if artist and title:

                pending.append({
                    "artist": artist,
                    "title": title,
                    "time": row.get(
                        "time",
                        ""
                    ),
                })

    return pending


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
                    f"{title}"
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
        f"{playlist_title}"
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

            video_id = (
                item
                .get(
                    "contentDetails",
                    {}
                )
                .get("videoId")
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

        video_id

    or:

        None

    Raises:

        Exception

    if the YouTube API returns an error.
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
# ERROR DETECTION
# ============================================================

def is_youtube_quota_error(error):
    """
    Determine whether an exception is caused by
    YouTube API quota being exhausted.
    """

    error_text = str(
        error
    ).lower()

    quota_terms = [
        "quotaexceeded",
        "quota exceeded",
        "rate_limit_exceeded",
        "ratelimitexceeded",
        "search queries per day",
    ]

    return any(
        term in error_text
        for term in quota_terms
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
    Process one station.

    The order is:

        1. Scrape website.
        2. Check CSV.
        3. Add genuinely new songs to CSV.
        4. Retry pending YouTube songs.
        5. Search YouTube.
        6. Add videos to playlist.
        7. If quota is exhausted, stop YouTube processing.
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
    # Prepare CSV
    # --------------------------------------------------------

    csv_path = get_csv_path(
        station_name
    )

    ensure_csv_format(
        csv_path
    )

    existing_csv_keys = (
        load_existing_keys(
            csv_path
        )
    )

    # --------------------------------------------------------
    # Scrape website
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
    # FIRST:
    #
    # Add every genuinely new song to CSV.
    #
    # This happens BEFORE YouTube.
    # --------------------------------------------------------

    new_songs = 0
    already_existing = 0
    csv_failed = 0

    new_song_list = []

    for song in songs:

        artist = song.get(
            "artist",
            ""
        ).strip()

        title = song.get(
            "title",
            ""
        ).strip()

        if not artist or not title:
            continue

        key = make_song_key(
            artist,
            title
        )

        if key in existing_csv_keys:

            already_existing += 1

            continue

        print()
        print(
            f"NEW SONG: "
            f"{artist} - {title}"
        )

        try:

            added = append_track_to_csv(
                station_name,
                song
            )

            if added:

                existing_csv_keys.add(
                    key
                )

                new_songs += 1

                new_song_list.append(
                    song
                )

                print(
                    " -> Added to CSV"
                )

        except Exception as e:

            csv_failed += 1

            print(
                f" -> CSV FAILED: {e}"
            )

            with open(
                log_path,
                "a",
                encoding="utf-8"
            ) as log:

                log.write(
                    f"CSV FAILED: "
                    f"{artist} - {title}\n"
                    f"Reason: {e}\n"
                )

    # --------------------------------------------------------
    # YouTube playlist
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

        print(
            "CSV updates have been preserved."
        )

        return

    # --------------------------------------------------------
    # Get existing playlist videos
    # --------------------------------------------------------

    try:

        if playlist_was_created:

            existing_video_ids = set()

        else:

            existing_video_ids = (
                get_playlist_video_ids(
                    youtube,
                    playlist_id
                )
            )

        print(
            f"YouTube playlist contains "
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
    # Build YouTube queue.
    #
    # First retry songs that are already in CSV
    # but haven't successfully reached YouTube.
    #
    # Then process tonight's new songs.
    # --------------------------------------------------------

    pending_songs = (
        get_pending_youtube_songs(
            station_name
        )
    )

    # Remove duplicates from queue.
    youtube_queue = []
    queue_keys = set()

    for song in (
        pending_songs
        + new_song_list
    ):

        artist = song.get(
            "artist",
            ""
        ).strip()

        title = song.get(
            "title",
            ""
        ).strip()

        key = make_song_key(
            artist,
            title
        )

        if key in queue_keys:
            continue

        queue_keys.add(key)

        youtube_queue.append(
            song
        )

    # --------------------------------------------------------
    # YouTube counters
    # --------------------------------------------------------

    youtube_added = 0
    youtube_skipped = 0
    youtube_failed = 0

    quota_exhausted = False

    # --------------------------------------------------------
    # Process YouTube queue
    # --------------------------------------------------------

    print()
    print(
        f"YouTube queue: "
        f"{len(youtube_queue)} songs"
    )

    for index, song in enumerate(
        youtube_queue,
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

        print()
        print(
            f"[YouTube "
            f"{index}/{len(youtube_queue)}] "
            f"{artist} - {title}"
        )

        # ----------------------------------------------------
        # If quota was exhausted, don't make another request.
        # ----------------------------------------------------

        if quota_exhausted:

            print(
                " -> YouTube quota exhausted."
            )

            print(
                " -> Leaving song as "
                "'pending' for next run."
            )

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

            error_message = str(e)

            print(
                f"YOUTUBE FAILED: "
                f"{artist} - {title}"
            )

            print(
                f"Reason: "
                f"{error_message}"
            )

            with open(
                log_path,
                "a",
                encoding="utf-8"
            ) as log:

                log.write(
                    f"YOUTUBE FAILED: "
                    f"{artist} - {title}\n"
                    f"Reason: "
                    f"{error_message}\n"
                )

            # ------------------------------------------------
            # QUOTA EXHAUSTED
            # ------------------------------------------------

            if is_youtube_quota_error(e):

                quota_exhausted = True

                print()
                print(
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                )

                print(
                    "YOUTUBE DAILY QUOTA EXHAUSTED"
                )

                print(
                    "Stopping further YouTube "
                    "searches for this run."
                )

                print(
                    "Remaining songs will stay "
                    "pending and be retried "
                    "on the next run."
                )

                print(
                    "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                )

                # Leave this song pending.
                update_csv_youtube_status(
                    station_name,
                    artist,
                    title,
                    "pending",
                    ""
                )

            else:

                update_csv_youtube_status(
                    station_name,
                    artist,
                    title,
                    "failed",
                    ""
                )

            continue

        # ----------------------------------------------------
        # No YouTube result
        # ----------------------------------------------------

        if not video_id:

            youtube_failed += 1

            print(
                " -> No YouTube result found."
            )

            update_csv_youtube_status(
                station_name,
                artist,
                title,
                "failed",
                ""
            )

            with open(
                log_path,
                "a",
                encoding="utf-8"
            ) as log:

                log.write(
                    f"YOUTUBE FAILED: "
                    f"{artist} - {title}\n"
                    f"Reason: No YouTube result found\n"
                )

            continue

        # ----------------------------------------------------
        # Existing YouTube video
        # ----------------------------------------------------

        if video_id in existing_video_ids:

            youtube_skipped += 1

            print(
                " -> Video already exists "
                "in playlist."
            )

            update_csv_youtube_status(
                station_name,
                artist,
                title,
                "yes",
                video_id
            )

            continue

        # ----------------------------------------------------
        # Add video to playlist
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
                "playlist."
            )

            update_csv_youtube_status(
                station_name,
                artist,
                title,
                "yes",
                video_id
            )

        except Exception as e:

            youtube_failed += 1

            error_message = str(e)

            print(
                f"YOUTUBE FAILED: "
                f"{artist} - {title}"
            )

            print(
                f"Reason: "
                f"{error_message}"
            )

            with open(
                log_path,
                "a",
                encoding="utf-8"
            ) as log:

                log.write(
                    f"YOUTUBE FAILED: "
                    f"{artist} - {title}\n"
                    f"Reason: "
                    f"{error_message}\n"
                )

            if is_youtube_quota_error(e):

                quota_exhausted = True

                print(
                    "YouTube quota exhausted."
                )

                print(
                    "Stopping further YouTube "
                    "operations for this run."
                )

                update_csv_youtube_status(
                    station_name,
                    artist,
                    title,
                    "pending",
                    ""
                )

            else:

                update_csv_youtube_status(
                    station_name,
                    artist,
                    title,
                    "failed",
                    ""
                )

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

    if quota_exhausted:

        print(
            "YouTube quota:        EXHAUSTED"
        )

    else:

        print(
            "YouTube quota:        OK"
        )

    # --------------------------------------------------------
    # Log summary
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

        if quota_exhausted:

            log.write(
                "YouTube quota was exhausted. "
                "Remaining songs are pending "
                "for the next run.\n"
            )


# ============================================================
# RUN ALL STATIONS
# ============================================================

def run_daily():

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
    # Process ALL stations
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

                sys.exit(1)

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
