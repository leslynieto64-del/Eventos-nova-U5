# Eventos Nova — imagen de la aplicación y de las pruebas (Docker Compose: DB + App + Tests).
#   target «app»   : API, migraciones y trabajador del Outbox (solo dependencias de ejecución).
#   target «tests» : imagen anterior + dependencias de desarrollo y el proyecto completo que la suite verifica
#                    (el contexto filtrado por .dockerignore: sin .env, .git, .venv ni exportaciones pesadas de BPMN).
# No se copia ningún secreto: `.env` está en .dockerignore y la configuración llega por variables de entorno.

FROM python:3.13-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src
WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY migraciones ./migraciones
COPY scripts ./scripts
COPY src ./src

RUN useradd --create-home --uid 10001 eventosnova && chown -R eventosnova /app
USER eventosnova
EXPOSE 8000
# Las plataformas de despliegue inyectan el puerto en PORT; sin ella se usa 8000 (Docker Compose lo conserva).
CMD ["sh", "-c", "exec python -m uvicorn api.main:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}"]


FROM app AS tests
USER root
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY . .
RUN chown -R eventosnova /app
USER eventosnova
# Ejecutor de la suite: pytest (pytest.ini); ejecuta también las pruebas existentes basadas en unittest.TestCase.
CMD ["python", "-m", "pytest"]
