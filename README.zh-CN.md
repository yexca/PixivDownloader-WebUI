# PixivDownloader-SQLite

> Languages: [English](README.md) | [日本語](README.ja.md)

PixivDownloader-SQLite 是一个本地 Pixiv 下载与管理 WebUI。当前维护的运行时由 FastAPI 后端、React + TypeScript 前端和本地 SQLite 数据库组成。

本仓库是 WebUI 重写版本。项目保留旧版 PyQt `pixiv.db` 数据导入能力，但旧桌面程序源码不属于本项目。

## 功能

- 通过 Pixiv 用户 ID 或作品 ID 创建下载任务。
- 在 WebUI 中管理下载目录和 Pixiv `refresh_token`。
- 使用 SQLite 记录任务、画师、作品和文件状态。
- 可在 WebUI 设置页显式导入旧版 PyQt `pixiv.db` 数据。
- 优先通过 Docker Compose 运行，也可以使用本地 Windows 脚本运行 WebUI。

## 推荐方式：Docker Compose

启动 WebUI：

```bat
docker compose up -d
```

打开：

```text
http://127.0.0.1:7653
```

默认启动只包含 WebUI。需要通过浏览器登录 Pixiv 时，WebUI 会提示启动 `pixiv-auth-browser` 认证浏览器 sidecar：

```bat
docker compose --profile auth up -d pixiv-auth-browser
```

认证浏览器 sidecar 会映射 noVNC：

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale
```

在 WebUI 设置页点击 Pixiv 登录后，在 noVNC 浏览器中完成 Pixiv 登录。后端会自动捕获回调并保存 `refresh_token`。配置完成并通过测试后，WebUI 会提示可以关闭认证浏览器：

```bat
docker compose stop pixiv-auth-browser
```

停止：

```bat
docker compose down
```

Compose 文件可构建 `yexca/pixivdownloader:v0.2.0`，映射 `7653:7653`，并挂载本地 `config/`、`resources/` 和 `downloads/` 目录用于持久化。

## 本地 Windows 运行

在项目目录安装：

```bat
run-install.bat
```

启动 WebUI：

```bat
run-webui.bat
```

脚本会检查 `env\python.exe` 和 `frontend\dist\index.html` 是否存在，然后启动后端并打开 <http://127.0.0.1:7653>。

如果需要使用其他本地端口，可以在运行脚本前设置 `PIXIVDOWNLOADER_PORT`。

## 运行架构

```text
浏览器 WebUI
  -> http://127.0.0.1:7653 上的 FastAPI 后端
  -> resources/ 中的 SQLite 数据库
  -> 配置的下载目录
```

主要目录：

- `backend/`: FastAPI 接口、服务、仓储、SQLite 迁移和后台下载队列。
- `frontend/`: React、TypeScript、Vite、Tailwind CSS 前端。
- `auth-browser/`: Docker 下用于 Pixiv 浏览器登录的 sidecar。
- `config/`: WebUI 配置；`settings.example.json` 可提交，`settings.json` 保存本地用户配置。
- `resources/`: SQLite 数据库与静态资源。

## 配置迁移

WebUI 默认配置来自：

```text
config\settings.example.json
```

本地用户配置和密钥保存到被忽略的文件：

```text
config\settings.json
```

旧版 `resources\conf\settings.json` 不会自动读取。如需显式迁移：

```bat
env\python.exe tools\migrate_settings_to_config.py
```

如果 `config\settings.json` 已存在，可以使用 `--overwrite`。

## 开发

后端开发服务：

```bat
env\python.exe -m uvicorn backend.app:create_app --factory --reload --host 127.0.0.1 --port 7653
```

前端开发服务：

```bat
cd frontend
npm run dev
```

检查命令：

```bat
env\python.exe -m ruff format --check .
env\python.exe -m ruff check .
env\python.exe -m pytest
```

```bat
cd frontend
npm run lint
npm run typecheck
npm run build
```

## 文档

- [文档入口](docs/README.md)
- [快速开始](docs/getting-started.md)
- [架构](docs/architecture.md)
- [部署](docs/deployment.md)
- [数据库](docs/database.md)
- [开发指南](docs/development.md)

## 打包说明

源码运行模式下，后端从仓库根目录解析资源：

- `config\settings.example.json`
- `config\settings.json`
- `resources\pixiv.sqlite3`
- `frontend\dist`

如果以后制作冻结可执行文件，应将这些资源按相同相对结构放在可执行文件旁边。后端路径解析器在冻结运行时会使用可执行文件所在目录。

## 重要声明

本工具仅供个人学习、研究或数据备份使用。请遵守 Pixiv 的服务条款，不要将本工具用于批量下载或内容再分发。
