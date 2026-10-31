# CI/CD y despliegue (fase final, Etapas 10 y 11)

## Estado real

| Elemento | Estado | Evidencia |
|---|---|---|
| Workflows `ci.yml` y `publicar-imagen.yml` | Escritos y validados **estáticamente** con actionlint (rc=0) | `docker run rhysd/actionlint` sobre `.github/` |
| Ejecución en GitHub Actions | **No ejecutada.** El repositorio local no tiene remoto configurado (`git remote -v` vacío) y no hay `gh` ni credenciales | — |
| Los mismos pasos, ejecutados localmente | Sí: migraciones (una cabeza `0004`, SQL offline), preparación de la base de pruebas, suite con cobertura y mínimo del PIA, `docker compose config`, imágenes, suite dentro de Docker, API sana | `tests/evidencias/ejecucion-pruebas-fase-final-etapa7-20261024.txt`, `cobertura-fase-final-20261024.txt` |
| Despliegue en una plataforma | **No realizado.** No hay plataforma, credenciales ni permisos | — |
| URL del sistema desplegado | **No existe.** No se inventa ninguna | — |

Una validación estática (actionlint) no demuestra que el pipeline funcione en GitHub: eso solo se sabe tras la primera ejecución real.

## CI (`.github/workflows/ci.yml`)

Dos trabajos: `pruebas` (PostgreSQL 18 como servicio efímero, instala dependencias, verifica una sola cabeza de Alembic y el SQL offline, migra, prepara la base de pruebas, ejecuta TODA la suite con cobertura y exige ≥ 80 % de sentencias) y `docker` (valida Compose, construye imágenes, ejecuta la suite dentro de Docker y comprueba `/ready`, `/health` y `/docs`). `EVENTOSNOVA_REQUIERE_BD=1` hace que la falta de PostgreSQL falle las pruebas en vez de omitirlas. La contraseña del servicio es la de una base efímera del job, no un secreto real.

### Cómo validarlo en GitHub (pasos manuales)

1. Revisar y versionar los archivos (ver la lista de abajo); **no se hizo ningún commit ni push**.
2. Crear el repositorio remoto, `git remote add origin <URL>` y publicar la rama.
3. Abrir Actions → ejecutar `CI` (disparo manual `workflow_dispatch` o por `push`/`pull_request`) y confirmar que ambos trabajos terminan en verde. Si algo falla, el paso «Registros de los servicios» muestra los logs de Compose.
4. Opcional: el workflow de publicación de imagen necesita permisos de paquetes y, si se desea el disparo de un despliegue, el secreto `DEPLOY_HOOK_URL`.

### Archivos que la CI necesita versionados

`.github/`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, `alembic.ini`, `migraciones/`, `scripts/`, `src/` (incluido `src/infrastructure/persistencia/` y `src/infrastructure/datos_demo/`), `tests/`, `datos/`, `docs/`, `requirements*.txt`, `.coveragerc`, `README.md` y el cierre de alcance aprobado. **No** deben subirse `.env`, `.coverage`, `htmlcov/` ni `.venv/`.

## Despliegue funcional

El PIA pide un despliegue con Swagger/OpenAPI accesible. La aplicación está lista para cualquier plataforma que ejecute contenedores y ofrezca PostgreSQL gestionado:

| Pieza | Configuración |
|---|---|
| Imagen | `Dockerfile`, objetivo `app` (sin dependencias de desarrollo ni secretos). Escucha en `$PORT` (8000 por omisión) |
| Base de datos | PostgreSQL 18 gestionado. Variable `DATABASE_URL` (se aceptan `postgres://`, `postgresql://` y `postgresql+psycopg://`) |
| Modo de persistencia | `EVENTOSNOVA_PERSISTENCIA=postgresql` |
| Paso previo | `python -m alembic upgrade head` (comando de pre-despliegue o *release*) |
| Proceso web | el `CMD` de la imagen (`uvicorn api.main:app`) |
| Trabajador del Outbox | segundo proceso con `python -m infrastructure.persistencia.trabajador_outbox --intervalo 2`; con `EVENTOSNOVA_DESPACHO_EN_LINEA=1` (por omisión) la API también despacha dentro de la petición. **Es obligatorio**: además del Outbox, aplica en cada ciclo la llegada de T (inicio automático y cierre sin contratación, ADR-008); sin él no hay inicio automático |
| Comprobación de salud | `GET /ready` (200 solo con la base disponible y el esquema al día) |
| Swagger / OpenAPI | `/docs` y `/openapi.json` (60 operaciones) |
| Opcional (solo demostración; no afecta la asignación de proveedores, que usa el catálogo) | `EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO=/app/src/infrastructure/datos_demo/disponibilidad_demo.json` |

### Pasos manuales exactos

1. Elegir la plataforma y crear un servicio web desde el `Dockerfile` (objetivo `app`) y una base PostgreSQL 18.
2. Definir `DATABASE_URL` (la entrega la plataforma) y `EVENTOSNOVA_PERSISTENCIA=postgresql` como variables del servicio.
3. Configurar el comando de pre-despliegue `python -m alembic upgrade head`.
4. Crear el segundo servicio (trabajador) con la misma imagen y variables y el comando indicado.
5. Verificar con la URL real que entrega la plataforma: `GET /ready` → 200, `GET /docs` carga, y un flujo de prueba (crear evento, propuesta, contrato y pago).
6. Anotar la URL real en el reporte y la presentación **solo después** de comprobarla.

### Verificación local equivalente (realizada)

`docker compose up -d` levanta `db`, `migrate`, `api` y `worker`; la API quedó sana (`/ready` → `{"estado":"ok","persistencia":"postgresql","base_de_datos":"ok"}`), `/docs` responde 200, `/openapi.json` lista 60 operaciones, un evento creado por HTTP sobrevive al reinicio del contenedor `api`, la imagen respeta `PORT` (probado con `PORT=9123`) y la migración funciona con una URL `postgres://`. Falta lo que requiere recursos externos: ejecución en GitHub, plataforma, credenciales y URL pública.
