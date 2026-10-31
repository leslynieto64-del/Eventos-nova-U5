"""Incremento 2.2 — esquema relacional y migración inicial (sin conexión a la base de datos).

Comprueba los metadatos de SQLAlchemy, las claves foráneas decididas para D-01, la ausencia de precisión/escala/máximos
inventados en los importes y que la revisión 0001 de Alembic coincide con los metadatos (DDL de la migración en modo offline,
sin ejecutar nada). La comparación es de líneas normalizadas: detecta errores de transcripción, no prueba el diseño."""
import ast, io, os, re, sys, unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(RAIZ, 'src'))
import sqlalchemy as sa                                                              # noqa: E402
from sqlalchemy.dialects import postgresql                                           # noqa: E402
from sqlalchemy.schema import CreateTable, CreateIndex                               # noqa: E402
from infrastructure.esquema_postgresql import metadata                               # noqa: E402

RUTA_MIGRACION = os.path.join(RAIZ, 'migraciones', 'versions', '0001_esquema_inicial.py')
IMPORTES = {
    ('version_propuesta', 'costo_total'), ('contrato', 'costo_total'), ('evento', 'revision_pagos_realizados'),
    ('evento', 'revision_saldo_pendiente'), ('solicitud_cambio', 'tarifa_importe'), ('solicitud_cambio', 'costo_proveedor'),
    ('solicitud_servicio_adicional', 'disponibilidad_costo'), ('sustitucion_alternativa', 'disponibilidad_costo'),
    ('sustitucion_proveedor', 'costo_adicional'), ('obligacion_pago', 'importe'), ('pago', 'importe'), ('devolucion', 'importe')}


def _fks():
    return {(t.name, tuple(c.name for c in f.columns)): f for t in metadata.tables.values() for f in t.foreign_key_constraints}


class Importes(unittest.TestCase):
    def test_las_columnas_numericas_monetarias_son_exactamente_las_esperadas(self):
        numericas = {(t.name, c.name) for t in metadata.tables.values() for c in t.columns if isinstance(c.type, sa.Numeric)}
        self.assertEqual(numericas, IMPORTES)

    def test_numeric_sin_precision_ni_escala_y_nunca_float(self):
        for t in metadata.tables.values():
            for c in t.columns:
                with self.subTest((t.name, c.name)):
                    self.assertNotIsInstance(c.type, (sa.Float, sa.REAL, sa.types.DOUBLE_PRECISION))
                    if isinstance(c.type, sa.Numeric):
                        self.assertIsNone(c.type.precision)
                        self.assertIsNone(c.type.scale)

    def test_cada_importe_tiene_un_check_no_negativo_y_finito(self):
        for tabla, columna in sorted(IMPORTES):
            exprs = [str(c.sqltext) for c in metadata.tables[tabla].constraints if isinstance(c, sa.CheckConstraint)
                     and re.search(rf'\b{columna}\b >= 0', str(c.sqltext))]
            with self.subTest((tabla, columna)):
                self.assertTrue(exprs, 'sin CHECK >= 0')
                self.assertTrue(any(f"{columna} <> 'NaN'" in e and f"{columna} <> 'Infinity'" in e for e in exprs),
                                'el CHECK no rechaza NaN e Infinity')

    def test_ningun_check_se_limita_a_mayor_o_igual_a_cero_en_un_importe(self):
        for tabla, columna in IMPORTES:
            for c in metadata.tables[tabla].constraints:
                if isinstance(c, sa.CheckConstraint) and re.search(rf'\b{columna}\b >= 0', str(c.sqltext)):
                    self.assertIn("'NaN'", str(c.sqltext), c.name)

    def test_importes_obligatorios_no_admiten_null_y_los_opcionales_lo_justifican(self):
        anulables = {('evento', 'revision_pagos_realizados'), ('evento', 'revision_saldo_pendiente'),
                     ('solicitud_cambio', 'costo_proveedor'), ('solicitud_servicio_adicional', 'disponibilidad_costo'),
                     ('sustitucion_alternativa', 'disponibilidad_costo'), ('sustitucion_proveedor', 'costo_adicional')}
        for tabla, columna in IMPORTES:
            with self.subTest((tabla, columna)):
                self.assertEqual(metadata.tables[tabla].c[columna].nullable, (tabla, columna) in anulables)

    def test_no_hay_maximos_ni_check_de_escala(self):
        for t in metadata.tables.values():
            for c in t.constraints:
                if isinstance(c, sa.CheckConstraint):
                    e = str(c.sqltext)
                    with self.subTest(c.name):
                        self.assertNotRegex(e, r'<=\s*\d|< \d|scale\(|round\(|trunc\(')


class ClavesForaneas(unittest.TestCase):
    def test_version_vigente_y_aceptada_exigen_pertenencia_no_solo_existencia(self):
        vig = _fks()[('propuesta', ('propuesta_id', 'version_vigente_id'))]
        self.assertEqual([e.target_fullname for e in vig.elements], ['version_propuesta.propuesta_id', 'version_propuesta.version_id'])
        self.assertTrue(vig.deferrable)
        self.assertEqual(vig.initially, 'DEFERRED')                  # propuesta y primera versión en la misma transacción
        self.assertTrue(vig.use_alter)
        ace = _fks()[('contrato', ('propuesta_id', 'version_aceptada_id'))]
        self.assertEqual([e.target_fullname for e in ace.elements], ['version_propuesta.propuesta_id', 'version_propuesta.version_id'])
        self.assertFalse(ace.deferrable)
        unicos = {tuple(c.name for c in u.columns) for u in metadata.tables['version_propuesta'].constraints
                  if isinstance(u, sa.UniqueConstraint)}
        self.assertIn(('propuesta_id', 'version_id'), unicos)         # destino de ambas FK compuestas

    def test_no_queda_la_fk_simple_de_version_vigente(self):
        self.assertNotIn(('propuesta', ('version_vigente_id',)), _fks())

    def test_fk_hacia_raices_confirmadas_por_el_codigo(self):
        esperadas = {
            ('propuesta', ('evento_id',)): 'evento', ('contrato', ('evento_id',)): 'evento',
            ('estado_cuenta', ('contrato_id', 'evento_id')): 'contrato',
            ('solicitud_cambio', ('evento_id',)): 'evento', ('solicitud_servicio_adicional', ('evento_id',)): 'evento',
            ('sustitucion_proveedor', ('evento_id',)): 'evento',
            ('solicitud_cambio', ('estado_cuenta_id', 'contrato_id')): 'estado_cuenta',
            ('solicitud_servicio_adicional', ('estado_cuenta_id', 'contrato_id')): 'estado_cuenta',
            ('sustitucion_proveedor', ('estado_cuenta_id', 'contrato_id')): 'estado_cuenta'}
        fks = _fks()
        for clave, destino in esperadas.items():
            with self.subTest(clave):
                self.assertIn(clave, fks)
                self.assertEqual(fks[clave].referred_table.name, destino)

    def test_sin_cascada_de_borrado_entre_raices(self):
        raices = {'propuesta', 'contrato', 'evento', 'solicitud_cambio', 'solicitud_servicio_adicional', 'sustitucion_proveedor',
                  'estado_cuenta'}
        for (tabla, cols), f in _fks().items():
            if tabla in raices:                                       # una raíz que referencia a otra raíz o a una versión
                with self.subTest((tabla, cols)):
                    self.assertIn(f.ondelete, (None, 'NO ACTION', 'RESTRICT'))

    def test_las_hijas_se_borran_en_cascada_solo_con_su_propio_agregado(self):
        agregado = {'version_propuesta': 'propuesta', 'contrato_anexo': 'contrato', 'contrato_seguimiento_anticipo': 'contrato',
                    'evento_servicio_contratado': 'evento', 'evento_solicitud_cancelacion': 'evento',
                    'evento_operacion_aplicada': 'evento', 'solicitud_cambio_condicion': 'solicitud_cambio',
                    'sustitucion_alternativa': 'sustitucion_proveedor', 'obligacion_pago': 'estado_cuenta',
                    'devolucion': 'estado_cuenta', 'estado_cuenta_seguimiento_cobro': 'estado_cuenta',
                    'estado_cuenta_cierre_sin_realizar': 'estado_cuenta', 'outbox_reaccion': 'outbox_evento', 'pago': 'obligacion_pago',
                    'sesion': 'usuario'}
        for (tabla, cols), f in _fks().items():
            if f.ondelete == 'CASCADE':
                with self.subTest((tabla, cols)):
                    self.assertEqual(agregado[tabla], f.referred_table.name)

    def test_referencias_blandas_documentadas_sin_fk(self):
        blandas = [('contrato_anexo', 'origen_id'), ('obligacion_pago', 'origen_id'), ('devolucion', 'solicitud_id'),
                   ('estado_cuenta_cierre_sin_realizar', 'origen_id'), ('outbox_evento', 'agregado_id'),
                   ('solicitud_cambio', 'anexo_id'), ('solicitud_cambio', 'obligacion_pago_id'),
                   ('sustitucion_proveedor', 'servicio_contratado_id'), ('propuesta', 'cliente_id'), ('evento', 'cliente_id'),
                   ('evento_servicio_contratado', 'proveedor_id'), ('sustitucion_proveedor', 'proveedor_original_id')]
        con_fk = {(t, c) for (t, cols) in _fks() for c in cols}
        for tabla, columna in blandas:
            with self.subTest((tabla, columna)):
                self.assertIn(columna, metadata.tables[tabla].c)
                self.assertNotIn((tabla, columna), con_fk)

    def test_el_grafo_es_creable_y_el_unico_ciclo_usa_alter(self):
        orden = [t.name for t in metadata.sorted_tables]            # falla (con aviso) si hubiera ciclos sin use_alter
        for (tabla, cols), f in _fks().items():
            destino = f.referred_table.name
            if destino != tabla and not f.use_alter:
                self.assertLess(orden.index(destino), orden.index(tabla), (tabla, destino))


class EnterosYLimiteTecnico(unittest.TestCase):
    """Incremento 2.4: solo las dos columnas de invitados son BIGINT por el límite técnico; el resto conserva su tipo."""
    BIGINT = {('evento', 'invitados_aproximados'), ('solicitud_cambio', 'datos_propuestos_invitados'), ('outbox_evento', 'secuencia'),
              *((t, 'version') for t in ('propuesta', 'contrato', 'evento', 'solicitud_cambio', 'solicitud_servicio_adicional',
                                        'sustitucion_proveedor', 'estado_cuenta')),      # versión de agregado (revisión 0004)
              ('intento_acceso', 'fallos')}                                                  # contador de intentos de acceso (revisión 0006)

    def _enteras(self):
        return {(t.name, c.name): c for t in metadata.tables.values() for c in t.columns
                if isinstance(c.type, sa.Integer)}                              # BigInteger hereda de Integer

    def test_tipos_de_los_metadatos(self):
        for (tabla, columna), c in self._enteras().items():
            with self.subTest((tabla, columna)):
                self.assertEqual(isinstance(c.type, sa.BigInteger), (tabla, columna) in self.BIGINT)

    def test_las_columnas_integer_son_las_previstas(self):
        integer = {k for k, c in self._enteras().items() if not isinstance(c.type, sa.BigInteger)}
        self.assertEqual(sorted(k for k in integer if k[1] != 'posicion'),
                         [('outbox_evento', 'intentos'), ('version_propuesta', 'numero')])     # generados por el sistema
        self.assertTrue(all(k[1] == 'posicion' for k in integer if k[1] not in ('intentos', 'numero')))

    def test_la_migracion_declara_los_mismos_tipos(self):
        with open(RUTA_MIGRACION, encoding='utf-8') as f:
            arbol = ast.parse(f.read())
        tipos = {}
        for n in ast.walk(arbol):
            if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'Column' and len(n.args) >= 2:
                if isinstance(n.args[1], ast.Call) and getattr(n.args[1].func, 'attr', '') in ('Integer', 'BigInteger'):
                    tipos.setdefault(n.args[0].value, set()).add(n.args[1].func.attr)
        self.assertEqual(tipos['invitados_aproximados'], {'BigInteger'})
        self.assertEqual(tipos['datos_propuestos_invitados'], {'BigInteger'})
        self.assertEqual(tipos['secuencia'], {'BigInteger'})
        for columna in ('numero', 'intentos', 'posicion'):
            self.assertEqual(tipos[columna], {'Integer'}, columna)

    def test_el_ddl_offline_usa_bigint_en_las_dos_columnas(self):
        from alembic import command
        from alembic.config import Config
        buf = io.StringIO()
        cfg = Config(os.path.join(RAIZ, 'alembic.ini'), output_buffer=buf)
        cfg.set_main_option('script_location', os.path.join(RAIZ, 'migraciones'))
        command.upgrade(cfg, 'head', sql=True)
        sql = buf.getvalue()
        self.assertRegex(sql, r'invitados_aproximados BIGINT NOT NULL')
        self.assertRegex(sql, r'datos_propuestos_invitados BIGINT,')
        self.assertNotRegex(sql, r'invitados\w* INTEGER')

    def test_el_check_de_positividad_se_conserva(self):
        evento = {str(c.name): str(c.sqltext) for c in metadata.tables['evento'].constraints if isinstance(c, sa.CheckConstraint)}
        solicitud = {str(c.name): str(c.sqltext) for c in metadata.tables['solicitud_cambio'].constraints
                     if isinstance(c, sa.CheckConstraint)}
        self.assertEqual(evento['ck_evento_invitados_positivo'], 'invitados_aproximados > 0')
        self.assertEqual(solicitud['ck_solicitud_cambio_datos_propuestos_invitados_positivo'],
                         'datos_propuestos_invitados IS NULL OR datos_propuestos_invitados > 0')

    def test_no_se_introdujo_ningun_maximo_de_negocio_en_los_check(self):
        for tabla in ('evento', 'solicitud_cambio'):
            for c in metadata.tables[tabla].constraints:
                if isinstance(c, sa.CheckConstraint) and 'invitados' in str(c.sqltext):
                    self.assertNotRegex(str(c.sqltext), r'<=?\s*\d')


TABLAS_POSTERIORES_A_0001 = {'proveedor', 'usuario', 'sesion', 'intento_acceso'}   # revisiones 0005 y 0006; su DDL se comprueba en test_la_revision_000*


class Migracion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(RUTA_MIGRACION, encoding='utf-8') as f:
            cls.arbol = ast.parse(f.read())

    def _ops(self, nombre):
        fn = next(n for n in self.arbol.body if isinstance(n, ast.FunctionDef) and n.name == nombre)
        salida = []
        for n in ast.walk(fn):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == 'op' and n.func.attr != 'f'):
                salida.append((n.func.attr, n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else None))
        return salida

    def test_una_sola_revision_inicial_y_una_cadena_lineal(self):
        carpeta = os.path.dirname(RUTA_MIGRACION)
        self.assertEqual(sorted(f for f in os.listdir(carpeta) if f.endswith('.py')),
                         ['0001_esquema_inicial.py', '0002_proveedor_original_opcional.py',
                          '0003_devolucion_anticipo_contratacion_cerrada.py', '0004_version_de_agregado.py',
                          '0005_catalogo_de_proveedores.py', '0006_seguridad_cuentas_y_sesiones.py'])
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        cfg = Config(os.path.join(RAIZ, 'alembic.ini'))
        cfg.set_main_option('script_location', os.path.join(RAIZ, 'migraciones'))
        script = ScriptDirectory.from_config(cfg)
        self.assertEqual(script.get_heads(), ['0006'])                  # una sola cabeza: historia lineal
        self.assertIsNone(script.get_revision('0001').down_revision)    # una única revisión inicial
        self.assertEqual(script.get_revision('0002').down_revision, '0001')
        self.assertEqual(script.get_revision('0003').down_revision, '0002')
        self.assertEqual(script.get_revision('0004').down_revision, '0003')
        self.assertEqual(script.get_revision('0005').down_revision, '0004')
        self.assertEqual(script.get_revision('0006').down_revision, '0005')

    def test_la_revision_0002_solo_relaja_una_columna(self):
        with open(os.path.join(os.path.dirname(RUTA_MIGRACION), '0002_proveedor_original_opcional.py'), encoding='utf-8') as f:
            arbol = ast.parse(f.read())
        for nombre, anulable in (('upgrade', True), ('downgrade', False)):
            fn = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == nombre)
            llamadas = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'alter_column']
            self.assertEqual(len(llamadas), 1, nombre)
            self.assertEqual([a.value for a in llamadas[0].args], ['sustitucion_proveedor', 'proveedor_original_id'])
            self.assertEqual({k.arg: k.value.value for k in llamadas[0].keywords if isinstance(k.value, ast.Constant)}['nullable'], anulable)
        self.assertEqual({o for o, _ in self._ops('upgrade')}, {'create_table', 'create_index', 'create_foreign_key'})   # 0001 no se tocó

    def test_upgrade_solo_crea(self):
        permitidas = {'create_table', 'create_index', 'create_foreign_key'}
        self.assertEqual({o for o, _ in self._ops('upgrade')} - permitidas, set())
        self.assertEqual(len([1 for o, _ in self._ops('upgrade') if o == 'create_table']), len(metadata.tables) - len(TABLAS_POSTERIORES_A_0001))

    def test_downgrade_es_la_inversa_exacta(self):
        up, down = self._ops('upgrade'), self._ops('downgrade')
        self.assertEqual([n for o, n in down if o == 'drop_table'], list(reversed([n for o, n in up if o == 'create_table'])))
        self.assertEqual({n for o, n in down if o == 'drop_index'}, {n for o, n in up if o == 'create_index'})
        self.assertEqual(down[0][0], 'drop_constraint')               # primero se quita la FK diferida
        self.assertEqual(sum(1 for o, _ in down if o == 'drop_constraint'), sum(1 for o, _ in up if o == 'create_foreign_key'))

    def test_el_ddl_offline_de_la_migracion_coincide_con_los_metadatos(self):
        from alembic import command
        from alembic.config import Config
        buf = io.StringIO()
        cfg = Config(os.path.join(RAIZ, 'alembic.ini'), output_buffer=buf)
        cfg.set_main_option('script_location', os.path.join(RAIZ, 'migraciones'))
        cfg.set_main_option('prepend_sys_path', os.path.join(RAIZ, 'src'))
        command.upgrade(cfg, '0001', sql=True)                        # modo offline: la revisión inicial; no se conecta a ninguna base
        sql = buf.getvalue()
        self.assertNotRegex(sql, r'(?im)^\s*(DROP|DELETE|TRUNCATE)\b')
        dialecto = postgresql.dialect()
        norm = lambda s: [re.sub(r'\s+', ' ', l).strip().rstrip(',') for l in s.splitlines() if l.strip() and not l.strip().startswith('--')]
        meta = set()
        for t in (t for t in metadata.sorted_tables if t.name not in TABLAS_POSTERIORES_A_0001):
            meta |= {(t.name, l) for l in norm(str(CreateTable(t).compile(dialect=dialecto)))
                     if not l.startswith('CREATE TABLE') and l != ')'}
            for ix in t.indexes:
                meta.add(('IX', ' '.join(norm(str(CreateIndex(ix).compile(dialect=dialecto))))))
        mig, orden = set(), []
        for bloque in re.split(r';\s*\n', sql):
            b = '\n'.join(norm(bloque))
            m = re.search(r'CREATE TABLE (\w+)', b)
            if m and m.group(1) != 'alembic_version':
                orden.append(m.group(1))
                mig |= {(m.group(1), l.rstrip(',')) for l in b.splitlines() if not l.startswith('CREATE TABLE') and l != ')'}
            elif b.startswith('CREATE') and 'INDEX' in b:
                mig.add(('IX', ' '.join(b.split('\n'))))
        # Cambios posteriores a 0001, ya reflejados en los metadatos: la 0002 (proveedor_original_id admite NULL) y la 0003
        # (decisión A: cierre_contratacion y las columnas, restricciones e índice de la devolución del anticipo).
        mig = {(t, 'proveedor_original_id TEXT') if (t, l) == ('sustitucion_proveedor', 'proveedor_original_id TEXT NOT NULL') else (t, l)
               for t, l in mig}
        mig = {(t, 'solicitud_id TEXT') if (t, l) == ('devolucion', 'solicitud_id TEXT NOT NULL') else (t, l) for t, l in mig}
        de_la_0003 = ('cierre_contratacion', 'tipo ', 'pago_id', 'fecha_referencia', 'tipo_valido', 'origen_segun_tipo', 'uq_devolucion_pago')
        meta = {(t, l) for t, l in meta if not (t in ('estado_cuenta', 'devolucion', 'IX') and any(k in l for k in de_la_0003))}
        # Revisión 0004 (control de concurrencia optimista): la columna version y su CHECK en las siete raíces.
        meta = {(t, l) for t, l in meta if not (l.startswith('version BIGINT') or 'version_no_negativa' in l)}
        self.assertEqual(meta - mig, set())
        self.assertEqual(mig - meta, set())
        self.assertEqual(sorted(orden), sorted(set(metadata.tables) - TABLAS_POSTERIORES_A_0001))
        self.assertIn('ALTER TABLE propuesta ADD CONSTRAINT fk_propuesta_version_vigente FOREIGN KEY(propuesta_id, version_vigente_id)', sql)
        self.assertIn('DEFERRABLE INITIALLY DEFERRED', sql)

    def test_la_revision_0003_es_aditiva_y_su_bajada_es_la_inversa(self):
        with open(os.path.join(os.path.dirname(RUTA_MIGRACION), '0003_devolucion_anticipo_contratacion_cerrada.py'), encoding='utf-8') as f:
            arbol = ast.parse(f.read())
        ops = lambda nombre: [n.func.attr for n in ast.walk(next(x for x in arbol.body if isinstance(x, ast.FunctionDef) and x.name == nombre))
                              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr not in ('f', 'Column', 'text')
                              and isinstance(n.func.value, ast.Name) and n.func.value.id == 'op']
        subida, bajada = ops('upgrade'), ops('downgrade')
        self.assertEqual(set(subida) - {'add_column', 'alter_column', 'create_check_constraint', 'create_index'}, set())
        self.assertEqual(subida.count('add_column'), 4)
        self.assertEqual(bajada.count('drop_column'), 4)
        self.assertEqual(bajada.count('drop_constraint'), 2)

    def test_la_revision_0004_solo_agrega_la_columna_version_a_las_siete_raices(self):
        with open(os.path.join(os.path.dirname(RUTA_MIGRACION), '0004_version_de_agregado.py'), encoding='utf-8') as f:
            texto = f.read()
        arbol = ast.parse(texto)
        raices = next(n.value for n in arbol.body if isinstance(n, ast.Assign) and n.targets[0].id == 'RAICES')
        self.assertEqual(sorted(e.value for e in raices.elts), sorted(['propuesta', 'contrato', 'evento', 'solicitud_cambio',
                                                                        'solicitud_servicio_adicional', 'sustitucion_proveedor',
                                                                        'estado_cuenta']))
        self.assertEqual(sorted(metadata.tables[t].c.version.name for t in (e.value for e in raices.elts)), ['version'] * 7)
        self.assertIn("server_default='0'", texto)                       # las filas existentes quedan en la versión 0
        self.assertNotRegex(texto, r'(?i)(delete|truncate|drop_table)')

    def test_la_revision_0005_solo_crea_la_tabla_proveedor(self):
        with open(os.path.join(os.path.dirname(RUTA_MIGRACION), '0005_catalogo_de_proveedores.py'), encoding='utf-8') as f:
            texto = f.read()
        arbol = ast.parse(texto)
        def ops(nombre):
            fn = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == nombre)
            return [(n.func.attr, n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else None) for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == 'op' and n.func.attr != 'f']
        self.assertEqual(ops('upgrade'), [('create_table', 'proveedor')])        # aditiva: ninguna tabla existente se toca
        self.assertEqual(ops('downgrade'), [('drop_table', 'proveedor')])
        self.assertIn('proveedor', metadata.tables)
        self.assertNotRegex(texto, r'(?i)(delete\s+from|truncate|alter_column|drop_column)')

    def test_la_revision_0006_solo_crea_las_tablas_de_seguridad_sin_cuentas_predeterminadas(self):
        with open(os.path.join(os.path.dirname(RUTA_MIGRACION), '0006_seguridad_cuentas_y_sesiones.py'), encoding='utf-8') as f:
            texto = f.read()
        arbol = ast.parse(texto)
        def ops(nombre):
            fn = next(n for n in arbol.body if isinstance(n, ast.FunctionDef) and n.name == nombre)
            return [(n.func.attr, n.args[0].value if n.args and isinstance(n.args[0], ast.Constant) else None) for n in ast.walk(fn)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == 'op' and n.func.attr != 'f']
        self.assertEqual(sorted(ops('upgrade')), sorted([('create_table', 'usuario'), ('create_table', 'sesion'), ('create_table', 'intento_acceso'),
                                                         ('create_index', None)]))      # el nombre del índice va en op.f(...)                  # aditiva: ninguna tabla existente se toca
        self.assertEqual(sorted(n for o, n in ops('downgrade') if o == 'drop_table'), ['intento_acceso', 'sesion', 'usuario'])
        self.assertNotRegex(texto, r'(?i)(insert\s+into|op\.execute|bulk_insert|alter_column|drop_column)')       # no inserta ninguna cuenta
        for tabla in ('usuario', 'sesion', 'intento_acceso'):
            self.assertIn(tabla, metadata.tables)

    def test_la_cadena_completa_agrega_solo_el_alter_de_0002(self):
        from alembic import command
        from alembic.config import Config
        buf = io.StringIO()
        cfg = Config(os.path.join(RAIZ, 'alembic.ini'), output_buffer=buf)
        cfg.set_main_option('script_location', os.path.join(RAIZ, 'migraciones'))
        command.upgrade(cfg, 'head', sql=True)
        sql = buf.getvalue()
        self.assertIn('ALTER TABLE sustitucion_proveedor ALTER COLUMN proveedor_original_id DROP NOT NULL', sql)
        self.assertIn('ALTER TABLE devolucion ALTER COLUMN solicitud_id DROP NOT NULL', sql)
        self.assertIn('ALTER TABLE estado_cuenta ADD COLUMN cierre_contratacion', sql)
        self.assertIn("ALTER TABLE estado_cuenta ADD COLUMN version BIGINT DEFAULT '0' NOT NULL", sql)
        self.assertIn('CREATE TABLE proveedor', sql)
        self.assertIn('CREATE TABLE usuario', sql)
        self.assertNotRegex(sql, r'(?im)^\s*(DROP|DELETE|TRUNCATE)\b')


if __name__ == '__main__':
    unittest.main()
