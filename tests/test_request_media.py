"""Regression tests for request creation with incomplete Overseerr responses."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.models.overseerr import MediaType
from src.tools.overseerr_client import OverseerrClient, OverseerrError


def request_record(request_id=760, tmdb_id=315154):
    return {
        "id": request_id,
        "status": 2,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "type": "tv",
        "media": {"id": 991, "tmdbId": tmdb_id},
    }


@pytest.mark.asyncio
async def test_complete_response_needs_no_reconciliation():
    client = OverseerrClient(base_url="http://unused", api_key="test")
    record = request_record()
    client._request = AsyncMock(return_value=record)

    result = await client.request_media(MediaType.TV, 315154, seasons=[1])

    assert result.id == 760
    assert client._request.await_count == 1
    assert client._request.await_args.args == ("POST", "/request")
    assert client._request.await_args.kwargs["json"]["seasons"] == [1]


@pytest.mark.asyncio
async def test_missing_id_is_verified_by_read_only_lookup():
    client = OverseerrClient(base_url="http://unused", api_key="test")
    incomplete = {k: v for k, v in request_record().items() if k != "id"}
    client._request = AsyncMock(side_effect=[
        incomplete,
        {"results": [request_record()]},
    ])

    result = await client.request_media(MediaType.TV, 315154)

    assert result.id == 760
    assert [call.args[0] for call in client._request.await_args_list] == ["POST", "GET"]
    assert client._request.await_args_list[1].args[1] == "/request"


@pytest.mark.asyncio
async def test_unverified_result_never_repeats_post():
    client = OverseerrClient(base_url="http://unused", api_key="test")
    client._request = AsyncMock(side_effect=[
        {"type": "tv", "media": {"id": 991, "tmdbId": 315154}},
        {"results": []},
    ])

    with pytest.raises(OverseerrError, match="could not uniquely verify"):
        await client.request_media(MediaType.TV, 315154)

    assert [call.args[0] for call in client._request.await_args_list] == ["POST", "GET"]


@pytest.mark.asyncio
async def test_multiple_possible_new_requests_are_not_guessed():
    client = OverseerrClient(base_url="http://unused", api_key="test")
    client._request = AsyncMock(side_effect=[
        {"type": "tv"},
        {"results": [request_record(760), request_record(761)]},
    ])

    with pytest.raises(OverseerrError, match="could not uniquely verify"):
        await client.request_media(MediaType.TV, 315154)

    assert [call.args[0] for call in client._request.await_args_list] == ["POST", "GET"]
