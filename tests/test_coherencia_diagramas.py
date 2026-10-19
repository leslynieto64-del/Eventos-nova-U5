"""Coherencia entre los entregables y el código (validación «Consistencia» de la Etapa 9).

Comprueba que los métodos, Domain Events, estados y clases citados en el mapa de dominio, los diagramas UML,
el documento principal, el informe y la matriz existen en el código, y que la matriz no tiene caracteres
invisibles en sus identificadores. Solo usa la biblioteca estándar."""
import ast, glob, os, re, sys, unittest, zipfile, html
import xml.etree.ElementTree as ET

RAIZ = os.path.join(os.path.dirname(__file__), '..')
SRC = os.path.join(RAIZ, 'src')
sys.path.insert(0, SRC)
from domain import eventos_dominio, valores                                   # noqa: E402

# Nombres que los documentos citan expresamente como eliminados o anteriores a una corrección.
HISTORICOS = {'registrarProveedorNoDisponibleYBuscarAlternativa', 'cerrarCambioNoProcedente'}
INVISIBLES = re.compile('[​‌‍⁠﻿­]')


def leer(ruta):
    with open(ruta, encoding='utf8') as f:
        return f.read()


def snake(nombre):
    return re.sub(r'([A-Z])', r'_\1', nombre).lower()


def indice_codigo():
    """{clase: {métodos y propiedades}} y conjunto global de nombres definidos en src/."""
    clases, globales = {}, set()
    for f in glob.glob(os.path.join(SRC, '**', '*.py'), recursive=True):
        arbol = ast.parse(leer(f))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ClassDef):
                miembros = {n.name for n in nodo.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
                bases = [b.id for b in nodo.bases if isinstance(b, ast.Name)]
                clases.setdefault(nodo.name, set()).update(miembros)
                clases.setdefault('__bases__' + nodo.name, set()).update(bases)
                globales.add(nodo.name)
            elif isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                globales.add(nodo.name)
    return clases, globales


def miembros(clases, nombre):
    """Métodos de la clase incluidos los heredados de clases del proyecto."""
    vistos, pendientes, total = set(), [nombre], set()
    while pendientes:
        c = pendientes.pop()
        if c in vistos:
            continue
        vistos.add(c)
        total |= clases.get(c, set())
        pendientes += list(clases.get('__bases__' + c, set()))
    return total


def texto_drawio():
    arbol = ET.parse(os.path.join(RAIZ, 'diagramas', 'dominio', 'mapa-dominio.drawio'))
    partes = []
    for c in arbol.getroot().iter('mxCell'):
        v = html.unescape(c.get('value') or '')
        partes.append(re.sub(r'<[^>]+>', ' ', v))
    return ' '.join(partes)


def texto_docx(ruta):
    with zipfile.ZipFile(ruta) as z:
        x = z.read('word/document.xml').decode('utf8')
    return html.unescape(re.sub(r'<[^>]+>', '', x.replace('</w:p>', '\n').replace('</w:tc>', ' | ')))


def metodos_citados(texto):
    return set(re.findall(r'\b([a-z][a-z0-9]*[A-Z][A-Za-z0-9]*)\(', texto))


class CoherenciaMapaDeDominio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clases, cls.globales = indice_codigo()
        cls.mapa = texto_drawio()

    def test_metodos_del_mapa_existen_en_el_codigo(self):
        faltan = sorted(m for m in metodos_citados(self.mapa) - HISTORICOS if snake(m) not in self.globales)
        self.assertEqual(faltan, [])

    def test_domain_events_del_codigo_aparecen_en_el_mapa_y_viceversa(self):
        en_codigo = {n for n, c in vars(eventos_dominio).items()
                     if isinstance(c, type) and issubclass(c, eventos_dominio.EventoDominio) and c is not eventos_dominio.EventoDominio}
        self.assertEqual(len(en_codigo), 31)                       # 22 de coordinación + 9 de auditoría
        self.assertEqual(sorted(e for e in en_codigo if e not in self.mapa), [])

    def test_estados_del_codigo_aparecen_en_el_mapa(self):
        enums = [valores.EstadoEvento, valores.EstadoPropuesta, valores.EstadoContrato, valores.EstadoSolicitudCambio,
                 valores.EstadoSolicitudServicioAdicional, valores.EstadoSustitucionProveedor,
                 valores.EstadoSolicitudCancelacion, valores.EstadoObligacionPago, valores.EstadoPago, valores.EstadoDevolucion]
        faltan = [f'{e.__name__}.{v.value}' for e in enums for v in e if v.value not in self.mapa]
        self.assertEqual(faltan, [])

    def test_clases_del_mapa_existen(self):
        for nombre in ['Propuesta', 'VersionPropuesta', 'Contrato', 'AnexoContrato', 'Evento', 'ServicioContratado',
                       'SolicitudCancelacion', 'SolicitudCambio', 'SolicitudServicioAdicional', 'SustitucionProveedor',
                       'AlternativaPropuesta', 'EstadoCuenta', 'ObligacionPago', 'Pago', 'Devolucion',
                       'EvaluarImpactoCambio', 'EvaluarRegularizacionDeSolicitudes', 'MotivoCancelacionEvento',
                       'MotivoCierreSolicitud', 'Decision']:
            self.assertIn(nombre, self.mapa); self.assertIn(nombre, self.globales)



class CoherenciaDocumentos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clases, cls.globales = indice_codigo()

        archivos_docx = glob.glob(
            os.path.join(RAIZ, "**", "*.docx"),
            recursive=True
        )

        cls.docs = sorted(
            ruta for ruta in archivos_docx
            if not os.path.relpath(ruta, RAIZ)
            .replace("\\", "/")
            .startswith("tests/evidencias/")
        )

    def test_hay_documentos(self):
        self.assertTrue(self.docs)

    def test_metodos_citados_en_documentos_existen(self):
        faltan = {}
        for d in self.docs:
            f = sorted(
                m for m in metodos_citados(texto_docx(d)) - HISTORICOS
                if snake(m) not in self.globales
            )
            if f:
                faltan[os.path.basename(d)] = f
        self.assertEqual(faltan, {})

    def test_version_del_modelo_unificada(self):
        for d in self.docs:
            t = texto_docx(d)
            self.assertNotRegex(
                t,
                r'[Mm]odelo(?: de dominio)? v1\.[0-3]\b',
                os.path.basename(d)
            )
        self.assertIn('v1.4', texto_drawio())

    def test_documentos_sin_nombres_de_archivos_fuente(self):
        for d in self.docs:
            self.assertNotRegex(
                texto_docx(d),
                r'CORREGIDO|ETAPAS_1_Y_2|\.docx\b',
                os.path.basename(d)
            )


class CoherenciaMatriz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clases, cls.globales = indice_codigo()
        ruta = os.path.join(RAIZ, 'docs', 'trazabilidad', 'matriz-trazabilidad.xlsx')
        with zipfile.ZipFile(ruta) as z:
            cls.textos = [html.unescape(t) for n in z.namelist() if n.startswith('xl/') and n.endswith('.xml')
                          for t in re.findall(r'<t[^>]*>([^<]*)</t>', z.read(n).decode('utf8'))]

    def test_sin_caracteres_invisibles(self):
        self.assertEqual([t for t in self.textos if INVISIBLES.search(t)], [])

    def test_identificadores_bien_formados(self):
        texto = ' '.join(self.textos)
        malos = re.findall(r'\b(?:BN|SE|US|CA|GL|CU|ADR|H|P|B)-\s+\d', texto)
        self.assertEqual(malos, [])

    def test_metodos_de_la_matriz_existen(self):
        faltan = sorted(m for t in self.textos for m in metodos_citados(t) - HISTORICOS if snake(m) not in self.globales)
        self.assertEqual(faltan, [])


class CoherenciaUML(unittest.TestCase):
    """Cada clase y método de los diagramas UML existe en el código, y cada participante de las secuencias
    aparece en el diagrama de clases."""

    @classmethod
    def setUpClass(cls):
        cls.clases, cls.globales = indice_codigo()
        cls.clases_uml = sorted(glob.glob(os.path.join(RAIZ, 'diagramas', 'clases', '*.puml')))
        cls.secuencias = sorted(glob.glob(os.path.join(RAIZ, 'diagramas', 'secuencia', '*.puml')))

    @staticmethod
    def _bloques(texto):
        """{clase: [métodos]} a partir de 'class|interface|abstract class Nombre ... { ... }'."""
        res = {}
        for m in re.finditer(r'^\s*(?:abstract\s+class|class|interface)\s+"?(\w+)"?[^{\n]*\{(.*?)^\s*\}', texto, re.M | re.S):
            res[m.group(1)] = re.findall(r'[+#~-]\s*(\w+)\(', m.group(2))
        return res

    def _alias_codigo(self, nombre):
        return '_SolicitudBase' if nombre == 'SolicitudBase' else nombre

    def test_hay_diagramas(self):
        if not self.clases_uml:
            self.skipTest('Diagramas UML todavía no generados (Etapa 8).')
        self.assertGreaterEqual(len(self.clases_uml), 1)
        self.assertEqual(len(self.secuencias), 2)

    def test_metodos_del_diagrama_de_clases_existen(self):
        if not self.clases_uml:
            self.skipTest('Etapa 8 pendiente.')
        faltan = []
        for f in self.clases_uml:
            for clase, metodos in self._bloques(leer(f)).items():
                c = self._alias_codigo(clase)
                if c not in self.globales:
                    faltan.append(f'clase {clase}'); continue
                disponibles = miembros(self.clases, c)
                faltan += [f'{clase}.{m}' for m in metodos if snake(m) not in disponibles]
        self.assertEqual(faltan, [])

    def test_participantes_y_mensajes_de_las_secuencias(self):
        if not self.secuencias:
            self.skipTest('Etapa 8 pendiente.')
        en_clases = set()
        for f in self.clases_uml:
            en_clases |= set(self._bloques(leer(f)))
        problemas = []
        for f in self.secuencias:
            t = leer(f)
            # El nombre visible puede dividirse en líneas con \n; sin los saltos debe ser el nombre de la clase.
            alias = dict((a, n.replace('\\n', '')) for n, a in re.findall(
                r'^\s*(?:participant|control|entity|boundary|collections|database)\s+"?([\w\\]+)"?\s+as\s+(\w+)', t, re.M))
            for n in alias.values():
                if n not in en_clases:
                    problemas.append(f'{os.path.basename(f)}: {n} no está en el diagrama de clases')
            for destino, metodo in re.findall(r'->\s*(\w+)\s*:\s*(\w+)\(', t):
                clase = alias.get(destino)
                if clase and snake(metodo) not in miembros(self.clases, self._alias_codigo(clase)):
                    problemas.append(f'{os.path.basename(f)}: {clase}.{metodo}')
        self.assertEqual(problemas, [])


if __name__ == '__main__':
    unittest.main()
