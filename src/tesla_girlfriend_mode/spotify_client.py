"""Thin wrapper around the Spotify Web API — the OWNER's account.

Honesty note: Tesla's Fleet API cannot choose a playlist inside the car's
own Spotify app (its media commands are only play/pause/next/volume).
So Girlfriend Mode starts her mix through the owner's Spotify account on
their *active Spotify device* — in practice their phone, which is already
connected to the car for audio. Nothing here touches the car's Spotify
app, and we never claim it does.
"""
from __future__ import annotations

import requests

API_BASE = "https://api.spotify.com/v1"


class SpotifyError(Exception):
    """Human-readable Spotify failure — never a raw stack trace."""


class SpotifyClient:
    def __init__(self, access_token: str, timeout: float = 15.0):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        })
        self.timeout = timeout

    def _request(self, method: str, path: str, **kwargs) -> dict | None:
        try:
            resp = self.session.request(method, f"{API_BASE}{path}",
                                        timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise SpotifyError(
                "Couldn't reach Spotify — check your internet connection "
                "and try again.") from exc
        if resp.status_code == 401:
            raise SpotifyError(
                "Spotify said the login has expired — reconnect Spotify "
                "in `tgmode setup` and try again.")
        if resp.status_code == 404:
            raise SpotifyError(
                "No active Spotify device found — open Spotify on your "
                "phone first (that's what plays through the car), then "
                "try again.")
        if resp.status_code >= 400:
            raise SpotifyError(
                f"Spotify returned an error ({resp.status_code}) — the "
                "mix didn't start, but everything else still ran.")
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def find_playlist_uri(self, search_phrase: str) -> str | None:
        data = self._request("GET", "/search",
                             params={"q": search_phrase, "type": "playlist",
                                     "limit": 1})
        items = (data or {}).get("playlists", {}).get("items", [])
        return items[0]["uri"] if items else None

    def play_mix(self, playlist_uri: str = "",
                 search_phrase: str = "love songs mix") -> str:
        """Start the mix on the active device, shuffle on. Returns a
        human description of what started."""
        uri = playlist_uri or self.find_playlist_uri(search_phrase)
        if not uri:
            raise SpotifyError(
                f"Couldn't find a Spotify playlist matching "
                f"\"{search_phrase}\" — paste a playlist link in "
                "`tgmode setup` instead.")
        self._request("PUT", "/me/player/shuffle", params={"state": "true"})
        self._request("PUT", "/me/player/play", json={"context_uri": uri})
        return f"love-songs mix ({uri})"
