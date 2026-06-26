# PixivDownloader-SQLite

> Languages: [English](README.md) | [日本語](README.ja.md)

PixivDownloader-SQLite 是一个面向 Windows 本地使用的 Pixiv 下载与管理工具。当前版本正在从旧的 PyQt6 桌面应用重构为本地 WebUI：使用 FastAPI 作为后端，React + TypeScript 作为前端，并继续使用本地 SQLite 保存数据。

## 功能

- 通过 Pixiv 用户 ID 或作品 ID 创建下载任务。
- 在 WebUI 中管理下载目录和 Pixiv `refresh_token`。
- 使用 SQLite 记录任务、画师、作品和文件状态。
- 自动迁移旧版 `resources/pixiv.db` 中的 `pic` 表数据。
- 通过 `run-webui.bat` 本地启动 WebUI，不需要独立数据库服务器。
- 通过 `run-gui.bat` 仍可启动旧版 PyQt 桌面 GUI。

## 运行架构

```text
run-webui.bat
  -> env\python.exe -m backend.app
  -> 在 http://127.0.0.1:7653 启动 FastAPI
  -> 托管 frontend\dist
  -> 自动打开浏览器中的 WebUI
```

主要目录：

- `backend/`: FastAPI 接口、服务、仓储、SQLite 迁移和后台下载队列。
- `frontend/`: React、TypeScript、Vite、Tailwind CSS 前端。
- `resources/`: 本地配置与 SQLite 数据库。
- `app/`: 通过 `run-gui.bat` 启动的旧 PyQt 代码；当前主要面向用户的界面是 WebUI。

## 安装

在项目目录运行：

```bat
run-install.bat
```

安装脚本会：

1. 如果缺少 Miniconda，则安装到 `%UserProfile%\Miniconda3`。
2. 创建本地 `env` 环境。
3. 将 Python 依赖安装到 `env`。
4. 使用 `npm` 安装前端依赖。
5. 构建前端资源到 `frontend\dist`。

安装脚本不会使用全局 Python。当前 Node.js 策略是检测系统 PATH 中的 `npm`；如果缺失，请先从 <https://nodejs.org/> 安装 Windows LTS 版 Node.js。

## 启动

WebUI：

```bat
run-webui.bat
```

脚本会检查 `env\python.exe` 和 `frontend\dist\index.html` 是否存在，然后启动后端并打开 <http://127.0.0.1:7653>。

旧版 PyQt GUI：

```bat
run-gui.bat
```

脚本会通过 `main.py` 启动原来的 PyQt 桌面界面。

如果需要使用其他本地端口，可以在运行脚本前设置 `PIXIVDOWNLOADER_PORT`。

## Docker Compose

使用已发布镜像并保持相同本地端口：

```bat
docker compose up -d
```

Compose 文件使用并可构建 `yexca/pixivdownloader:v0.2.0`，映射 `7653:7653`，并挂载本地 `resources/` 和 `downloads/` 目录用于持久化。

Docker Compose 还会启动 `pixiv-auth-browser` 认证浏览器 sidecar，并映射 noVNC 端口 `6080:6080`。在 WebUI 设置页点击 Pixiv 登录后，会打开 <http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale>，在远程浏览器中完成 Pixiv 登录后，后端会自动捕获回调并保存 `refresh_token`。

```bat
docker compose build
```

## 开发

后端开发服务：

```bat
run-backend-dev.bat
```

前端开发服务：

```bat
run-frontend-dev.bat
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

- `resources\conf\settings.json`
- `resources\pixiv.db`
- `frontend\dist`

如果以后制作冻结可执行文件，应将这些资源按相同相对结构放在可执行文件旁边。后端路径解析器在冻结运行时会使用可执行文件所在目录。

## 重要声明

本工具仅供个人学习、研究或数据备份使用。请遵守 Pixiv 的服务条款，不要将本工具用于批量下载或内容再分发。
