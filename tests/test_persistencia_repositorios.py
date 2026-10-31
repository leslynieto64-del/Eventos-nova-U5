"""Etapa 4 de la persistencia — pruebas de CONTRATO de los repositorios.

Las mismas pruebas se ejecutan sobre el adaptador en memoria y sobre el adaptador SQL (PostgreSQL de pruebas): ambos deben cumplir
el contrato de `application.puertos`. Después, pruebas propias del adaptador SQL: restricciones, atomicidad y traducción de errores.
Los escenarios (`apoyo_persistencia`) se construyen con métodos reales del dominio y respetan las claves foráneas del esquema."""
import os, sys, unittest
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
import apoyo_persistencia as A                                                            # noqa: E402
from apoyo_persistencia import estado_de, T0, FECHA_EVENTO                                # noqa: E402
from apoyo_bd import BaseConBD                                                            # noqa: E402
from infrastructure import repositorios_memoria as M                                      # noqa: E402
from infrastructure.unidad_trabajo import UnitOfWorkMemoria                               # noqa: E402
from infrastructure.persistencia import repositorios_sql as S                             # noqa: E402
from infrastructure.persistencia.errores import ErrorDeDatos, ViolacionDeRestriccion       # noqa: E402
from domain.valores import (DatosEvento, EstadoEvento, EstadoSolicitudCambio, Importe, ConceptoPago, PlazoPago)   # noqa: E402
from domain.estado_cuenta import ObligacionPago                                           # noqa: E402

ORDEN_DE_GUARDADO = ('eventos', 'propuestas', 'contratos', 'estados_cuenta', 'cambios', 'adicionales', 'sustituciones')
REPOS = (('propuestas', 'Propuesta'), ('contratos', 'Contrato'), ('eventos', 'Evento'), ('estados_cuenta', 'EstadoCuenta'),
         ('cambios', 'SolicitudCambio'), ('adicionales', 'SolicitudServicioAdicional'), ('sustituciones', 'SustitucionProveedor'))


class FabricaMemoria:
    def __init__(self):
        uow = UnitOfWorkMemoria()
        self.uow = uow
        self.repos = SimpleNamespace(
            propuestas=M.PropuestaRepositoryMemoria(uow), contratos=M.ContratoRepositoryMemoria(uow),
            eventos=M.EventoRepositoryMemoria(uow), cambios=M.SolicitudCambioRepositoryMemoria(uow),
            adicionales=M.SolicitudServicioAdicionalRepositoryMemoria(uow),
            sustituciones=M.SustitucionProveedorRepositoryMemoria(uow), estados_cuenta=M.EstadoCuentaRepositoryMemoria(uow))

    def guardar(self, repo, ag):
        self.uow.iniciar(); self.uow.registrar(ag); repo.guardar(ag); self.uow.confirmar()


class FabricaSQL:
    def __init__(self, almacen):
        self.repos = SimpleNamespace(
            propuestas=S.PropuestaRepositorySQL(almacen), contratos=S.ContratoRepositorySQL(almacen),
            eventos=S.EventoRepositorySQL(almacen), cambios=S.SolicitudCambioRepositorySQL(almacen),
            adicionales=S.SolicitudServicioAdicionalRepositorySQL(almacen),
            sustituciones=S.SustitucionProveedorRepositorySQL(almacen), estados_cuenta=S.EstadoCuentaRepositorySQL(almacen))

    def guardar(self, repo, ag):
        repo.guardar(ag)                                   # escritura aislada: su propia transacción


def _por_id(lista):
    return sorted(lista, key=lambda a: a.id)


class ContratoDeRepositorio:
    """Mixin con las pruebas de contrato. Requiere `self.f` (una fábrica con `.repos` y `.guardar`)."""
    def sembrar(self):
        """Guarda todos los escenarios en orden de dependencia. Devuelve {nombre_de_repo: [originales]}."""
        escenarios = A.todos()
        por_repo = {'propuestas': escenarios['Propuesta'], 'contratos': escenarios['Contrato'], 'eventos': escenarios['Evento'],
                    'estados_cuenta': escenarios['EstadoCuenta'], 'cambios': escenarios['SolicitudCambio'],
                    'adicionales': escenarios['SolicitudServicioAdicional'], 'sustituciones': escenarios['SustitucionProveedor']}
        for nombre in ORDEN_DE_GUARDADO:
            for ag in por_repo[nombre]:
                self.f.guardar(getattr(self.f.repos, nombre), ag)
        return por_repo

    def test_un_identificador_inexistente_devuelve_none(self):
        for nombre, _ in REPOS:
            with self.subTest(nombre):
                self.assertIsNone(getattr(self.f.repos, nombre).obtener_por_id('NO-EXISTE'))

    def test_los_siete_agregados_se_guardan_y_se_recuperan_completos(self):
        por_repo = self.sembrar()
        for nombre, _ in REPOS:
            repo = getattr(self.f.repos, nombre)
            for original in por_repo[nombre]:
                with self.subTest(f'{nombre} {original.id}'):
                    recuperado = repo.obtener_por_id(original.id)
                    self.assertIsNotNone(recuperado)
                    self.assertIs(type(recuperado), type(original))
                    self.assertEqual(estado_de(recuperado), estado_de(original))
                    self.assertEqual(recuperado._eventos, [])               # nunca vienen eventos del almacén

    def test_guardar_dos_veces_es_idempotente_y_no_duplica_filas_hijas(self):
        por_repo = self.sembrar()
        for nombre, _ in REPOS:
            repo = getattr(self.f.repos, nombre)
            for original in por_repo[nombre]:
                self.f.guardar(repo, original)                              # segundo guardado idéntico
                with self.subTest(f'{nombre} {original.id}'):
                    self.assertEqual(estado_de(repo.obtener_por_id(original.id)), estado_de(original))

    def test_actualizar_refleja_los_cambios_sin_duplicar(self):
        self.sembrar()
        e = self.f.repos.eventos.obtener_por_id('EV-2')                     # En gestión
        self.assertEqual(e.estado, EstadoEvento.EN_GESTION)
        from domain.evento import ServicioContratado
        from domain.valores import CondicionesServicio
        e.confirmar_contratacion([ServicioContratado('CT-2-S1', 'Música', None, CondicionesServicio('x'))])
        self.f.guardar(self.f.repos.eventos, e)
        e2 = self.f.repos.eventos.obtener_por_id('EV-2')
        self.assertEqual(e2.estado, EstadoEvento.EN_ORGANIZACION)
        self.assertEqual(list(e2.servicios), ['CT-2-S1'])
        ec = self.f.repos.estados_cuenta.obtener_por_id('EC-2')
        n_pagos, n_obl = len(ec.pagos), len(ec.obligaciones)
        ec.registrar_y_verificar_pago('PG-NUEVO', 'OB-9', ec.obligaciones['OB-9'].importe, T0, 'C-9', True)   # el anticipo es el 30 %
        self.f.guardar(self.f.repos.estados_cuenta, ec)
        self.f.guardar(self.f.repos.estados_cuenta, ec)                     # repetir no crea otro pago
        ec2 = self.f.repos.estados_cuenta.obtener_por_id('EC-2')
        self.assertEqual((len(ec2.pagos), len(ec2.obligaciones)), (n_pagos + 1, n_obl))
        self.assertEqual(ec2.obligaciones['OB-9'].estado.name, 'LIQUIDADA')

    def test_el_agregado_recuperado_es_una_copia_independiente(self):
        self.sembrar()
        a = self.f.repos.eventos.obtener_por_id('EV-1')
        a.datos = DatosEvento('Cambiado sin guardar', FECHA_EVENTO, 'X', 1)
        a.servicios.clear()
        b = self.f.repos.eventos.obtener_por_id('EV-1')
        self.assertEqual(b.datos.tipo, 'Boda 2')
        self.assertEqual(len(b.servicios), 3)

    def test_guardar_no_consume_los_eventos_pendientes_del_agregado(self):
        s = A.solicitudes_cambio()[4]
        self.sembrar_previos_de(s)
        antes = list(s._eventos)
        self.assertTrue(antes)
        self.f.repos.cambios.guardar(s)             # el repositorio no extrae eventos; de eso se encarga la unidad de trabajo
        self.assertEqual(s._eventos, antes)

    def sembrar_previos_de(self, _):
        e = A.eventos()[0]; self.f.guardar(self.f.repos.eventos, e)
        c = A.contratos()[0]; p = A.propuestas()[0]
        self.f.guardar(self.f.repos.propuestas, p); self.f.guardar(self.f.repos.contratos, c)
        self.f.guardar(self.f.repos.estados_cuenta, A.estados_cuenta()[0])

    def test_listados_por_evento_y_totales(self):
        por_repo = self.sembrar()
        r = self.f.repos
        self.assertEqual([x.id for x in _por_id(r.propuestas.listar_por_evento_id('EV-1'))], ['PR-1'])
        self.assertEqual([x.id for x in _por_id(r.contratos.listar_por_evento_id('EV-2'))], ['CT-2'])
        self.assertEqual(r.propuestas.listar_por_evento_id('EV-X'), [])
        self.assertEqual(sorted(x.id for x in r.eventos.listar_todos()), sorted(x.id for x in por_repo['eventos']))
        self.assertEqual([x.id for x in _por_id(r.estados_cuenta.listar_por_evento_id('EV-1'))], ['EC-1'])
        self.assertEqual(sorted(x.id for x in r.estados_cuenta.listar_todos()), ['EC-1', 'EC-2', 'EC-3'])
        for nombre in ('cambios', 'adicionales', 'sustituciones'):
            repo = getattr(r, nombre)
            self.assertEqual(sorted(x.id for x in repo.listar_todas()), sorted(x.id for x in por_repo[nombre]), nombre)
            self.assertEqual(sorted(x.id for x in repo.listar_por_evento_id('EV-1')), sorted(x.id for x in por_repo[nombre]))
            self.assertEqual(repo.listar_por_evento_id('EV-9'), [])

    def test_pendientes_son_las_solicitudes_que_no_estan_en_un_estado_final(self):
        por_repo = self.sembrar()
        for nombre in ('cambios', 'adicionales', 'sustituciones'):
            repo = getattr(self.f.repos, nombre)
            esperado = sorted(x.id for x in por_repo[nombre] if x.pendiente and x.evento_id == 'EV-1')
            with self.subTest(nombre):
                self.assertEqual(sorted(x.id for x in repo.listar_pendientes_por_evento_id('EV-1')), esperado)
                self.assertEqual(repo.listar_pendientes_por_evento_id('EV-9'), [])
        self.assertTrue(any(not x.pendiente for x in por_repo['cambios']))         # el escenario incluye finales y pendientes
        self.assertTrue(any(x.pendiente for x in por_repo['cambios']))

    def test_estado_cuenta_se_obtiene_por_contrato(self):
        self.sembrar()
        ec = self.f.repos.estados_cuenta.obtener_por_contrato_id('CT-1')
        self.assertEqual(ec.id, 'EC-1')
        self.assertIsNone(self.f.repos.estados_cuenta.obtener_por_contrato_id('CT-NO'))

    def test_el_estado_privado_sobrevive_al_guardado_y_a_la_lectura(self):
        self.sembrar()
        ec = self.f.repos.estados_cuenta.obtener_por_id('EC-1')
        self.assertEqual(ec._ventana_resuelta, 'OB-5')
        self.assertIn('SC-1', ec._cierres_sin_realizar)
        ev = self.f.repos.eventos.obtener_por_id('EV-1')
        self.assertEqual(ev._operaciones_aplicadas, {'SC-1', 'SA-1', 'SP-1'})
        sol = self.f.repos.cambios.obtener_por_id('SC-2')
        self.assertEqual(sol._estado_antes_de_detener, EstadoSolicitudCambio.REGISTRADA)

    def test_la_precision_decimal_se_conserva(self):
        self.sembrar()
        ec = self.f.repos.estados_cuenta.obtener_por_id('EC-1')
        self.assertEqual({k: str(o.importe.cantidad) for k, o in ec.obligaciones.items()},
                         {'OB-1': '3000.00', 'OB-2': '7000.00', 'OB-3': '150.25', 'OB-3B': '99.9', 'OB-4': '100.00', 'OB-5': '200.00'})
        p = self.f.repos.propuestas.obtener_por_id('PR-1')
        self.assertEqual([str(v.contenido.costo_total.cantidad) for v in p.versiones], ['12345.60', '15000'])

    def test_el_maximo_tecnico_de_invitados_se_conserva(self):
        self.sembrar()
        self.assertEqual(self.f.repos.eventos.obtener_por_id('EV-2').datos.invitados_aproximados, 9223372036854775807)


class RepositoriosEnMemoria(ContratoDeRepositorio, unittest.TestCase):
    def setUp(self):
        self.f = FabricaMemoria()


class RepositoriosSQL(ContratoDeRepositorio, BaseConBD):
    def setUp(self):
        super().setUp()
        self.f = FabricaSQL(self.almacen)

    # ---- propias del adaptador SQL
    def test_los_listados_estan_ordenados_por_identificador(self):
        self.sembrar()
        ids = [x.id for x in self.f.repos.eventos.listar_todos()]
        self.assertEqual(ids, sorted(ids))

    def test_clave_foranea_hacia_una_raiz_inexistente(self):
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            self.f.guardar(self.f.repos.propuestas, A.propuestas()[0])       # el Evento EV-1 no existe todavía
        self.assertEqual(ctx.exception.restriccion, 'fk_propuesta_evento_id_evento')
        self.assertEqual(self.contar('propuesta'), 0)                        # nada quedó a medias
        self.assertEqual(self.contar('version_propuesta'), 0)

    def test_un_contrato_exige_una_version_de_su_propia_propuesta(self):
        self.f.guardar(self.f.repos.eventos, A.eventos()[0])
        self.f.guardar(self.f.repos.eventos, A.eventos()[1])
        p1, p2 = A.propuestas()[0], A.propuestas()[1]
        self.f.guardar(self.f.repos.propuestas, p1); self.f.guardar(self.f.repos.propuestas, p2)
        c = A.contratos()[0]
        c.version_aceptada_id = 'PR-2-v1'                                    # versión de OTRA propuesta (PR-2), no de PR-1
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            self.f.guardar(self.f.repos.contratos, c)
        self.assertEqual(ctx.exception.restriccion, 'fk_contrato_version_aceptada')

    def test_la_version_vigente_debe_pertenecer_a_la_propuesta(self):
        self.f.guardar(self.f.repos.eventos, A.eventos()[0])
        self.f.guardar(self.f.repos.eventos, A.eventos()[1])
        self.f.guardar(self.f.repos.propuestas, A.propuestas()[1])           # PR-2 con PR-2-v1
        p = A.propuestas()[0]
        p.version_vigente_id = 'PR-2-v1'                                     # vigente de otra propuesta
        with self.assertRaises(ViolacionDeRestriccion) as ctx:               # la FK es diferida: falla al confirmar
            self.f.guardar(self.f.repos.propuestas, p)
        self.assertEqual(ctx.exception.restriccion, 'fk_propuesta_version_vigente')
        self.assertEqual(self.contar('propuesta'), 1)                        # solo PR-2; PR-1 se revirtió completa

    def test_un_estado_de_cuenta_por_contrato(self):
        self.sembrar()
        from domain.estado_cuenta import EstadoCuenta
        otro = EstadoCuenta('EC-OTRO', 'CT-1', 'EV-1')                       # mismo contrato que EC-1
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            self.f.guardar(self.f.repos.estados_cuenta, otro)
        self.assertIn('uq_estado_cuenta_contrato_id', ctx.exception.restriccion)

    def test_un_estado_de_cuenta_debe_coincidir_con_el_evento_de_su_contrato(self):
        self.sembrar()
        from domain.estado_cuenta import EstadoCuenta
        from domain.contrato import Contrato
        from domain.valores import CondicionesContractuales, PoliticaNoReembolso
        nuevo = Contrato('CT-9', 'EV-1', 'PR-1', 'PR-1-v1', CondicionesContractuales(('a',), Importe(D('1')), 'c'), PoliticaNoReembolso(True))
        self.f.guardar(self.f.repos.contratos, nuevo)                              # contrato del evento EV-1, sin estado de cuenta
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            self.f.guardar(self.f.repos.estados_cuenta, EstadoCuenta('EC-9', 'CT-9', 'EV-3'))   # evento distinto al del contrato
        self.assertEqual(ctx.exception.restriccion, 'fk_estado_cuenta_contrato')
        self.f.guardar(self.f.repos.estados_cuenta, EstadoCuenta('EC-9', 'CT-9', 'EV-1'))       # el coherente sí se guarda

    def test_una_solicitud_exige_su_evento_y_el_estado_de_cuenta_del_contrato(self):
        self.sembrar()
        s = A.solicitudes_cambio()[4]
        s.id, s.evento_id = 'SC-NUEVA', 'EV-INEXISTENTE'
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            self.f.guardar(self.f.repos.cambios, s)
        self.assertEqual(ctx.exception.restriccion, 'fk_solicitud_cambio_evento')
        s2 = A.solicitudes_cambio()[4]
        s2.id, s2.contrato_id = 'SC-NUEVA2', 'CT-2'                          # EC-1 no es el estado de cuenta del contrato CT-2
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            self.f.guardar(self.f.repos.cambios, s2)
        self.assertEqual(ctx.exception.restriccion, 'fk_solicitud_cambio_estado_cuenta')

    def test_guardar_es_atomico_si_una_fila_hija_viola_una_restriccion(self):
        self.sembrar()
        ec = self.f.repos.estados_cuenta.obtener_por_id('EC-1')               # leído: se actualiza con control de versión
        ec.pagos[0].obligacion_id = 'OB-NO-EXISTE'                           # el pago apunta a una obligación inexistente
        antes = self.contar('pago')
        ec.devoluciones[0].comprobante = 'Cambiado'                          # una modificación válida que debe revertirse
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            self.f.guardar(self.f.repos.estados_cuenta, ec)
        self.assertEqual(self.contar('pago'), antes)
        self.assertEqual(self.f.repos.estados_cuenta.obtener_por_id('EC-1').devoluciones[0].comprobante, 'Transferencia 99')

    def test_la_referencia_sin_fk_no_la_protege_la_base(self):
        # Límite documentado (D-01): sin clave foránea, PostgreSQL acepta una referencia blanda inexistente.
        self.sembrar()
        e = self.f.repos.eventos.obtener_por_id('EV-1')
        e.cliente_id = 'CLIENTE-QUE-NO-EXISTE'
        self.f.guardar(self.f.repos.eventos, e)
        ec = self.f.repos.estados_cuenta.obtener_por_id('EC-3')
        ec._cierres_sin_realizar['SOLICITUD-FANTASMA'] = (T0, False)
        self.f.guardar(self.f.repos.estados_cuenta, ec)
        self.assertIn('SOLICITUD-FANTASMA', self.f.repos.estados_cuenta.obtener_por_id('EC-3')._cierres_sin_realizar)

    def test_un_valor_fuera_de_rango_se_traduce_a_error_de_datos(self):
        e = A.eventos()[1]
        object.__setattr__(e.datos, 'invitados_aproximados', 9223372036854775808)     # esquiva el dominio a propósito
        with self.assertRaises(ErrorDeDatos):
            self.f.guardar(self.f.repos.eventos, e)
        self.assertEqual(self.contar('evento'), 0)

    def test_check_de_base_de_datos_ultima_barrera(self):
        e = A.eventos()[1]
        object.__setattr__(e.datos, 'invitados_aproximados', -5)
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            self.f.guardar(self.f.repos.eventos, e)
        self.assertEqual(ctx.exception.restriccion, 'ck_evento_invitados_positivo')

    def test_importe_no_finito_que_esquiva_el_dominio_lo_rechaza_la_base(self):
        self.sembrar()
        ec = self.f.repos.estados_cuenta.obtener_por_id('EC-2')
        object.__setattr__(ec.obligaciones['OB-9'].importe, 'cantidad', D('NaN'))
        with self.assertRaises(ViolacionDeRestriccion) as ctx:
            self.f.guardar(self.f.repos.estados_cuenta, ec)
        self.assertEqual(ctx.exception.restriccion, 'ck_obligacion_pago_importe_valido')


if __name__ == '__main__':
    unittest.main()
