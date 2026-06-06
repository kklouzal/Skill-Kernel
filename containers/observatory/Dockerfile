FROM node:24-slim AS build

WORKDIR /ui

COPY sidecar/autoskill/observatory/package*.json ./
RUN npm ci

COPY sidecar/autoskill/observatory ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine

ENV SKILLKERNEL_OBSERVATORY_PORT=8757

COPY docker/observatory/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /ui/dist /usr/share/nginx/html/admin
COPY containers/observatory/entrypoint.sh /app/entrypoint.sh
COPY containers/observatory/healthcheck.py /app/healthcheck.py

USER root
RUN apk add --no-cache python3 \
    && chmod +x /app/entrypoint.sh /app/healthcheck.py \
    && chown -R nginx:nginx /app /usr/share/nginx/html/admin
USER nginx

EXPOSE 8757

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
HEALTHCHECK --interval=10s --timeout=5s --retries=12 CMD ["python3", "/app/healthcheck.py", "observatory"]
