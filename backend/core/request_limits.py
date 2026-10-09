from tempfile import SpooledTemporaryFile

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class LegacyUploadLimit:
    """Bound multipart input before its parser can spool an unlimited request."""

    def __init__(self, app: ASGIApp, max_bytes: int = 65 * 1024 * 1024) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != "/api/imports/legacy-database"
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length", b"")
        if length.isdigit() and int(length) > self.max_bytes:
            await self.reject(scope, receive, send)
            return
        with SpooledTemporaryFile(max_size=1024 * 1024) as body:
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.max_bytes:
                    await self.reject(scope, receive, send)
                    return
                body.write(chunk)
                if not message.get("more_body", False):
                    break
            body.seek(0)

            async def replay():
                chunk = body.read(1024 * 1024)
                return {"type": "http.request", "body": chunk, "more_body": body.tell() < size}

            await self.app(scope, replay, send)

    async def reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            {"error": {"code": "upload_too_large", "message": "Upload exceeds 65 MiB"}},
            status_code=413,
        )
        await response(scope, receive, send)
