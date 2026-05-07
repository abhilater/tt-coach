"""YouTube uploads playlist paging and published-at cutoff."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.ingest.youtube import channel_uploads


def test_channel_uploads_breaks_when_hitting_age_cutoff() -> None:
    now = datetime.now(tz=UTC)
    recent = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")

    first_resp = {
        "items": [
            {"contentDetails": {"videoId": "NEWINWINDOW__", "videoPublishedAt": recent}},
            {"contentDetails": {"videoId": "TOOOLDDDDDDDD_", "videoPublishedAt": stale}},
        ]
    }

    list_request = MagicMock()
    list_request.execute.return_value = first_resp

    playlists_inst = MagicMock()
    playlists_inst.list.return_value = list_request
    playlists_inst.list_next.return_value = None

    channels_inst = MagicMock()
    channels_inst.list.return_value.execute.return_value = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUuploads______"}}}],
    }

    yt_mock = MagicMock()
    yt_mock.channels.return_value = channels_inst
    yt_mock.playlistItems.return_value = playlists_inst

    with patch("app.ingest.youtube.yt_service", return_value=yt_mock):
        out = channel_uploads("key", "UCwhatever____", days=30, max_results=50)

    assert out == ["NEWINWINDOW__"]
    playlists_inst.list_next.assert_not_called()


def test_channel_uploads_fetches_next_page_until_max_results() -> None:
    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    page_ids = [f"n{i:010d}a"[-11:] for i in range(5)]
    page_items = [
        {"contentDetails": {"videoId": vid, "videoPublishedAt": now}}
        for vid in page_ids
    ]

    first_req = MagicMock()
    second_req = MagicMock()
    first_req.execute.return_value = {"items": page_items[:3]}
    second_req.execute.return_value = {"items": page_items[3:5]}

    playlists_inst = MagicMock()
    playlists_inst.list.return_value = first_req

    def list_next_side_effect(req, _resp):
        if req is first_req:
            return second_req
        return None

    playlists_inst.list_next.side_effect = list_next_side_effect

    channels_inst = MagicMock()
    channels_inst.list.return_value.execute.return_value = {
        "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUlist_________"}}}],
    }

    yt_mock = MagicMock()
    yt_mock.channels.return_value = channels_inst
    yt_mock.playlistItems.return_value = playlists_inst

    with patch("app.ingest.youtube.yt_service", return_value=yt_mock):
        out = channel_uploads("key", "UCchan_________", days=365, max_results=5)

    assert len(out) == 5
    assert out[0] == page_ids[0]
    playlists_inst.list_next.assert_called_once()
