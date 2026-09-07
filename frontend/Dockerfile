# ==============================================================================
# Multi-stage Production Dockerfile for React SPA Frontend
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Compile Assets
# ------------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first for caching layers
COPY package.json ./
RUN npm install --frozen-lockfile || npm install

# Copy source and build static files
COPY . .
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Serve Assets with Nginx
# ------------------------------------------------------------------------------
FROM nginx:alpine AS runner

# Copy built assets to default Nginx root path
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy a lightweight default nginx server config for Single Page Apps (handling routing)
COPY <<EOF /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html index.htm;
        try_files \$uri \$uri/ /index.html;
    }

    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
EOF

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
