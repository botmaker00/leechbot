"""
Generate Spotify credentials using librespot-auth

###Spotify Authentication ->

Clone the librespot-auth repository:
git clone https://github.com/dspearson/librespot-auth
cd librespot-auth
cargo build --release

Generate credentials:
./target/release/librespot-auth

Adjust your credentials.json with the format:
{"username": "your_spotify_username", "credentials": "your_credentials_string", "type": "AUTHENTICATION_STORED_SPOTIFY_CREDENTIALS"}

### Alternative Authentication (Through this script) ->
pip install git+https://github.com/kokarare1212/librespot-python.git
"""

import logging
import pathlib
import time
import os

from librespot.zeroconf import ZeroconfServer

zs = ZeroconfServer.Builder().create()
logging.warning(
    "Transfer playback from desktop client to librespot-python via Spotify Connect in order to store session"
)

while True:
    time.sleep(1)
    if zs._ZeroconfServer__session:
        logging.warning(
            f"Grabbed {zs._ZeroconfServer__session} for {zs._ZeroconfServer__session.username()}"
        )

        cred_file = pathlib.Path("credentials.json")
        if cred_file.exists():
            new_file = pathlib.Path("spotify_credentials.json")
            os.replace(cred_file, new_file)  # rename / overwrite if exists
            logging.warning(f"Session stored in {new_file}. Now you can Ctrl+C")
            break

