import os

# pytest carga este fichero antes que los tests, así que estas variables ya
# están puestas cuando se importa la API y config.py monta DB_URL.
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5433"
os.environ["POSTGRES_USER"] = "test"
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["POSTGRES_DB"] = "test"
