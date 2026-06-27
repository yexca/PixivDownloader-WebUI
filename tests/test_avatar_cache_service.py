from backend.domain.entities import Artist
from backend.services.avatar_cache_service import AvatarCacheService


class FakeResponse:
    def __init__(self, chunks, content_type="image/png"):
        self.chunks = chunks
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size: int):
        assert chunk_size > 0
        return iter(self.chunks)


class FakeHttpClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url: str, *, headers: dict[str, str], stream: bool, timeout: int):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "stream": stream,
                "timeout": timeout,
            }
        )
        return self.response


def test_avatar_cache_downloads_and_serves_cached_file(tmp_path):
    http_client = FakeHttpClient(FakeResponse([b"avatar"]))
    service = AvatarCacheService(tmp_path, http_client=http_client)
    artist = Artist(
        id="123",
        name="Artist",
        avatar_url="https://i.pximg.net/user-profile/img/avatar.png",
    )

    assert service.cache_artist_avatar(artist) is True

    cached = service.get_cached_avatar("123")
    assert cached is not None
    assert cached.path.read_bytes() == b"avatar"
    assert cached.media_type == "image/png"
    assert service.has_cached_avatar("123") is True
    assert http_client.calls[0]["headers"]["Referer"] == "https://www.pixiv.net/"


def test_avatar_cache_ignores_missing_or_invalid_avatar(tmp_path):
    service = AvatarCacheService(tmp_path)

    assert service.cache_artist_avatar(Artist(id="123", name="Artist")) is False
    assert service.cache_artist_avatar(
        Artist(id="123", name="Artist", avatar_url="https://example.com/avatar.txt")
    ) is False
    assert service.has_cached_avatar("123") is False


def test_avatar_cache_removes_artist_avatar(tmp_path):
    service = AvatarCacheService(
        tmp_path,
        http_client=FakeHttpClient(FakeResponse([b"avatar"], content_type="image/jpeg")),
    )
    artist = Artist(id="123", name="Artist", avatar_url="https://example.com/avatar.jpg")
    assert service.cache_artist_avatar(artist) is True

    service.remove_artist_avatar("123")

    assert service.get_cached_avatar("123") is None
