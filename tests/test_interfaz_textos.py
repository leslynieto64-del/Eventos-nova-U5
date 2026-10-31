"""Textos visibles de la interfaz web: sin valores ausentes («null», «undefined») y sin referencias internas a requisitos.

1. Estático: ninguna cadena de texto de src/web contiene códigos internos (BN-…, CA-…, GL-…, SE-…, US-…, etc.); los comentarios del
   código y los documentos técnicos conservan sus referencias.
2. `humanizar` (src/web/js/texto.js, se ejecuta con Node): para TODOS los mensajes de negocio que pueden devolver el dominio, la aplicación y
   la API, el texto que ve el usuario no contiene códigos internos, conserva el motivo y respeta los identificadores de datos (EV-…, PV-…).
3. `sinVacios`: los valores ausentes no llegan al DOM (causa del texto «null» en los cuadros de confirmación).
Las pruebas con navegador real (diálogos y pantallas) están en scripts/probar_interfaz_navegador.mjs y probar_proveedores_navegador.mjs.
Ejecutar desde la raíz:  python -m unittest tests.test_interfaz_textos -v"""
import ast, json, os, re, shutil, subprocess, sys, tempfile, unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WEB = os.path.join(RAIZ, 'src', 'web')
# Códigos de documentos internos. Los identificadores de datos (EV-, PV-, CT-, EC-, PR-, SC-, SA-, SP-, OB-, CL-) no cuentan.
CODIGO = re.compile(r'\b(?:BN|CA|GL|SE|US|CU|RN|AR|TP|ADR|[ACDEHR])-\d{1,3}[A-Za-z]?\b(?!-)')
NODE = shutil.which('node')


def _sin_comentarios_js(texto):
    texto = re.sub(r'/\*.*?\*/', '', texto, flags=re.S)
    salida = []
    for linea in texto.splitlines():
        # quita «// comentario» que no esté dentro de una cadena (heurística: antes de la barra hay un número par de comillas)
        for m in re.finditer(r'//', linea):
            antes = linea[:m.start()]
            if all(antes.count(q) % 2 == 0 for q in ("'", '"', '`')) and not antes.rstrip().endswith(':'):
                linea = antes
                break
        salida.append(linea)
    return '\n'.join(salida)


def _cadenas(texto):
    return re.findall(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`", texto, flags=re.S)


def _archivos(ext):
    for d, _, fs in os.walk(WEB):
        for f in fs:
            if f.endswith(ext):
                yield os.path.join(d, f)


class SinCodigosInternosEnElCodigoDeLaInterfaz(unittest.TestCase):
    def test_ninguna_cadena_visible_contiene_codigos_internos(self):
        encontrados = []
        for f in list(_archivos('.js')) + list(_archivos('.html')):
            texto = open(f, encoding='utf-8').read()
            cuerpo = _sin_comentarios_js(texto) if f.endswith('.js') else re.sub(r'<!--.*?-->', '', texto, flags=re.S)
            for c in (_cadenas(cuerpo) if f.endswith('.js') else [cuerpo]):
                for m in CODIGO.finditer(c):
                    encontrados.append(f'{os.path.relpath(f, RAIZ)}: {m.group(0)} en {c[:90]!r}')
        self.assertEqual(encontrados, [])


@unittest.skipUnless(NODE, 'Node.js no está instalado')
class HumanizarYSinVacios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='enova-texto-')
        shutil.copy(os.path.join(WEB, 'js', 'texto.js'), os.path.join(cls.tmp, 'texto.mjs'))      # Node trata .js como CommonJS sin package.json
        cls.corredor = os.path.join(cls.tmp, 'corredor.mjs')
        with open(cls.corredor, 'w', encoding='utf-8') as f:
            f.write("import { humanizar, sinVacios, tieneCodigoInterno } from './texto.mjs';\n"
                    "import { readFileSync } from 'node:fs';\n"
                    "const entrada = JSON.parse(readFileSync(process.argv[2], 'utf-8'));\n"
                    "console.log(JSON.stringify({ textos: entrada.textos.map((t) => [humanizar(t), tieneCodigoInterno(humanizar(t))]),\n"
                    "  vacios: sinVacios('a', null, undefined, false, ['b', null, ['c']], 0, '').map(String) }));\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def ejecutar(self, textos):
        entrada = os.path.join(self.tmp, 'entrada.json')
        with open(entrada, 'w', encoding='utf-8') as f:
            json.dump({'textos': textos}, f)
        r = subprocess.run([NODE, self.corredor, entrada], capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_todos_los_mensajes_del_sistema_quedan_sin_codigos_internos(self):
        mensajes = set()
        for carpeta in ('domain', 'application', 'api'):
            for d, _, fs in os.walk(os.path.join(RAIZ, 'src', carpeta)):
                for f in (x for x in fs if x.endswith('.py')):
                    arbol = ast.parse(open(os.path.join(d, f), encoding='utf-8').read())
                    for n in ast.walk(arbol):
                        partes = []
                        if isinstance(n, ast.Constant) and isinstance(n.value, str):
                            partes = [n.value]
                        elif isinstance(n, ast.JoinedStr):
                            partes = [''.join(v.value if isinstance(v, ast.Constant) else '{}' for v in n.values)]
                        mensajes.update(p for p in partes if CODIGO.search(p) and ' ' in p and len(p) > 12)
        self.assertGreater(len(mensajes), 20)                       # el corpus real tiene decenas de mensajes con referencias
        resultado = self.ejecutar(sorted(mensajes))['textos']
        con_codigo = [(m, r[0]) for m, r in zip(sorted(mensajes), resultado) if r[1]]
        self.assertEqual(con_codigo, [])

    def test_conserva_el_motivo_y_los_identificadores_de_datos(self):
        casos = {
            'El proveedor no figura disponible para este servicio y fecha (CA-029, CA-031).': 'El proveedor no figura disponible para este servicio y fecha.',
            'Los proveedores solo se gestionan con el Evento En organización; el Evento está Cancelado (BN-009).':
                'Los proveedores solo se gestionan con el Evento En organización; el Evento está Cancelado.',
            'Pago y saldo (BN-005 y CA-027) no válidos (decisión E-3).': 'Pago y saldo no válidos.',
            'Rechazada según CA-052.': 'Rechazada.',
            'Servicio CT-9-S1 con PV-DEMO-BANQUETE-1 y EV-157c1d85-2609 (En organización)': 'Servicio CT-9-S1 con PV-DEMO-BANQUETE-1 y EV-157c1d85-2609 (En organización)',
            'La solicitud SC-1 está Registrada (pendiente).': 'La solicitud SC-1 está Registrada (pendiente).',
        }
        salida = self.ejecutar(list(casos))['textos']
        self.assertEqual([r[0] for r in salida], list(casos.values()))

    def test_los_valores_ausentes_no_llegan_al_dom(self):
        self.assertEqual(self.ejecutar([])['vacios'], ['a', 'b', 'c', '0', ''])


class CausaDelTextoNull(unittest.TestCase):
    def test_el_cuadro_de_confirmacion_no_pasa_valores_ausentes_al_dom(self):
        ui = open(os.path.join(WEB, 'js', 'ui.js'), encoding='utf-8').read()
        self.assertIn('vistaConfirmacion.replaceChildren(...sinVacios(', ui)
        self.assertNotRegex(ui, r'vistaConfirmacion\.replaceChildren\(h\(')       # la forma anterior: `def.aviso ? ... : null` escribía «null»


if __name__ == '__main__':
    unittest.main()
