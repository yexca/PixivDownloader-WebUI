from backend.services.file_downloader import FileDownloader


class FakeResponse:
    def __init__(self, chunks):
        self.chunks = chunks

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        return self.chunks


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    def get(self, url, *, headers, stream, timeout):
        self.calls.append((url, headers, stream, timeout))
        return FakeResponse([b"new"])


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
