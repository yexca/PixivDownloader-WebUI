from typing import Literal

ArtworkFileStatus = Literal["pending", "downloading", "downloaded", "skipped", "failed"]
DownloadInputMode = Literal["artist", "artwork"]
