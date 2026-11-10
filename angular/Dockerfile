# Axiom Watch: build with Node, serve the static files with nginx.
#   docker build -t axiom-watch .
#   docker run --rm -p 8080:80 -e AXIOM_API_BASE=http://localhost:8000 axiom-watch

# ---- build stage: Node 24 LTS (the Angular 22 CLI needs >= 22.22.3 or >= 24.15)
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx ng build --configuration production

# ---- runtime stage: nginx only, no Node, no source
FROM nginx:1.29-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/40-axiom-config.sh /docker-entrypoint.d/40-axiom-config.sh
COPY --from=build /app/dist/axiom-watch/browser /usr/share/nginx/html
RUN chmod +x /docker-entrypoint.d/40-axiom-config.sh
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
