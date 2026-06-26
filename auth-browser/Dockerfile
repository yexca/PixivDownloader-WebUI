FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    CHROMIUM_PATH=/usr/bin/chromium \
    PIXIV_AUTH_BROWSER_PORT=7654

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium \
        fluxbox \
        novnc \
        python3-websockify \
        x11vnc \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY package.json ./
RUN npm install --omit=dev

COPY src ./src
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

EXPOSE 6080 7654

CMD ["./start.sh"]
