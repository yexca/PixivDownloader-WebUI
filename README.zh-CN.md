# PixivDownloader WebUI

> 语言: [English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

> 注意: 当前程序界面仅支持英语。后续是否加入 i18n / 多语言界面，将根据开发情况决定。

PixivDownloader WebUI 是一个本地优先的 Pixiv 作品备份、工作流自动化和图库管理 WebUI。它由 FastAPI 后端、React + TypeScript 前端和本地 SQLite 数据库组成。

本仓库是 PixivDownloader 的 WebUI 项目。它支持导入 [yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite) 生成的 `pixiv.db` 数据库，但不会捆绑该项目的源码。

## 功能

- Dashboard 显示工作流运行、触发器健康状态、队列压力和图库注意事项。
- 支持可复用的工作流定义，可手动运行或创建计划触发器。
- 支持通过 Pixiv 画师 ID 或作品 ID 创建快捷下载。
- 支持图库、画师详情、作品文件状态、本地标签、重试、同步和删除操作。
- 支持队列暂停/恢复、任务重试/重新运行/取消、批量取消和 WebSocket 实时进度。
- 支持配置下载目录、Pixiv 登录、请求/文件下载延迟、并发限制、磁盘空间保护、已有文件处理方式和图库过期检查。
- Docker 环境下可使用可选 noVNC 认证浏览器 sidecar 完成 Pixiv 登录。
- 可在 Settings 中显式导入 [yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite) 的 `pixiv.db`。
- 支持 Docker Compose 运行，也支持本地 Windows 脚本运行。

## 推荐运行方式: Docker Compose

启动 WebUI:

```bat
docker compose up -d
```

打开:

```text
http://127.0.0.1:7653
```

默认 Compose 启动只运行 WebUI。需要通过浏览器登录 Pixiv 时，启动可选的 `pixiv-auth-browser` sidecar:

```bat
docker compose --profile auth up -d pixiv-auth-browser
```

sidecar 会暴露 noVNC:

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale
```

在 WebUI Settings 中点击 Pixiv 登录后，在 noVNC 浏览器中完成 Pixiv 登录。sidecar 会把回调发送给后端，后端会自动保存 `refresh_token`。

配置并测试 token 后，可以停止认证浏览器:

```bat
docker compose stop pixiv-auth-browser
```

停止 WebUI:

```bat
docker compose down
```

Compose 文件可构建 `yexca/pixivdownloader:v0.2.0`，映射 `7653:7653`，并挂载本地 `config/`、`resources/` 和 `downloads/` 用于持久化。`auth` profile 也可以构建和运行 `yexca/pixivdownloader-auth-browser:v0.2.0`。

## 本地 Windows 运行

在项目目录安装:

```bat
run-install.bat
```

运行:

```bat
run-webui.bat
```

脚本会检查 `env\python\python.exe` 和 `frontend\dist\index.html` 是否存在，启动后端，并打开 <http://127.0.0.1:7653>。

如果需要使用其他本地端口，请在运行脚本前设置 `PIXIVDOWNLOADER_PORT`。

## 运行架构

```text
浏览器 WebUI
  -> http://127.0.0.1:7653 上的 FastAPI 后端
  -> 工作流运行、触发器、队列、任务和 worker
  -> resources/ 中的 SQLite 数据库
  -> 配置的下载目录
```

主要目录:

- `backend/`: FastAPI API、服务、仓库、SQLite 迁移、工作流运行器、调度器和下载 worker。
- `frontend/`: React、TypeScript、Vite、Tailwind CSS WebUI。
- `auth-browser/`: 可选 Docker sidecar，用于 Pixiv 浏览器登录。
- `config/`: WebUI 配置；`settings.example.json` 提交到仓库，`settings.json` 保存本地用户配置和密钥。
- `resources/`: SQLite 数据库、导入的 PixivDownloader-SQLite 数据库、缓存资源和静态资源。
- `tools/`: 维护工具，例如历史配置迁移。
- `tests/`: 后端回归测试。

## 配置迁移

WebUI 默认配置来自:

```text
config\settings.example.json
```

本地用户配置和密钥会保存到被忽略的文件:

```text
config\settings.json
```

旧的 `resources\conf\settings.json` 不会自动读取。如需显式迁移:

```bat
env\python\python.exe tools\migrate_settings_to_config.py
```

如果 `config\settings.json` 已存在，可以使用 `--overwrite`。

## 开发

后端开发服务:

```bat
env\python\python.exe -m uvicorn backend.app:create_app --factory --reload --host 127.0.0.1 --port 7653
```

前端开发服务:

```bat
cd frontend
npm run dev
```

检查命令:

```bat
env\python\python.exe -m ruff format --check .
env\python\python.exe -m ruff check .
env\python\python.exe -m pytest
```

```bat
cd frontend
npm run lint
npm run typecheck
npm run build
```

## 文档

- [文档入口](docs/README.md)
- [Getting Started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [API Reference](docs/api-reference.md)
- [Deployment](docs/deployment.md)
- [Database](docs/database.md)
- [Development Guide](docs/development.md)
- [Verification](docs/verification.md)

## 打包说明

源码运行模式下，后端会从仓库根目录解析资源:

- `config\settings.example.json`
- `config\settings.json`
- `resources\pixiv.sqlite3`
- `frontend\dist`

如果未来制作冻结可执行文件，应将这些资源按相同相对结构放在可执行文件旁边。后端路径解析器在冻结运行时会使用可执行文件所在目录。

## 重要声明

本工具仅供个人学习、研究或数据备份使用。请遵守 Pixiv 的服务条款，不要将本工具用于滥用式批量下载或内容再分发。
