"""Reloj de negocio (TP-06 del cierre de alcance aprobado: zona horaria America/Mexico_City).

Verificación del 28/10/2026: la API y el trabajador usaban `datetime.now()`, es decir, la hora del sistema operativo (UTC en los
contenedores), mientras las fechas del dominio, de la API y de la base son horas de pared sin zona de la Ciudad de México. Estas pruebas
fijan que API, trabajador y Outbox comparten `application.reloj.reloj_negocio` y que su resultado es la hora de pared de
America/Mexico_City sin zona. No se convierte ninguna fecha almacenada ni recibida.
Ejecutar desde la raíz:  python -m unittest tests.test_reloj_negocio -v"""
import inspect, os, sys, unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from api import dependencias                                                       # noqa: E402
from application.reloj import ZONA_NEGOCIO, reloj_negocio                          # noqa: E402
from infrastructure.persistencia import outbox_sql, trabajador_outbox              # noqa: E402


class RelojDeNegocio(unittest.TestCase):
    def test_la_zona_es_la_aprobada_en_tp_06(self):
        self.assertEqual(ZONA_NEGOCIO, 'America/Mexico_City')

    def test_convierte_un_instante_utc_a_la_hora_de_pared_de_la_ciudad_de_mexico_sin_zona(self):
        r = reloj_negocio(datetime(2026, 10, 29, 1, 36, tzinfo=timezone.utc))
        self.assertEqual(r, datetime(2026, 10, 28, 19, 36))                         # UTC−6 (sin horario de verano desde 2022)
        self.assertIsNone(r.tzinfo)
        self.assertEqual(reloj_negocio(datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)), datetime(2026, 7, 1, 6, 0))

    def test_cruza_la_medianoche_igual_que_el_calendario_de_negocio(self):             # 20:00 UTC del 31/10 sigue siendo 14:00 del 31/10
        self.assertEqual(reloj_negocio(datetime(2026, 11, 1, 5, 59, 59, tzinfo=timezone.utc)), datetime(2026, 10, 31, 23, 59, 59))
        self.assertEqual(reloj_negocio(datetime(2026, 11, 1, 6, 0, 0, tzinfo=timezone.utc)), datetime(2026, 11, 1, 0, 0, 0))

    def test_el_reloj_actual_coincide_con_la_hora_de_pared_de_mexico_y_no_con_utc(self):
        ahora_mx, utc = reloj_negocio(), datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertLess(abs((ahora_mx - (utc - timedelta(hours=6))).total_seconds()), 5)
        self.assertGreater(abs((ahora_mx - utc).total_seconds()), 5 * 3600)


class ApiTrabajadorYOutboxUsanElMismoReloj(unittest.TestCase):
    def test_la_dependencia_de_la_api_entrega_el_reloj_de_negocio(self):
        self.assertIs(dependencias.obtener_reloj(), reloj_negocio)

    def test_el_trabajador_usa_por_omision_el_reloj_de_negocio(self):
        self.assertIs(inspect.signature(trabajador_outbox.ejecutar).parameters['reloj'].default, reloj_negocio)

    def test_el_despachador_del_outbox_usa_por_omision_el_reloj_de_negocio(self):
        self.assertIs(inspect.signature(outbox_sql.DespachadorOutboxSQL.__init__).parameters['reloj'].default, reloj_negocio)

    def test_el_codigo_de_produccion_ya_no_usa_datetime_now(self):
        raiz = os.path.join(os.path.dirname(__file__), '..', 'src')
        for carpeta in ('api', 'application', 'domain', 'infrastructure'):
            for dirpath, _, archivos in os.walk(os.path.join(raiz, carpeta)):
                for nombre in archivos:
                    if nombre.endswith('.py'):
                        with open(os.path.join(dirpath, nombre), encoding='utf-8') as f:
                            texto = f.read()
                        with self.subTest(archivo=nombre):
                            self.assertNotIn('datetime.now(', texto.replace('datetime.now(timezone.utc)', ''))
                            self.assertNotIn('datetime.now\n', texto)
                            self.assertNotIn('= datetime.now)', texto)


if __name__ == '__main__':
    unittest.main()
