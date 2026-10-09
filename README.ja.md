# PixivDownloader WebUI

> Languages: [English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

> 注意: 現在のアプリケーション UI は英語のみ対応しています。i18n / 多言語 UI の追加は、今後の開発状況に応じて検討します。

PixivDownloader WebUI は、Pixiv 作品のバックアップ、ワークフロー自動化、ライブラリ管理をローカル環境で行うための WebUI です。FastAPI バックエンド、React + TypeScript フロントエンド、ローカル SQLite データベースで構成されています。

このリポジトリは PixivDownloader の WebUI プロジェクトです。[yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite) が生成した `pixiv.db` データベースのインポートに対応していますが、そのプロジェクトのソースコードは同梱していません。

## 機能

- Dashboard でワークフロー実行、トリガー状態、キュー負荷、ライブラリの注意項目を確認できます。
- 再利用可能なワークフロー定義を作成し、手動実行またはスケジュール実行できます。
- Pixiv のアーティスト ID または作品 ID からショートカットダウンロードを作成できます。
- ライブラリ、アーティスト詳細、作品ファイル状態、ローカルタグ、再試行、同期、削除操作を扱えます。
- キューの一時停止/再開、ジョブの再試行/再実行/キャンセル、一括キャンセル、WebSocket によるリアルタイム進捗表示に対応しています。
- ダウンロード先、Pixiv 認証、リクエスト/ファイルダウンロード遅延、並行数、空き容量保護、既存ファイル処理、ライブラリ更新確認間隔を設定できます。
- Docker 環境では、任意の noVNC 認証ブラウザ sidecar を使って Pixiv ログインを行えます。
- Settings から [yexca/PixivDownloader-SQLite](https://github.com/yexca/PixivDownloader-SQLite) の `pixiv.db` を明示的にインポートできます。
- Docker Compose とローカル Windows スクリプトの両方で実行できます。

## 推奨実行方法: Docker Compose

WebUI を起動します:

```bat
docker compose up -d
```

開きます:

```text
http://127.0.0.1:7653
```

デフォルトの Compose 起動では WebUI のみが実行され、公開ポートは localhost のみにバインドされます。Pixiv ブラウザ認証が必要な場合は、[デプロイ手順](docs/deployment.md#browser-authentication)に従って非公開の `.env` にランダムな共有トークンと VNC パスワードを設定してから、任意の `pixiv-auth-browser` sidecar を起動してください:

```bat
docker compose --profile auth up -d pixiv-auth-browser
```

noVNC を開き、VNC パスワードを入力します:

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale
```

WebUI の Settings で Pixiv サインインを開始したら、noVNC ブラウザで Pixiv ログインを完了してください。sidecar がコールバックをバックエンドへ送信し、バックエンドが `refresh_token` を自動保存します。

token の設定とテストが完了したら、認証ブラウザを停止できます:

```bat
docker compose stop pixiv-auth-browser
```

WebUI を停止します:

```bat
docker compose down
```

Compose ファイルは `yexca/pixivdownloader:v0.2.0` をビルドでき、`127.0.0.1:7653:7653` を公開し、永続化のためにローカルの `config/`、`resources/`、`downloads/` をマウントします。`auth` profile では `yexca/pixivdownloader-auth-browser:v0.2.0` もビルドおよび実行できます。

## ローカル Windows 実行

プロジェクトフォルダーでインストールします:

```bat
run-install.bat
```

実行します:

```bat
run-webui.bat
```

スクリプトは `env\python\python.exe` と `frontend\dist\index.html` の存在を確認し、バックエンドを起動して <http://127.0.0.1:7653> を開きます。

別のローカルポートを使う場合は、スクリプト実行前に `PIXIVDOWNLOADER_PORT` を設定してください。

## 実行アーキテクチャ

```text
Browser WebUI
  -> http://127.0.0.1:7653 の FastAPI backend
  -> ワークフロー実行、トリガー、キュー、ジョブ、worker
  -> resources/ 内の SQLite database
  -> 設定されたダウンロード先
```

主なディレクトリ:

- `backend/`: FastAPI API、サービス、リポジトリ、SQLite マイグレーション、ワークフローランナー、スケジューラー、ダウンロード worker。
- `frontend/`: React、TypeScript、Vite、Tailwind CSS WebUI。
- `auth-browser/`: Pixiv ブラウザ認証用の任意 Docker sidecar。
- `config/`: WebUI 設定。`settings.example.json` はコミットされ、`settings.json` はローカルユーザー設定と秘密情報を保存します。
- `resources/`: SQLite データベース、インポートされた PixivDownloader-SQLite データベース、キャッシュ、静的リソース。
- `tools/`: 過去の設定移行などのメンテナンス補助ツール。
- `tests/`: バックエンド回帰テスト。

## 設定移行

WebUI のデフォルト設定:

```text
config\settings.example.json
```

ローカル設定と秘密情報:

```text
config\settings.json
```

以前の `resources\conf\settings.json` は自動では読み込まれません。必要な場合は明示的に移行してください:

```bat
env\python\python.exe tools\migrate_settings_to_config.py
```

`config\settings.json` が既に存在する場合は `--overwrite` を使用できます。

## 開発

バックエンド開発サーバー:

```bat
env\python\python.exe -m uvicorn backend.app:create_app --factory --reload --host 127.0.0.1 --port 7653
```

フロントエンド開発サーバー:

```bat
cd frontend
npm run dev
```

チェックコマンド:

```bat
env\python\python.exe -m ruff format --check .
env\python\python.exe -m ruff check .
env\python\python.exe -m pytest
```

```bat
cd frontend
npm run lint
npm run typecheck
npm run test
npm run build
```

## ドキュメント

- [Documentation index](docs/README.md)
- [Getting Started](docs/getting-started.md)
- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [API Reference](docs/api-reference.md)
- [Deployment](docs/deployment.md)
- [Database](docs/database.md)
- [Development Guide](docs/development.md)
- [Verification](docs/verification.md)

## パッケージングメモ

ソースチェックアウトで実行する場合、バックエンドはリポジトリルートからリソースを解決します:

- `config\settings.example.json`
- `config\settings.json`
- `resources\pixiv.sqlite3`
- `frontend\dist`

将来、凍結実行ファイルとして配布する場合は、同じ相対構造で実行ファイルの隣にこれらのリソースを配置してください。凍結実行時、バックエンドのパス解決は実行ファイルのディレクトリを基準にします。

## 免責事項

このツールは、個人の学習、研究、またはデータバックアップ目的でのみ使用してください。Pixiv の利用規約を守り、過度な一括ダウンロードやコンテンツの再配布には使用しないでください。

検証結果と互換性の詳細は [Verification](docs/verification.md) と [Repair Report](docs/repair-report.md) を参照してください。リモートアクセスには SSH トンネルを利用してください。
