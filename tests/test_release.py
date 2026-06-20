"""Tests for fastcontext_mcp.release — prebuilt wheel resolution.

These tests don't hit the real GitHub API. They mock urllib to return
canned responses so the logic is tested deterministically.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from fastcontext_mcp.release import (
    GITHUB_OWNER,
    GITHUB_REPO,
    ReleaseError,
    download_wheel,
    find_wheel_asset,
    latest_release,
    resolve_wheel_url,
)

# --- Constants -----------------------------------------------------------

class TestConstants:
    def test_owner_is_set(self):
        assert GITHUB_OWNER == "rubybear-lgtm"

    def test_repo_is_set(self):
        assert GITHUB_REPO == "fastcontext"


# --- find_wheel_asset ----------------------------------------------------

class TestFindWheelAsset:
    def test_finds_wheel(self):
        release = {
            "assets": [
                {"name": "source.tar.gz", "browser_download_url": "https://x/src.tar.gz"},
                {"name": "fastcontext_mcp-0.1.0-py3-none-any.whl",
                 "browser_download_url": "https://x/fastcontext_mcp-0.1.0-py3-none-any.whl"},
            ]
        }
        asset = find_wheel_asset(release)
        assert asset is not None
        assert asset["name"] == "fastcontext_mcp-0.1.0-py3-none-any.whl"
        assert asset["browser_download_url"] == "https://x/fastcontext_mcp-0.1.0-py3-none-any.whl"

    def test_no_wheel_returns_none(self):
        release = {"assets": [{"name": "source.tar.gz"}]}
        assert find_wheel_asset(release) is None

    def test_empty_assets(self):
        assert find_wheel_asset({"assets": []}) is None

    def test_missing_assets_key(self):
        assert find_wheel_asset({}) is None

    def test_matches_versioned_wheel(self):
        release = {"assets": [{"name": "fastcontext_mcp-1.2.3-py3-none-any.whl"}]}
        asset = find_wheel_asset(release)
        assert asset is not None
        assert "1.2.3" in asset["name"]

    def test_does_not_match_non_py3_wheel(self):
        release = {"assets": [{"name": "fastcontext_mcp-0.1.0-cp312-cp312-macosx_11_0_arm64.whl"}]}
        # Only py3-none-any wheels are platform-independent and safe to distribute
        assert find_wheel_asset(release) is None


# --- latest_release ------------------------------------------------------

class TestLatestRelease:
    @patch("fastcontext_mcp.release._api_get")
    def test_fetches_latest(self, mock_get: MagicMock):
        mock_get.return_value = {"tag_name": "v0.1.0", "assets": []}
        result = latest_release()
        assert result["tag_name"] == "v0.1.0"
        # Should call the /latest endpoint
        assert mock_get.call_args[0][0].endswith("/releases/latest")

    @patch("fastcontext_mcp.release._api_get")
    def test_falls_back_to_list(self, mock_get: MagicMock):
        # First call (latest) raises, second (list) returns releases
        mock_get.side_effect = [Exception("404 no latest"), [{"tag_name": "v0.0.9"}]]
        result = latest_release()
        assert result["tag_name"] == "v0.0.9"

    @patch("fastcontext_mcp.release._api_get")
    def test_no_releases_raises(self, mock_get: MagicMock):
        mock_get.side_effect = [Exception("404"), []]
        with pytest.raises(ReleaseError, match="No GitHub releases"):
            latest_release()

    @patch("fastcontext_mcp.release._api_get")
    def test_both_calls_fail_raises(self, mock_get: MagicMock):
        mock_get.side_effect = [Exception("net"), Exception("net")]
        with pytest.raises(ReleaseError, match="Could not fetch releases"):
            latest_release()


# --- resolve_wheel_url ---------------------------------------------------

class TestResolveWheelUrl:
    @patch("fastcontext_mcp.release.latest_release")
    def test_returns_url_and_version(self, mock_latest: MagicMock):
        mock_latest.return_value = {
            "tag_name": "v0.1.0",
            "assets": [{
                "name": "fastcontext_mcp-0.1.0-py3-none-any.whl",
                "browser_download_url": "https://example.com/whl",
            }],
        }
        url, version = resolve_wheel_url()
        assert url == "https://example.com/whl"
        assert version == "v0.1.0"

    @patch("fastcontext_mcp.release.latest_release")
    def test_no_wheel_returns_none(self, mock_latest: MagicMock):
        mock_latest.return_value = {"tag_name": "v0.1.0", "assets": []}
        assert resolve_wheel_url() is None

    @patch("fastcontext_mcp.release.latest_release")
    def test_missing_download_url_returns_none(self, mock_latest: MagicMock):
        mock_latest.return_value = {
            "tag_name": "v0.1.0",
            "assets": [{"name": "fastcontext_mcp-0.1.0-py3-none-any.whl"}],
        }
        assert resolve_wheel_url() is None

    @patch("fastcontext_mcp.release.latest_release", side_effect=ReleaseError("nope"))
    def test_release_error_returns_none(self, mock_latest: MagicMock):
        assert resolve_wheel_url() is None


# --- download_wheel ------------------------------------------------------

class TestDownloadWheel:
    @patch("fastcontext_mcp.release.urllib.request.urlretrieve")
    def test_downloads_to_dest(self, mock_retrieve: MagicMock):
        result = download_wheel("https://x/whl", "/tmp/out.whl")
        assert result == "/tmp/out.whl"
        mock_retrieve.assert_called_once_with("https://x/whl", "/tmp/out.whl")

    @patch(
        "fastcontext_mcp.release.urllib.request.urlretrieve",
        side_effect=Exception("network error"),
    )
    def test_failure_raises_release_error(self, mock_retrieve: MagicMock):
        with pytest.raises(ReleaseError, match="Failed to download wheel"):
            download_wheel("https://x/whl", "/tmp/out.whl")


# --- Integration: full resolve flow --------------------------------------

class TestResolveFlow:
    @patch("fastcontext_mcp.release._api_get")
    def test_full_flow_finds_wheel(self, mock_get: MagicMock):
        """End-to-end: API returns a release with a wheel, we resolve it."""
        mock_get.return_value = {
            "tag_name": "v0.2.0",
            "assets": [{
                "name": "fastcontext_mcp-0.2.0-py3-none-any.whl",
                "browser_download_url": "https://github.com/releases/v0.2.0/whl",
            }],
        }
        url, version = resolve_wheel_url()
        assert "github.com" in url
        assert version == "v0.2.0"

    @patch("fastcontext_mcp.release._api_get")
    def test_full_flow_no_wheel_falls_to_none(self, mock_get: MagicMock):
        """End-to-end: API returns a release without a wheel."""
        mock_get.return_value = {"tag_name": "v0.1.0", "assets": []}
        assert resolve_wheel_url() is None
