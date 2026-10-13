"""P4-05 spike: log in to Spotify with PKCE, search one track, play it on the open desktop app."""

import os
from pathlib import Path

import spotipy
from dotenv import load_dotenv
from spotipy.cache_handler import CacheFileHandler
from spotipy.oauth2 import SpotifyPKCE

load_dotenv()

SCOPE = "user-modify-playback-state user-read-playback-state"
TOKEN_CACHE = Path(".secrets") / "spotify_token.json"  # .secrets/ is git-ignored


def main() -> None:
    TOKEN_CACHE.parent.mkdir(exist_ok=True)
    auth = SpotifyPKCE(
        client_id=os.environ["SPOTIPY_CLIENT_ID"],
        redirect_uri=os.environ["SPOTIPY_REDIRECT_URI"],
        scope=SCOPE,
        cache_handler=CacheFileHandler(cache_path=str(TOKEN_CACHE)),
    )
    sp = spotipy.Spotify(auth_manager=auth)

    devices = sp.devices()["devices"]
    print("Devices:", [d["name"] for d in devices])
    if not devices:
        print("No active device. Open Spotify on the laptop, play any song for a second, pause, run again.")
        return

    found = sp.search(q="Blinding Lights", type="track", limit=1)["tracks"]["items"]
    if not found:
        print("Search returned nothing.")
        return
    track = found[0]
    print("Playing:", track["name"], "-", track["artists"][0]["name"])
    sp.start_playback(device_id=devices[0]["id"], uris=[track["uri"]])


if __name__ == "__main__":
    main()