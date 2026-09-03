from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube"
]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",
    SCOPES
)

credentials = flow.run_local_server(
    port=0,
    access_type="offline",
    prompt="consent"
)

print()
print("Authorization successful!")
print()
print("Access token:")
print(credentials.token)
print()
print("Refresh token:")
print(credentials.refresh_token)
print()
