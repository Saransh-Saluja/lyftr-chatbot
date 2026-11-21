# syntax=docker/dockerfile:1
# ---------- Stage 1: build the static site ------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vite bakes VITE_* variables into the JS bundle at BUILD time (a browser cannot
# read server environment variables), so the API URL is a build argument.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# ---------- Stage 2: serve it with nginx (no Node in the final image) ---------
# "unprivileged" variant runs as a non-root user, so it can't bind port 80:
# we listen on 3000 (see nginx.conf).
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO /dev/null http://127.0.0.1:3000/ || exit 1
