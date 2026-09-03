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


youtube = get_youtube_service()

response = youtube.channels().list(
    part="snippet",
    mine=True
).execute()

for channel in response.get("items", []):
    print("Successfully authenticated!")
    print("YouTube channel:", channel["snippet"]["title"])
