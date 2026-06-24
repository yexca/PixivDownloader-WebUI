# PixivDownloader-SQLite

> Languages: [English](README.md) | [简体中文](README.zh-CN.md)

PixivDownloader-SQLite は、Windows でローカル実行する Pixiv ダウンロード管理ツールです。現在は旧 PyQt6 デスクトップアプリからローカル WebUI へ移行中で、FastAPI バックエンド、React + TypeScript フロントエンド、SQLite データベースを使用します。

## 主な機能

- Pixiv ユーザー ID または作品 ID からダウンロードジョブを作成。
- WebUI でダウンロード先と Pixiv `refresh_token` を管理。
- SQLite にジョブ、アーティスト、作品、ファイル状態を保存。
- 旧 `resources/pixiv.db` の `pic` テーブルを新しいスキーマへ移行。
- `run-webui.bat` から WebUI をローカル起動。外部データベースサーバーは不要です。
- `run-gui.bat` から旧 PyQt デスクトップ GUI も起動できます。

## 実行アーキテクチャ

```text
run-webui.bat
  -> env\python.exe -m backend.app
  -> http://127.0.0.1:7653 で FastAPI を起動
  -> frontend\dist を配信
  -> ブラウザーで WebUI を開く
```

主なディレクトリ:

- `backend/`: FastAPI API、サービス、リポジトリ、SQLite マイグレーション、ダウンロードワーカー。
- `frontend/`: React、TypeScript、Vite、Tailwind CSS の WebUI。
- `resources/`: ローカル設定と SQLite データベース。
- `app/`: `run-gui.bat` から起動できる旧 PyQt コード。現在の主なユーザー向け画面は WebUI です。

## インストール

プロジェクトフォルダーで実行します:

```bat
run-install.bat
```

インストーラーの処理:

1. Miniconda がない場合は `%UserProfile%\Miniconda3` にインストール。
2. ローカル `env` 環境を作成。
3. Python 依存関係を `env` にインストール。
4. `npm` でフロントエンド依存関係をインストール。
5. フロントエンドを `frontend\dist` にビルド。

インストーラーはグローバル Python を使用しません。Node.js は現在、システム PATH 上の `npm` を検出します。見つからない場合は <https://nodejs.org/> から Windows LTS 版をインストールしてください。

## 起動

WebUI:

```bat
run-webui.bat
```

スクリプトは `env\python.exe` と `frontend\dist\index.html` を確認し、バックエンドを起動して <http://127.0.0.1:7653> を開きます。

旧 PyQt GUI:

```bat
run-gui.bat
```

スクリプトは `main.py` から旧 PyQt デスクトップ画面を起動します。

別のローカルポートを使う場合は、スクリプト実行前に `PIXIVDOWNLOADER_PORT` を設定してください。

## Docker Compose

公開済みイメージを同じローカルポートで起動します:

```bat
docker compose up -d
```

Compose ファイルは `yexca/pixivdownloader:v0.2.0` を使用およびビルドでき、`7653:7653` を公開し、永続化のためにローカルの `resources/` と `downloads/` をマウントします。

```bat
docker compose build
```

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

- [Project overview](docs/project-overview.md)
- [WebUI architecture](docs/webui-architecture.md)
- [Database migrations](docs/database-migrations.md)
- [UI verification notes](docs/ui-verification.md)

## パッケージングメモ

ソースチェックアウトで実行する場合、バックエンドはリポジトリルートからリソースを解決します:

- `resources\conf\settings.json`
- `resources\pixiv.db`
- `frontend\dist`

将来、実行ファイルとしてパッケージ化する場合は、同じ相対構造で実行ファイルの隣にリソースを配置してください。凍結ビルドでは、バックエンドのパス解決は実行ファイルのディレクトリを基準にします。

## 免責事項

本ツールは個人的な学習、研究、バックアップ目的でのみ使用してください。Pixiv の利用規約を遵守し、大量ダウンロードやコンテンツ再配布には使用しないでください。
