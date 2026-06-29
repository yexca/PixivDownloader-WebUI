from backend.services.file_downloader import FileDownloader
from backend.services.pixiv_rate_policy import (
    PixivRequestPolicy,
    RateLimiter,
    RateLimitRule,
    RetryRule,
)


class FakeResponse:
    def __init__(self, chunks, status_code=200):
        self.chunks = chunks
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeHttpError(self.status_code)
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        return self.chunks


class FakeHttpError(Exception):
    def __init__(self, status_code):
        self.response = FakeResponse([], status_code=status_code)
        super().__init__(f"HTTP error {status_code}")


class FakeHttpClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [FakeResponse([b"new"])])

    def get(self, url, *, headers, stream, timeout):
        self.calls.append((url, headers, stream, timeout))
        return self.responses.pop(0)


def test_file_downloader_skips_existing_file(tmp_path):
    target = tmp_path / "Artist - 123" / "100_p0.jpg"
    target.parent.mkdir()
    target.write_bytes(b"old")
    http_client = FakeHttpClient()
    downloader = FileDownloader(
        tmp_path,
        http_client=http_client,
        existing_file_behavior="skip",
    )

    result = downloader.download("Artist", "123", "https://example.test/100_p0.jpg")

    assert result.skipped is True
    assert result.local_path == target
    assert target.read_bytes() == b"old"
    assert http_client.calls == []


def test_file_downloader_skip_existing_does_not_wait(tmp_path):
    target = tmp_path / "Artist - 123" / "100_p0.jpg"
    target.parent.mkdir()
    target.write_bytes(b"old")
    waits = []
    downloader = FileDownloader(
        tmp_path,
        http_client=FakeHttpClient(),
        existing_file_behavior="skip",
        request_policy=PixivRequestPolicy(
            rate_limiter=RateLimiter(RateLimitRule(10.0), sleep=waits.append),
            retry_rule=RetryRule(status_delays_seconds={}),
            sleep=waits.append,
        ),
    )

    downloader.download("Artist", "123", "https://example.test/100_p0.jpg")

    assert waits == []


def test_file_downloader_overwrites_existing_file(tmp_path):
    target = tmp_path / "Artist - 123" / "100_p0.jpg"
    target.parent.mkdir()
    target.write_bytes(b"old")
    http_client = FakeHttpClient()
    downloader = FileDownloader(
        tmp_path,
        http_client=http_client,
        existing_file_behavior="overwrite",
    )

    result = downloader.download("Artist", "123", "https://example.test/100_p0.jpg")

    assert result.skipped is False
    assert result.local_path == target
    assert target.read_bytes() == b"new"
    assert len(http_client.calls) == 1


def test_file_downloader_saves_duplicate_file(tmp_path):
    target = tmp_path / "Artist - 123" / "100_p0.jpg"
    target.parent.mkdir()
    target.write_bytes(b"old")
    http_client = FakeHttpClient()
    downloader = FileDownloader(
        tmp_path,
        http_client=http_client,
        existing_file_behavior="save_duplicate",
    )

    result = downloader.download("Artist", "123", "https://example.test/100_p0.jpg")

    assert result.skipped is False
    assert result.local_path == tmp_path / "Artist - 123" / "100_p0 (1).jpg"
    assert target.read_bytes() == b"old"
    assert result.local_path.read_bytes() == b"new"
    assert len(http_client.calls) == 1


def test_file_downloader_retries_retryable_http_status(tmp_path):
    http_client = FakeHttpClient(
        responses=[
            FakeResponse([], status_code=429),
            FakeResponse([b"new"], status_code=200),
        ]
    )
    retry_sleeps = []
    downloader = FileDownloader(
        tmp_path,
        http_client=http_client,
        existing_file_behavior="overwrite",
        request_policy=PixivRequestPolicy(
            rate_limiter=RateLimiter(RateLimitRule(0.0), sleep=retry_sleeps.append),
            retry_rule=RetryRule(status_delays_seconds={429: (0.25,)}),
            sleep=retry_sleeps.append,
        ),
    )

    result = downloader.download("Artist", "123", "https://example.test/100_p0.jpg")

    assert result.local_path.read_bytes() == b"new"
    assert len(http_client.calls) == 2
    assert retry_sleeps == [0.25]
