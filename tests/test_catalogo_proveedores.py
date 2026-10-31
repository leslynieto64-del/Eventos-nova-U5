"""Catálogo de proveedores: registro, consulta y búsqueda, y su uso en la asignación de un proveedor a un servicio contratado.

Cubre el dominio (normalización y validación), la API en memoria y la API sobre PostgreSQL (base de PRUEBAS): alta, duplicados,
búsqueda, 404, asignación de extremo a extremo (disponibilidad → asignación → respuesta del proveedor), nombres legibles en la
información del evento y en los servicios pendientes, y persistencia tras reconstruir el contenedor.
Ejecutar desde la raíz:  python -m unittest tests.test_catalogo_proveedores -v"""
import os, sys, unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from apoyo_bd import BaseConBD                                                               # noqa: E402
from test_api_operaciones import ApiHttp                                                     # noqa: E402
from domain.proveedor import Proveedor, normalizar_texto                                     # noqa: E402
from domain.valores import ErrorDominio                                                      # noqa: E402
from infrastructure.composicion import construir                                              # noqa: E402
from infrastructure.persistencia.composicion_persistente import construir_persistente          # noqa: E402

AHORA = datetime(2026, 10, 1, 10, 0)


class DominioDelProveedor(unittest.TestCase):
    def test_normaliza_nombre_y_servicios_sin_duplicados(self):
        p = Proveedor.registrar('PV-1', '  Banquetes   del Valle ', ['Música', ' musica ', 'Banquete', ''], '  55 1234  ', AHORA)
        self.assertEqual(p.nombre, 'Banquetes del Valle')
        self.assertEqual(p.servicios, ('Música', 'Banquete'))
        self.assertEqual(p.contacto, '55 1234')

    def test_el_nombre_es_obligatorio(self):
        for vacio in ('', '   ', None):
            with self.assertRaises(ErrorDominio):
                Proveedor.registrar('PV-1', vacio, [], '', AHORA)

    def test_ofrece_y_busca_sin_distinguir_mayusculas_ni_acentos(self):
        p = Proveedor.registrar('PV-1', 'Sonido Ñandú', ['Música'], 'sonido@ejemplo.mx', AHORA)
        self.assertTrue(p.ofrece('MUSICA'))
        self.assertFalse(p.ofrece('Banquete'))
        for q in ('nandu', 'MÚSICA', 'ejemplo', 'pv-1', ''):
            self.assertTrue(p.coincide_con(q), q)
        self.assertFalse(p.coincide_con('fotografia'))
        self.assertEqual(normalizar_texto('  ÁÉÍ  ñ '), 'aei n')


class _FlujoDeProveedores:
    """Pruebas HTTP comunes a memoria y PostgreSQL (la subclase decide el contenedor)."""

    def alta(self, nombre='Banquetes del Valle', servicios=('Banquete',), contacto='55 1234', esperado=201):
        return self.post('/proveedores', {'nombre': nombre, 'servicios': list(servicios), 'contacto': contacto}, esperado=esperado)

    def servicio_de(self, evento):
        return self.get(f'/eventos/{evento}/administracion')['proveedores'][0]

    def test_alta_consulta_y_busqueda(self):
        r = self.alta()
        datos = r['datos']
        self.assertTrue(datos['proveedorId'].startswith('PV-'))
        self.assertEqual((datos['nombre'], datos['servicios'], datos['contacto']), ('Banquetes del Valle', ['Banquete'], '55 1234'))
        self.alta('Sonido Nova', ['Música'], '')
        ficha = self.get(f"/proveedores/{datos['proveedorId']}")['datos']
        self.assertEqual(ficha['nombre'], 'Banquetes del Valle')
        todos = self.get('/proveedores')['datos']['proveedores']
        self.assertEqual([p['nombre'] for p in todos], ['Banquetes del Valle', 'Sonido Nova'])
        self.assertEqual([p['nombre'] for p in self.get('/proveedores', q='SONIDO')['datos']['proveedores']], ['Sonido Nova'])
        self.assertEqual([p['nombre'] for p in self.get('/proveedores', servicio='musica')['datos']['proveedores']], ['Sonido Nova'])
        self.assertEqual(self.get('/proveedores', q='no existe')['datos']['proveedores'], [])

    def test_rechazos_de_negocio_y_404(self):
        self.alta()
        duplicado = self.alta('  BANQUETES del valle ', esperado=422)
        self.assertEqual(duplicado['tipo'], 'rechazo_de_negocio')
        self.assertIn('Ya existe', duplicado['detalle'])
        self.assertEqual(self.alta('   ', esperado=422)['tipo'], 'rechazo_de_negocio')
        self.post('/proveedores', {'servicios': []}, esperado=422)                                     # falta el nombre: validación de forma
        self.post('/proveedores', {'nombre': 'X', 'campo_inventado': 1}, esperado=422)               # sin campos desconocidos
        self.assertEqual(self.get('/proveedores/PV-NO-EXISTE', esperado=404)['tipo'], 'no_encontrado')
        self.assertEqual(len(self.get('/proveedores')['datos']['proveedores']), 1)                   # los rechazos no dejaron nada

    def test_asignacion_de_extremo_a_extremo(self):
        ids = self.contratar()
        evento = ids['evento']
        servicio = self.servicio_de(evento)
        self.assertEqual((servicio['estado'], servicio['proveedorId']), ('Sin proveedor asignado', None))
        self.assertNotIn('proveedorNombre', servicio)
        ruta = f"/eventos/{evento}/servicios/{servicio['servicioContratadoId']}"

        # Sin catálogo no hay candidatos: el rechazo explica por qué.
        self.assertEqual(self.get(f'{ruta}/disponibilidad')['datos']['disponibles'], [])
        sin = self.post(f'{ruta}/proveedor', {'proveedor_id': 'PV-X'}, esperado=422)
        self.assertIn('no está registrado en el catálogo', sin['detalle'])                    # proveedor inexistente

        # Un proveedor que ofrece OTRO servicio no es candidato.
        otro = self.alta('Sonido Nova', ['Música'])['datos']['proveedorId']
        self.assertEqual(self.get(f'{ruta}/disponibilidad')['datos']['disponibles'], [])
        rechazo = self.post(f'{ruta}/proveedor', {'proveedor_id': otro}, esperado=422)
        self.assertIn('«Sonido Nova» no ofrece el servicio «Banquete»', rechazo['detalle'])    # existe pero no ofrece este servicio
        self.assertEqual(self.servicio_de(evento)['estado'], 'Sin proveedor asignado')          # el rechazo no cambió nada

        # Con el proveedor correcto: candidato → asignación → pendiente de confirmación.
        pv = self.alta('Banquetes del Valle', ['Banquete'])['datos']['proveedorId']
        self.assertEqual(self.get(f'{ruta}/disponibilidad')['datos']['disponibles'], [pv])
        r = self.post(f'{ruta}/proveedor', {'proveedor_id': pv})
        self.assertEqual(r['datos']['estado'], 'Pendiente de confirmación del proveedor')
        servicio = self.servicio_de(evento)
        self.assertEqual((servicio['proveedorId'], servicio['proveedorNombre'], servicio['estado']),
                         (pv, 'Banquetes del Valle', 'Pendiente de confirmación del proveedor'))

        # Los servicios pendientes distinguen «asignado, sin confirmar» y traen el nombre legible.
        pend = [s for s in self.get('/servicios-pendientes-confirmacion', evento_id=evento)['servicios']]
        self.assertEqual([(s['proveedorId'], s['proveedorNombre'], s['estado']) for s in pend],
                         [(pv, 'Banquetes del Valle', 'Pendiente de confirmación del proveedor')])

        # No se asigna dos veces; otro proveedor no puede responder por este servicio.
        self.post(f'{ruta}/proveedor', {'proveedor_id': pv}, esperado=422)
        self.post(f'{ruta}/respuesta-proveedor', {'proveedor_id': otro, 'disponible': True}, esperado=422)

        # El proveedor asignado confirma: el servicio queda confirmado y deja de estar pendiente.
        c = self.post(f'{ruta}/respuesta-proveedor', {'proveedor_id': pv, 'disponible': True})
        self.assertEqual(c['datos']['estado'], 'Confirmado por el proveedor')
        self.assertEqual(self.servicio_de(evento)['estado'], 'Confirmado por el proveedor')
        self.assertEqual(self.get('/servicios-pendientes-confirmacion', evento_id=evento)['servicios'], [])
        self.post(f'{ruta}/respuesta-proveedor', {'proveedor_id': pv, 'disponible': True}, esperado=422)   # ya no espera respuesta

    def test_proveedor_asignado_que_no_esta_en_el_catalogo_conserva_su_identificador(self):
        """Identificadores históricos (p. ej. de la fuente de disponibilidad): se muestran tal cual, sin nombre inventado."""
        from application.servicios import transaccion
        ids = self.contratar()
        servicio = self.servicio_de(ids['evento'])
        ev = self.contenedor.repos.eventos.obtener_por_id(ids['evento'])
        ev.asignar_proveedor(servicio['servicioContratadoId'], 'PV-HISTORICO')
        with transaccion(self.contenedor.uow, ev):
            self.contenedor.repos.eventos.guardar(ev)
        actual = self.servicio_de(ids['evento'])
        self.assertEqual((actual['proveedorId'], actual.get('proveedorNombre')), ('PV-HISTORICO', None))
        pend = self.get('/servicios-pendientes-confirmacion', evento_id=ids['evento'])['servicios'][0]
        self.assertEqual((pend['proveedorId'], pend['proveedorNombre']), ('PV-HISTORICO', None))

    def test_un_evento_cancelado_rechaza_la_asignacion_con_su_propio_motivo_y_no_cambia_nada(self):
        ids = self.contratar()
        servicio = self.servicio_de(ids['evento'])
        pv = self.alta()['datos']['proveedorId']
        self.post(f"/eventos/{ids['evento']}/cancelacion", {'motivo': 'Cancelación de prueba'})
        r = self.post(f"/eventos/{ids['evento']}/servicios/{servicio['servicioContratadoId']}/proveedor", {'proveedor_id': pv}, esperado=422)
        self.assertIn('Los proveedores solo se gestionan con el Evento En organización', r['detalle'])
        actual = self.servicio_de(ids['evento'])
        self.assertEqual((actual['estado'], actual['proveedorId']), ('Sin proveedor asignado', None))

    def test_la_asignacion_exige_el_evento_en_organizacion(self):
        ids = self.contratar(confirmar=False)               # contrato firmado, anticipo sin pagar: sin servicios contratados todavía
        self.assertEqual(self.get(f"/eventos/{ids['evento']}/administracion")['proveedores'], [])
        pv = self.alta()['datos']['proveedorId']
        r = self.post(f"/eventos/{ids['evento']}/servicios/SC-NO-EXISTE/proveedor", {'proveedor_id': pv}, esperado=422)
        self.assertEqual(r['tipo'], 'rechazo_de_negocio')


class FuenteDeDemostracionFueraDeLaOperacion(unittest.TestCase):
    """Los PV-DEMO-* del archivo de demostración no son candidatos de la asignación operativa; solo el catálogo registrado lo es."""
    DEMO = os.path.join(os.path.dirname(__file__), '..', 'src', 'infrastructure', 'datos_demo', 'disponibilidad_demo.json')

    def test_la_fuente_del_entorno_no_ofrece_candidatos_de_demostracion_pero_sigue_disponible_para_otros_flujos(self):
        from unittest import mock
        import infrastructure.adaptadores as AD
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO': self.DEMO}):
            fuente = AD.disponibilidad_desde_entorno()
        self.assertTrue(fuente.solo_demostracion)
        contenedor = construir(fuente)
        asignacion = contenedor.servicios.proveedores.disponibilidad
        self.assertEqual(asignacion.consultar('Banquete', AHORA, []), [])                         # catálogo vacío: ningún candidato
        self.assertTrue(contenedor.servicios.cambios.disponibilidad is fuente)                    # otros flujos conservan su fuente
        self.assertEqual([d.proveedor_id for d in fuente.consultar('Banquete', AHORA, [])], ['PV-DEMO-BANQUETE-1', 'PV-DEMO-BANQUETE-2'])

    def test_con_la_fuente_del_entorno_activa_solo_el_catalogo_aparece_como_candidato(self):
        from unittest import mock
        import infrastructure.adaptadores as AD
        from domain.proveedor import Proveedor
        with mock.patch.dict(os.environ, {'EVENTOSNOVA_DISPONIBILIDAD_ARCHIVO': self.DEMO}):
            contenedor = construir(AD.disponibilidad_desde_entorno())
        contenedor.repos.proveedores.guardar(Proveedor.registrar('PV-REAL', 'Proveedor Real', ['Banquete'], '', AHORA))
        ids = [d.proveedor_id for d in contenedor.servicios.proveedores.disponibilidad.consultar('Banquete', AHORA, [])]
        self.assertEqual(ids, ['PV-REAL'])
        self.assertFalse(any(i.startswith('PV-DEMO') for i in ids))

    def test_una_fuente_inyectada_explicitamente_sigue_funcionando_como_fixture(self):
        import infrastructure.adaptadores as AD
        contenedor = construir(AD.ConsultaDisponibilidadDesdeArchivo(self.DEMO))                  # inyección explícita (pruebas aisladas)
        ids = [d.proveedor_id for d in contenedor.servicios.proveedores.disponibilidad.consultar('Banquete', AHORA, []) if d.disponible]
        self.assertEqual(ids, ['PV-DEMO-BANQUETE-1'])


class CatalogoEnMemoria(_FlujoDeProveedores, ApiHttp, unittest.TestCase):
    def crear_contenedor(self, disponibilidad=None):
        return construir(disponibilidad)


class CatalogoEnPostgreSQL(_FlujoDeProveedores, ApiHttp, BaseConBD):
    def setUp(self):
        BaseConBD.setUp(self)
        self.arrancar()

    def crear_contenedor(self, disponibilidad=None):
        return construir_persistente(motor=self.motor, disponibilidad=disponibilidad)

    def test_persiste_tras_reconstruir_el_contenedor(self):
        ids = self.contratar()
        servicio = self.servicio_de(ids['evento'])
        pv = self.alta('Banquetes del Valle', ['Banquete', 'Música'], 'contacto@ejemplo.mx')['datos']['proveedorId']
        self.post(f"/eventos/{ids['evento']}/servicios/{servicio['servicioContratadoId']}/proveedor", {'proveedor_id': pv})
        self.arrancar()                                                                           # contenedor y aplicación nuevos, misma base
        ficha = self.get(f'/proveedores/{pv}')['datos']
        self.assertEqual((ficha['nombre'], ficha['servicios'], ficha['contacto']), ('Banquetes del Valle', ['Banquete', 'Música'], 'contacto@ejemplo.mx'))
        actual = self.servicio_de(ids['evento'])
        self.assertEqual((actual['proveedorId'], actual['proveedorNombre'], actual['estado']), (pv, 'Banquetes del Valle', 'Pendiente de confirmación del proveedor'))

    def test_la_base_impide_nombres_duplicados_aunque_se_salte_la_aplicacion(self):
        from infrastructure.persistencia.repositorios_sql import ProveedorRepositorySQL
        repo = ProveedorRepositorySQL(self.contenedor.almacen)
        self.assertTrue(repo.guardar(Proveedor.registrar('PV-A', 'Nombre Único', [], '', AHORA)))
        self.assertFalse(repo.guardar(Proveedor.registrar('PV-B', 'nombre unico', [], '', AHORA)))     # mismo nombre normalizado
        self.assertFalse(repo.guardar(Proveedor.registrar('PV-A', 'Otro Nombre', [], '', AHORA)))      # mismo identificador
        self.assertEqual([p.proveedor_id for p in repo.listar_todos()], ['PV-A'])
        self.assertEqual(repo.obtener_por_id('PV-A').nombre, 'Nombre Único')
        self.assertIsNone(repo.obtener_por_id('PV-B'))


if __name__ == '__main__':
    unittest.main()
