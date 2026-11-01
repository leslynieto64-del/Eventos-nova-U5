"""Apoyo de las pruebas de integración con PostgreSQL.

Usan SIEMPRE la base de PRUEBAS (`TEST_DATABASE_URL`, nombre terminado en `_test`), nunca la de desarrollo. La base se crea si no
existe (sin borrar nada) y se migra una vez por proceso. Entre pruebas se vacían solo las tablas de la base de pruebas.

Si PostgreSQL no está disponible, las pruebas se OMITEN con un mensaje explícito; si la variable de entorno
`EVENTOSNOVA_REQUIERE_BD=1` está definida (CI, Docker Compose) la falta de la base es un FALLO, no una omisión."""
import atexit, os, sys, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import sqlalchemy as sa                                                                   # noqa: E402
from infrastructure.persistencia import configuracion as C                                # noqa: E402
from infrastructure.persistencia.conexion import AlmacenSQL, crear_motor                  # noqa: E402
from infrastructure.persistencia.preparacion import asegurar_base_de_pruebas, limpiar_base_de_pruebas   # noqa: E402

_MOTOR = None
_ERROR = None
_GRACIA_SESIONES_AJENAS = 15.0                  # segundos


class BaseDePruebasNoAislada(AssertionError):
    """La base de pruebas no es exclusiva de la suite. SIEMPRE es un fallo (nunca una omisión): las pruebas vacían sus tablas y
    cualquier otro consumidor (trabajador del Outbox, API) se llevaría eventos del Outbox o alteraría el estado de los agregados."""


def _exigir_nombre_propio(url: str) -> None:
    """Antes de conectar, migrar o vaciar nada: la suite nunca usa la base de las pruebas manuales."""
    nombre = sa.make_url(url).database or ''
    if 'manual' in nombre:
        raise BaseDePruebasNoAislada(
            f'TEST_DATABASE_URL apunta a «{nombre}», la base de las pruebas manuales (docker-compose.manual-test.yml): la suite la '
            'vaciaría y su trabajador/API manual interferirían con el Outbox. Use una base propia, p. ej. «eventosnova_test».')


def _exigir_sin_sesiones_ajenas(url: str, motor: sa.Engine) -> None:
    """La base de pruebas debe ser exclusiva de esta ejecución: sin trabajadores, APIs ni otro pytest conectados."""
    nombre = sa.make_url(url).database or ''
    # La sesión de una ejecución recién terminada (el paso anterior del CI, otra pasada de pytest) tarda unos instantes en
    # desaparecer de pg_stat_activity: se concede un plazo de gracia; un trabajador o una API vivos no desaparecen.
    limite = time.monotonic() + _GRACIA_SESIONES_AJENAS
    while True:
        with motor.connect() as con:
            ajenas = con.execute(sa.text(
                'select pid, coalesce(application_name, \'\'), coalesce(client_addr::text, \'local\') from pg_stat_activity '
                'where datname = current_database() and pid <> pg_backend_pid()')).all()
        if not ajenas or time.monotonic() >= limite:
            break
        time.sleep(0.5)
    if ajenas:
        detalle = '; '.join(f'pid {p} ({app or "sin nombre"}, {origen})' for p, app, origen in ajenas)
        raise BaseDePruebasNoAislada(
            f'La base de pruebas «{nombre}» tiene otras sesiones conectadas ({detalle}): un trabajador del Outbox, una API u otra '
            'ejecución de pytest la están usando. Deténgalos o use otra base; compartirla produce fallos intermitentes.')


def motor_de_pruebas() -> sa.Engine:
    """Motor de la base de pruebas, preparada una sola vez por proceso. Lanza SkipTest (o falla si se exige la base)."""
    global _MOTOR, _ERROR
    if _MOTOR is not None:
        return _MOTOR
    if _ERROR is None:
        try:
            url = C.url_pruebas()
            if not url:
                raise RuntimeError('TEST_DATABASE_URL no está definida')
            if not C.es_base_local_de_pruebas(url):
                raise RuntimeError('TEST_DATABASE_URL no apunta a una base local cuyo nombre termine en «_test»')
            _exigir_nombre_propio(url)
            asegurar_base_de_pruebas(url)
            motor = crear_motor(url)
            with motor.connect() as con:
                con.execute(sa.text('select 1'))
            _exigir_sin_sesiones_ajenas(url, motor)
            _MOTOR = motor
            atexit.register(motor.dispose)                          # cierra el pool al terminar el proceso
            return _MOTOR
        except BaseDePruebasNoAislada:
            raise
        except Exception as e:                                                             # servicio detenido, sin red, etc.
            _ERROR = f'{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ""}'
    if os.environ.get('EVENTOSNOVA_REQUIERE_BD') == '1':
        raise AssertionError(f'La base de pruebas es obligatoria (EVENTOSNOVA_REQUIERE_BD=1) y no está disponible: {_ERROR}')
    raise unittest.SkipTest(f'PostgreSQL de pruebas no disponible ({_ERROR})')


class BaseConBD(unittest.TestCase):
    """Cada prueba arranca con la base de pruebas vacía y un almacén nuevo."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.motor = motor_de_pruebas()

    def setUp(self):
        super().setUp()
        limpiar_base_de_pruebas(self.motor)
        self.almacen = AlmacenSQL(self.motor)

    def contar(self, tabla: str) -> int:
        with self.motor.connect() as con:
            return con.execute(sa.text(f'select count(*) from "{tabla}"')).scalar()
