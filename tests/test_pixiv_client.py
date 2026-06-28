from types import SimpleNamespace

from backend.services.pixiv_client import PixivClient


class FakePixivApi:
    def __init__(self, user_detail_result=None):
        self.calls = []
        self.user_detail_result = user_detail_result

    def auth(self, *, refresh_token: str) -> None:
        self.calls.append(("auth", refresh_token))

    def user_detail(self, user_id: str):
        self.calls.append(("user_detail", user_id))
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
