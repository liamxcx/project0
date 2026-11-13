# nginx sin root. Escucha en el 8080 porque sin root no puede abrir puertos por
# debajo del 1024.
FROM nginxinc/nginx-unprivileged:1.30-alpine

COPY nginx.conf /etc/nginx/nginx.conf
# Con el mismo nombre que el server de ejemplo de la imagen, para sustituirlo
COPY nginx-cluster.conf /etc/nginx/conf.d/default.conf
# Fuera de conf.d, porque nginx carga solo todo lo que hay ahí y este fichero
# solo vale dentro de un server
COPY nginx-common.conf /etc/nginx/snippets/common.conf
COPY public/ /usr/share/nginx/html/
