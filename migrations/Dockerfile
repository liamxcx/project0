# Flyway con las migraciones dentro, para que el Job del clúster aplique las
# de un commit concreto. La versión es la misma que en docker-compose.yml.
FROM flyway/flyway:13-alpine

COPY *.sql /flyway/migrations/

# Así el Job solo tiene que dar la conexión a la base.
ENV FLYWAY_LOCATIONS=filesystem:/flyway/migrations

CMD ["migrate"]
