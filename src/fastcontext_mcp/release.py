"""Resolve and download prebuilt wheel releases from GitHub.

Used by ``scripts/install.sh`` to install a prebuilt wheel instead of
building from a git clone. Falls back to the git URL if no release is
available.

The GitHub release is expected to have a wheel asset matching the pattern
``fastcontext_mcp-<version>-py3-none-any.whl`` attached to it.
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Optional

GITHUB_OWNER = "rubybear-lgtm"
GITHUB_REPO = "fastcontext"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

_WHEEL_RE = re.compile(r"fastcontext_mcp-[\w.]+-py3-none-any\.whl$")


class ReleaseError(Exception):
    """Raised when a release or wheel cannot be found or downloaded."""


def _api_get(url: str, *, timeout: float = 30) -> dict:
    """Fetch JSON from the GitHub API."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "fastcontext-mcp-installer",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_release(*, timeout: float = 30) -> dict:
    """Return the latest published release dict from GitHub.

    Includes draft/prereleases only if no stable release exists.
    Raises ReleaseError if the API call fails or no release exists.
    """
    try:
        return _api_get(f"{RELEASES_API}/latest", timeout=timeout)
    except Exception as e:
        # No published releases yet — fall back to listing all releases
        try:
            releases = _api_get(RELEASES_API, timeout=timeout)
        except Exception as list_err:
            raise ReleaseError(
                f"Could not fetch releases: latest={e}, list={list_err}"
            ) from list_err
        if not releases:
            raise ReleaseError("No GitHub releases found")
        return releases[0]


def find_wheel_asset(release: dict) -> Optional[dict]:
    """Find the wheel asset in a release dict, or None if not present."""
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if _WHEEL_RE.search(name):
            return asset
    return None


def resolve_wheel_url(*, timeout: float = 30) -> Optional[tuple[str, str]]:
    """Resolve the latest prebuilt wheel URL.

    Returns a tuple of (download_url, version) or None if no prebuilt
    wheel is available (caller should fall back to git install).
    """
    try:
        release = latest_release(timeout=timeout)
    except ReleaseError:
        return None

    asset = find_wheel_asset(release)
    if asset is None:
        return None

    url = asset.get("browser_download_url")
    if not url:
        return None

    version = release.get("tag_name", "unknown")
    return (url, version)


def download_wheel(url: str, dest_path: str, *, timeout: float = 120) -> str:
    """Download a wheel from ``url`` to ``dest_path``.

    Returns the destination path. Raises ReleaseError on failure.
    """
    try:
        urllib.request.urlretrieve(url, dest_path)
    except Exception as e:
        raise ReleaseError(f"Failed to download wheel from {url}: {e}") from e
    return dest_path
