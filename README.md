# PyQt6 Pixiv Downloader & Manager

> 语言 / 言語: [简体中文](README.zh-CN.md) | [日本語](README.ja.md)

A Windows desktop application built with **PyQt6** and **Python** for automatically collecting image data from specific Pixiv artists and managing it in a local **SQLite** database.

This project was originally developed using MySQL but was refactored to use SQLite for a more lightweight, portable, and serverless experience.

MySQL Repo: <https://github.com/yexca/PixivDownloader-MySQL>

## Overview

Home

![main](https://github.com/yexca/picx-images-hosting/raw/master/2026/01-pixiv-downloader-readme/image.73ufnw4wqo.webp)

Setting

![setting](https://github.com/yexca/picx-images-hosting/raw/master/2026/01-pixiv-downloader-readme/settings.32ig9i2nxz.webp)

> Background image: <https://www.pixiv.net/artworks/83273073>

## Features

* **User-Friendly GUI:** A simple and clean interface built with PyQt6.
* **Automatic Data Collection:** Automatically downloads works (images) from the specified artists.
* **Local Database Management:** All collected metadata (ID, URLs) is stored and organized in a local SQLite database.
* **Lightweight & Portable:** By using SQLite, the application runs without needing a separate database server, making it easy to use and back up.

## Technology Stack

* **Python 3**
* **PyQt6:** For the desktop application GUI.
* **SQLite3:** For lightweight, local database storage.

## How to Run

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yexca/PixivDownloader-SQLite.git
    cd PixivDownloader-SQLite
    ```

2.  **Install dependencies:**
    ```bash
    pip install PyQt6
    ```

3.  **Run the application:**
    ```bash
    python main.py
    ```

## Disclaimer

This tool is intended for **personal, academic, or backup purposes only**. Please be responsible and respect Pixiv's Terms of Service. The developer is not responsible for any misuse of this application or for any violations of Pixiv's policies. Do not use this tool for mass-downloading or distribution of content.
