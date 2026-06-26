class PixivDownloaderError(Exception):
    """Base class for predictable application errors."""


class ConfigError(PixivDownloaderError):
    """Raised when configuration cannot be loaded or validated."""


class PixivAuthError(PixivDownloaderError):
    """Raised when Pixiv authentication fails."""


class PixivApiError(PixivDownloaderError):
    """Raised when Pixiv API calls fail."""


class DownloadError(PixivDownloaderError):
    """Raised when a file download fails."""


class InsufficientDiskSpaceError(PixivDownloaderError):
    """Raised when downloads are blocked by the configured free-space floor."""


class DatabaseError(PixivDownloaderError):
    """Raised when database access fails."""


class JobCancelledError(PixivDownloaderError):
    """Raised when a download job is cancelled."""


class JobNotFoundError(PixivDownloaderError):
    """Raised when a requested job does not exist."""


class JobNotCancellableError(PixivDownloaderError):
    """Raised when a requested job cannot be cancelled."""
