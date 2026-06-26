# PixivDownloader-SQLite Documentation

This documentation is organized for three common readers:

- **Users** who want to install and run the downloader.
- **Operators** who want to run it with Docker Compose.
- **Developers** who want to understand or change the backend, frontend, and database.

## Start Here

- [Getting Started](getting-started.md): Docker Compose, local script runtime, and first configuration.
- [Deployment](deployment.md): Docker Compose, local scripts, ports, volumes, and packaging notes.
- [Configuration](configuration.md): settings storage, refresh token handling, and runtime environment variables.

## Architecture

- [Architecture](architecture.md): backend/frontend/runtime architecture and code ownership.
- [API Reference](api-reference.md): current HTTP and WebSocket API surface.
- [Database](database.md): SQLite schema, migration flow, and legacy `pic` migration.

## Development

- [Development Guide](development.md): local dev servers, checks, project conventions, and troubleshooting.
- [Verification](verification.md): automated checks, smoke tests, Docker checks, and manual UI checklist.
