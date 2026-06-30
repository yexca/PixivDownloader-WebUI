from types import SimpleNamespace

from backend.services.pixiv_client import PixivClient
from backend.services.pixiv_rate_policy import (
    PixivRequestPolicy,
    RateLimiter,
    RateLimitRule,
    RetryRule,
)


class FakePixivApi:
    def __init__(self, user_detail_result=None, user_detail_results=None):
        self.calls = []
        self.user_detail_result = user_detail_result
        self.user_detail_results = list(user_detail_results or [])

    def auth(self, *, refresh_token: str) -> None:
        self.calls.append(("auth", refresh_token))

    def user_detail(self, user_id: str):
        self.calls.append(("user_detail", user_id))
        if self.user_detail_results:
            result = self.user_detail_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        if self.user_detail_result is not None:
            return self.user_detail_result
        return SimpleNamespace(
            user=SimpleNamespace(
                id=user_id,
                name="Artist",
                account="artist",
                profile_image_urls={},
                comment="",
            )
        )

    def illust_detail(self, illust_id: str):
        self.calls.append(("illust_detail", illust_id))
        return SimpleNamespace(
            illust=SimpleNamespace(user=SimpleNamespace(id="123", name="Artist"))
        )

    def user_illusts(self, *args, **kwargs):
        self.calls.append(("user_illusts", args, kwargs))
        return SimpleNamespace(illusts=[], next_url=None)

    def parse_qs(self, next_url: str | None):
        self.calls.append(("parse_qs", next_url))
        return None


def make_illust(illust_id: str, user_id: str = "123"):
    return SimpleNamespace(
        id=illust_id,
        user=SimpleNamespace(id=user_id),
        title=f"Artwork {illust_id}",
        type="illust",
        caption="",
        page_count=1,
        width=100,
        height=100,
        sanity_level=2,
        restrict=0,
        tags=[],
        create_date="2026-01-01T00:00:00+09:00",
        meta_single_page=SimpleNamespace(
            original_image_url=f"https://i.pximg.net/img-original/img/{illust_id}_p0.jpg"
        ),
        meta_pages=[],
    )


class PagingPixivApi(FakePixivApi):
    def __init__(self):
        super().__init__()
        self.pages = [
            SimpleNamespace(
                illusts=[make_illust("254"), make_illust("253")],
                next_url="next-page",
            ),
            SimpleNamespace(
                illusts=[make_illust("252")],
                next_url=None,
            ),
        ]

    def user_illusts(self, *args, **kwargs):
        self.calls.append(("user_illusts", args, kwargs))
        return self.pages.pop(0)

    def parse_qs(self, next_url: str | None):
        self.calls.append(("parse_qs", next_url))
        return {"user_id": "123", "offset": 30} if next_url else None


def test_pixiv_client_sleeps_before_metadata_api_requests():
    api = FakePixivApi()
    sleeps = []
    client = PixivClient(refresh_token="token", api=api, sleeper=lambda: sleeps.append("sleep"))

    client.get_artist_by_user_id("123")
    client.get_artist_by_artwork_id("456")
    client.get_artworks_by_user_id("123")

    request_calls = [
        call[0] for call in api.calls if call[0] in {"user_detail", "illust_detail", "user_illusts"}
    ]
    assert request_calls == ["user_detail", "illust_detail", "user_illusts"]
    assert sleeps == ["sleep", "sleep", "sleep"]


def test_pixiv_client_stops_artwork_pages_at_known_artwork_id():
    api = PagingPixivApi()
    client = PixivClient(refresh_token="token", api=api)

    artworks = client.get_artworks_by_user_id("123", stop_at_artwork_id="253")

    assert [artwork.id for artwork in artworks] == ["254"]
    assert [call[0] for call in api.calls].count("user_illusts") == 1
    assert not any(call[0] == "parse_qs" for call in api.calls)


def test_pixiv_client_marks_japanese_user_not_found_as_unavailable():
    api = FakePixivApi(
        user_detail_result={
            "error": {
                "user_message": "エラーが発生しました",
                "message": "ユーザーが見つかりませんでした",
            }
        }
    )
    client = PixivClient(refresh_token="token", api=api)

    artist = client.get_artist_by_user_id("11915338")

    assert artist.id == "11915338"
    assert artist.account_status == "unavailable"
    assert artist.account_status_reason == "エラーが発生しました ユーザーが見つかりませんでした"


def test_pixiv_client_marks_restricted_user_detail_as_unavailable():
    api = FakePixivApi(
        user_detail_result={"error": {"user_message": "Your access is currently restricted."}}
    )
    client = PixivClient(refresh_token="token", api=api)

    artist = client.get_artist_by_user_id("11915338")

    assert artist.id == "11915338"
    assert artist.account_status == "unavailable"
    assert artist.account_status_reason == "Your access is currently restricted."


class FakePixivHttpError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"HTTP error {status_code}")


def test_pixiv_client_retries_retryable_metadata_status():
    api = FakePixivApi(
        user_detail_results=[
            FakePixivHttpError(429),
            SimpleNamespace(
                user=SimpleNamespace(
                    id="123",
                    name="Artist",
                    account="artist",
                    profile_image_urls={},
                    comment="",
                )
            ),
        ]
    )
    retry_sleeps = []
    client = PixivClient(
        refresh_token="token",
        api=api,
        request_policy=PixivRequestPolicy(
            rate_limiter=RateLimiter(RateLimitRule(0.0), sleep=retry_sleeps.append),
            retry_rule=RetryRule(status_delays_seconds={429: (0.25,)}),
            sleep=retry_sleeps.append,
        ),
    )

    artist = client.get_artist_by_user_id("123")

    assert artist.name == "Artist"
    assert [call[0] for call in api.calls].count("user_detail") == 2
    assert retry_sleeps == [0.25]
