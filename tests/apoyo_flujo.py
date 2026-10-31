"""Flujo de negocio reutilizable sobre CUALQUIER contenedor de composición (en memoria o persistente).

`Flujo(app)` recorre, con los servicios reales, la contratación completa de un evento (registro, propuesta, aceptación, contrato,
firma, política de no reembolso y anticipo verificado) y deja al evento «En organización». Sirve para ejecutar las mismas pruebas
sobre `construir()` y sobre la composición persistente."""
import os, sys
from datetime import timedelta
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))
from test_reglas_corregidas import T0, FECHA_EVENTO, CONTENIDO                       # noqa: E402,F401
from domain.valores import DatosEvento, Importe                                      # noqa: E402


class Flujo:
    def __init__(self, app):
        self.app = app
        self.s, self.d, self.repos = app.servicios, app.despachador, app.repos

    def registrar_evento(self, cliente='CL-1', tipo='Boda', lugar='Salón', invitados=100, servicios=('Banquete',)):
        r = self.s.propuestas.registrar_evento(cliente, DatosEvento(tipo, FECHA_EVENTO, lugar, invitados), list(servicios))
        return r.datos['evento_id']

    def contratar(self, evento_id=None, confirmar=True):
        """Devuelve un SimpleNamespace-like con evento_id, propuesta_id, contrato_id y ec_id."""
        s, d = self.s, self.d
        self.evento_id = evento_id or self.registrar_evento()
        self.propuesta_id = s.propuestas.crear_propuesta(self.evento_id, CONTENIDO, T0).datos['propuesta_id']
        p = self.repos.propuestas.obtener_por_id(self.propuesta_id)
        s.propuestas.aceptar_propuesta(self.propuesta_id, p.version_vigente_id, T0); d.despachar()
        self.contrato_id = s.contratacion.preparar_contrato(self.propuesta_id, True).datos['contrato_id']
        s.contratacion.registrar_firma_contrato(self.contrato_id, T0); d.despachar()
        self.ec_id = self.repos.estados_cuenta.obtener_por_contrato_id(self.contrato_id).id
        if confirmar:
            self.confirmar_contratacion()
        return self

    def confirmar_contratacion(self):
        self.s.contratacion.registrar_comunicacion_politica_no_reembolso(self.contrato_id, T0)
        ob = self.obligacion('Anticipo')
        self.s.pagos.registrar_y_verificar_pago(self.ec_id, ob.obligacion_id, Importe(D('3000.00')), T0 + timedelta(days=1), 'C-ANT')
        self.d.despachar()

    def ec(self):
        return self.repos.estados_cuenta.obtener_por_id(self.ec_id)

    def evento(self):
        return self.repos.eventos.obtener_por_id(self.evento_id)

    def obligacion(self, concepto):
        return next(o for o in self.ec().obligaciones.values() if o.concepto.value == concepto)
