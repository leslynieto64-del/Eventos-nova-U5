"""Incremento 2.2 — evalúa en PostgreSQL 18 las expresiones REALES de los CHECK definidos en los metadatos.

Solo lectura: no crea tablas, no inserta datos y no altera el esquema. Cada expresión se extrae de
`infrastructure.esquema_postgresql.metadata` y se evalúa con `SELECT (<expresión>) IS NOT FALSE` sobre valores literales
(una restricción CHECK acepta una fila cuando la expresión es verdadera o NULL). La conexión se abre con
`default_transaction_read_only=on`. Si el servicio PostgreSQL no está disponible, las pruebas se omiten de forma explícita:
la validación del esquema no depende de Docker para el resto de la suite.

`evaluar_todo()` devuelve cada caso (valor, esperado, real) para documentar el resultado."""
import os, re, sys, unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'src'))
import sqlalchemy as sa                                                              # noqa: E402
from infrastructure.esquema_postgresql import metadata                               # noqa: E402

VALORES_IMPORTE = [('-1', False), ('-0.01', False), ('0', True), ('0.00', True), ('1', True), ('125.50', True),
                   ('12.345678901234', True), ('123456789012345678901234567890.5', True),
                   ('NaN', False), ('Infinity', False), ('-Infinity', False)]


def _url():
    url = os.environ.get('DATABASE_URL')
    ruta = RAIZ / '.env'
    if not url and ruta.is_file():
        for linea in ruta.read_text(encoding='utf-8').splitlines():
            if linea.startswith('DATABASE_URL='):
                url = linea.split('=', 1)[1].strip()
    return url.replace('postgresql+psycopg://', 'postgresql://') if url else None


def _conectar():
    import psycopg
    url = _url()
    if not url:
        raise unittest.SkipTest('DATABASE_URL no está definida')
    try:
        return psycopg.connect(url, connect_timeout=3, options='-c default_transaction_read_only=on', autocommit=True)
    except Exception as e:                                                        # servicio detenido o sin red
        raise unittest.SkipTest(f'PostgreSQL no disponible ({type(e).__name__})')


def _checks_de_importes():
    for t in metadata.sorted_tables:
        num = [c for c in t.columns if isinstance(c.type, sa.Numeric)]
        for ck in t.constraints:
            if isinstance(ck, sa.CheckConstraint):
                expr = str(ck.sqltext)
                usadas = [c for c in num if re.search(rf'\b{c.name}\b', expr)]
                if usadas and "'NaN'" in expr:      # CHECK de validez del importe; los de grupo («todo o nada») son estructurales
                    yield t, ck, expr, usadas


def _evaluar(con, expr, valores):
    columnas = ', '.join(f'%s::numeric AS {n}' for n in valores)
    sql = f'SELECT ({expr}) IS NOT FALSE FROM (SELECT {columnas}) AS t'
    return con.execute(sql, list(valores.values())).fetchone()[0]


def evaluar_todo():
    """Lista de filas {restriccion, columna, valor, esperado, real, ok}. Lanza SkipTest sin conexión."""
    filas = []
    with _conectar() as con:
        # --- importes (numéricos)
        for t, ck, expr, usadas in _checks_de_importes():
            for col in usadas:
                otras = {c.name: '1' for c in usadas if c is not col}
                casos = list(VALORES_IMPORTE)
                if col.nullable:
                    casos.append((None, True))
                for valor, esperado in casos:
                    real = _evaluar(con, expr, {col.name: valor, **otras})
                    filas.append(dict(restriccion=f'{t.name}.{ck.name}', columna=col.name, valor=valor, esperado=esperado,
                                      real=real, ok=real == esperado))
                if not col.nullable:       # NULL: el CHECK lo deja pasar (NULL), pero NOT NULL de la columna lo rechaza
                    real = _evaluar(con, expr, {col.name: None, **otras})
                    filas.append(dict(restriccion=f'{t.name}.{ck.name}', columna=col.name, valor='NULL (NOT NULL en la columna)',
                                      esperado=True, real=real, ok=real is True and col.nullable is False))
        # --- enteros y texto
        def check(tabla, nombre):
            return next(str(c.sqltext) for c in metadata.tables[tabla].constraints
                        if isinstance(c, sa.CheckConstraint) and str(c.name).endswith(nombre))

        def entero(tabla, nombre, columna, casos, tipo='integer'):
            expr = check(tabla, nombre)
            for valor, esperado in casos:
                real = con.execute(f'SELECT ({expr}) IS NOT FALSE FROM (SELECT %s::{tipo} AS {columna}) AS t', [valor]).fetchone()[0]
                filas.append(dict(restriccion=f'{tabla}.{nombre}', columna=columna, valor=valor, esperado=esperado, real=real,
                                  ok=real == esperado))
        # BIGINT: el máximo del límite técnico (2^63-1) y un valor mayor que INTEGER son válidos para el CHECK de positividad
        entero('evento', 'invitados_positivo', 'invitados_aproximados',
               [(-1, False), (0, False), (1, True), (2147483647, True), (2147483648, True), (9223372036854775807, True)], 'bigint')
        entero('solicitud_cambio', 'datos_propuestos_invitados_positivo', 'datos_propuestos_invitados',
               [(-1, False), (0, False), (1, True), (None, True), (2147483648, True), (9223372036854775807, True)], 'bigint')
        entero('version_propuesta', 'numero_positivo', 'numero', [(-1, False), (0, False), (1, True), (7, True)])
        entero('outbox_evento', 'intentos_no_negativos', 'intentos', [(-1, False), (0, True), (3, True)])

        def texto(tabla, nombre, columnas, casos):
            expr = check(tabla, nombre)
            sel = ', '.join(f'%s::text AS {c}' for c in columnas)
            for valores, esperado in casos:
                real = con.execute(f'SELECT ({expr}) IS NOT FALSE FROM (SELECT {sel}) AS t', list(valores)).fetchone()[0]
                filas.append(dict(restriccion=f'{tabla}.{nombre}', columna='/'.join(columnas), valor=repr(valores),
                                  esperado=esperado, real=real, ok=real == esperado))
        texto('evento', 'datos_no_vacios', ['tipo', 'lugar'],
              [(('Boda', 'Salón'), True), (('', 'Salón'), False), (('Boda', ''), False), (('123', '456'), True),
               (('Boda 2', 'Av. Juárez #123'), True), (('  ', 'x'), True)])        # solo espacios: el dominio también lo acepta
        texto('solicitud_cambio', 'datos_propuestos_no_vacios', ['datos_propuestos_tipo', 'datos_propuestos_lugar'],
              [((None, None), True), (('Boda', 'Salón'), True), (('', 'Salón'), False), (('Boda', ''), False), (('123', '456'), True)])
    return filas


class ChecksEnPostgreSQL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.filas = evaluar_todo()                                                # SkipTest si no hay base de datos

    def test_hay_casos_para_cada_restriccion_numerica(self):
        restricciones = {f['restriccion'] for f in self.filas}
        for t, ck, _, _ in _checks_de_importes():
            self.assertIn(f'{t.name}.{ck.name}', restricciones)
        for nombre in ('evento.invitados_positivo', 'version_propuesta.numero_positivo', 'outbox_evento.intentos_no_negativos',
                       'evento.datos_no_vacios'):
            self.assertIn(nombre, restricciones)

    def test_cada_caso_coincide_con_lo_esperado(self):
        malos = [f for f in self.filas if not f['ok']]
        self.assertEqual(malos, [], f'{len(malos)} casos no coinciden')

    def test_nan_infinity_y_negativos_se_rechazan_en_todos_los_importes(self):
        for f in self.filas:
            if f['valor'] in ('NaN', 'Infinity', '-Infinity', '-1', '-0.01'):
                self.assertFalse(f['real'], f)

    def test_el_limite_tecnico_de_bigint_se_acepta_y_el_siguiente_no_cabe_en_la_columna(self):
        # Solo SELECT sobre literales (conexión de solo lectura): demuestra por qué el dominio rechaza 2^63 antes de persistir.
        from domain.valores import MAXIMO_TECNICO_BIGINT
        self.assertEqual(MAXIMO_TECNICO_BIGINT, 9223372036854775807)
        with _conectar() as con:
            self.assertEqual(con.execute('SELECT %s::bigint', [MAXIMO_TECNICO_BIGINT]).fetchone()[0], MAXIMO_TECNICO_BIGINT)
            for fuera in (MAXIMO_TECNICO_BIGINT + 1, 10 ** 30):
                with self.assertRaises(Exception) as ctx:
                    con.execute('SELECT %s::bigint', [fuera])
                self.assertIn('out of range', str(ctx.exception))

    def test_cero_y_decimales_sin_limite_se_aceptan(self):
        for f in self.filas:
            if f['valor'] in ('0', '0.00', '12.345678901234', '123456789012345678901234567890.5'):
                self.assertTrue(f['real'], f)


if __name__ == '__main__':
    unittest.main()
