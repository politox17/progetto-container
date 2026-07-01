# Dockerfile autosufficiente per Node.js
FROM node:20-slim

WORKDIR /app

# Installazione delle dipedenze
COPY package.json ./
RUN npm install --omit=dev

COPY . .

# Nessuna porta esposta
CMD ["node", "index.js"]
