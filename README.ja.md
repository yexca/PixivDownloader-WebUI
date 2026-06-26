# PixivDownloader-SQLite

> Languages: [English](README.md) | [简体中文](README.zh-CN.md)

PixivDownloader-SQLite は、Pixiv 作品のバックアップと管理を行うローカル WebUI です。現在メンテナンスされている実行環境は、FastAPI バックエンド、React + TypeScript フロントエンド、ローカル SQLite データベースで構成されています。

旧 PyQt デスクトップアプリは `legacy/pyqt/` にアーカイブされており、現在のメンテナンス対象ではありません。

## 主な機能

- Pixiv ユーザー ID または作品 ID からダウンロードジョブを作成。
- WebUI でダウンロード先と Pixiv `refresh_token` を管理。
- SQLite にジョブ、アーティスト、作品、ファイル状態を保存。
- WebUI の Settings から旧 PyQt `pixiv.db` データを明示的にインポート。
- Docker Compose を優先し、必要に応じて Windows ローカルスクリプトでも WebUI を実行可能。

## 推奨: Docker Compose

WebUI を起動します:

```bat
docker compose up -d
```

開きます:

```text
http://127.0.0.1:7653
```

Docker Compose は `pixiv-auth-browser` サイドカーも起動し、noVNC を公開します:

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale
```

WebUI の Settings で Pixiv サインインを開始し、noVNC ブラウザーで Pixiv ログインを完了してください。バックエンドがコールバックを受け取り、`refresh_token` を保存します。

停止:

```bat
docker compose down
```

Compose ファイルは `yexca/pixivdownloader:v0.2.0` をビルドでき、`7653:7653` を公開し、永続化のためにローカルの `config/`、`resources/`、`downloads/` をマウントします。

## Windows ローカル実行

プロジェクトフォルダーでインストールします:

```bat
run-install.bat
```

WebUI を起動します:

```bat
run-webui.bat
```

スクリプトは `env\python.exe` と `frontend\dist\index.html` を確認し、バックエンドを起動して <http://127.0.0.1:7653> を開きます。

別のローカルポートを使う場合は、スクリプト実行前に `PIXIVDOWNLOADER_PORT` を設定してください。

## 実行アーキテクチャ

```text
Browser WebUI
  -> FastAPI backend on http://127.0.0.1:7653
  -> SQLite database in resources/
  -> configured download directory
```

主なディレクトリ:

- `backend/`: FastAPI API、サービス、リポジトリ、SQLite マイグレーション、ダウンロードワーカー。
- `frontend/`: React、TypeScript、Vite、Tailwind CSS の WebUI。
- `auth-browser/`: Docker で Pixiv ブラウザーログインを行うサイドカー。
- `config/`: WebUI 設定。`settings.example.json` はコミットされ、`settings.json` はローカル設定を保存します。
- `resources/`: SQLite データベースと静的リソース。
- `legacy/pyqt/`: アーカイブ済み PyQt デスクトップアプリ。現在の実行環境には含まれません。

## 設定移行

WebUI のデフォルト設定:

```text
config\settings.example.json
```

ローカル設定とシークレット:

```text
config\settings.json
```

旧 `resources\conf\settings.json` は自動では読み込まれません。必要な場合は明示的に移行してください:

```bat
env\python.exe tools\migrate_settings_to_config.py
```

`config\settings.json` がすでに存在する場合は `--overwrite` を使用できます。

## 開発

バックエンド開発サーバー:

```bat
run-backend-dev.bat
```

フロントエンド開発サーバー:

```bat
run-frontend-dev.bat
```

チェックコマンド:

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

## ドキュメント

- [Documentation index](docs/README.md)
- [Getting Started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [Deployment](docs/deployment.md)
- [Database](docs/database.md)
- [Development Guide](docs/development.md)

## パッケージングメモ

ソースチェックアウトで実行する場合、バックエンドはリポジトリルートからリソースを解決します:

- `config\settings.example.json`
- `config\settings.json`
- `resources\pixiv.sqlite3`
- `frontend\dist`

将来、実行ファイルとしてパッケージ化する場合は、同じ相対構造で実行ファイルの隣にリソースを配置してください。凍結ビルドでは、バックエンドのパス解決は実行ファイルのディレクトリを基準にします。

## 免責事項

本ツールは個人的な学習、研究、バックアップ目的でのみ使用してください。Pixiv の利用規約を遵守し、大量ダウンロードやコンテンツ再配布には使用しないでください。
