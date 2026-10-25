# nginx sin root. Por eso escucha en el 8080, porque sin root no puede abrir
# puertos por debajo del 1024.
FROM nginxinc/nginx-unprivileged:1.30-alpine

COPY index.html /usr/share/nginx/html/
