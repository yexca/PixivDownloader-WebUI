# PyQt6 图像数据收集与管理系统 (Pixiv下载器)

> Language / 言語: [English](README.md) | [日本語](README.ja.md)

这是一个使用 **PyQt6** 和 **Python** 开发的 Windows 桌面应用程序。它能自动收集特定 Pixiv 画师的图像数据，并使用本地 **SQLite** 数据库进行管理

本项目最初使用 MySQL 开发，后为了实现更轻量化、便携性以及无服务器（Serverless）的体验，重构为使用 SQLite

MySQL 版本仓库: <https://github.com/yexca/PixivDownloader-MySQL>

## 主要功能

* **友好的用户界面(GUI):** 基于 PyQt6 构建的简洁明了的操作界面
* **自动数据收集:** 自动下载指定画师的作品
* **本地数据库管理:** 所有收集到的元数据（如 ID、URL 等）都存储在本地 SQLite 数据库中，易于管理和查询
* **轻量与便携:** 采用 SQLite，无需安装独立的数据库服务器，使应用更易于使用和备份

## 技术栈

* **Python 3**
* **PyQt6:** 用于构建桌面应用 GUI
* **SQLite3:** 用于轻量级的本地数据存储

## 如何运行

1.  **克隆仓库:**
    ```bash
    git clone https://github.com/yexca/PixivDownloader-SQLite.git
    cd PixivDownloader-SQLite
    ```

2.  **安装依赖:**
    ```bash
    pip install PyQt6
    ```

3.  **运行程序:**
    ```bash
    python main.py
    ```

## 重要声明

本工具仅供**个人学习、研究或数据备份**使用。请务必遵守 Pixiv 的服务条款 (Terms of Service)。开发者不对任何对本应用的滥用行为或任何违反 Pixiv 政策的行为负责。请勿使用此工具进行批量下载或分发内容。
