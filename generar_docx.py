import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn
from pathlib import Path

def set_cell_background(cell, hex_color):
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_cell_margins(cell, top=120, bottom=120, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('w:top', top), ('w:bottom', bottom), ('w:left', left), ('w:right', right)]:
        node = OxmlElement(m)
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def create_document():
    doc = docx.Document()

    # Configuración de márgenes
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Estilos de fuentes principales
    style_normal = doc.styles['Normal']
    style_normal.font.name = 'Calibri'
    style_normal.font.size = Pt(11)
    style_normal.font.color.rgb = RGBColor(30, 41, 59) # Slate oscuro

    # ==============================================================================
    # PORTADA / ENCABEZADO PRINCIPAL
    # ==============================================================================
    p_pre = doc.add_paragraph()
    p_pre.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run_pre = p_pre.add_run("DOCUMENTO TÉCNICO DE SUSTENTACIÓN ACADÉMICA // BACKEND API")
    run_pre.font.name = 'Consolas'
    run_pre.font.size = Pt(9.5)
    run_pre.font.bold = True
    run_pre.font.color.rgb = RGBColor(100, 116, 139)

    title_p = doc.add_paragraph()
    title_run = title_p.add_run("Arquitectura, Seguridad y Lógica de Negocio:")
    title_run.font.name = 'Calibri'
    title_run.font.size = Pt(18)
    title_run.font.color.rgb = RGBColor(71, 85, 105)
    
    title_p2 = doc.add_paragraph()
    title_run2 = title_p2.add_run("API de Pasarela de Pagos & Sistema de Facturación JSON")
    title_run2.font.name = 'Calibri'
    title_run2.font.size = Pt(24)
    title_run2.font.bold = True
    title_run2.font.color.rgb = RGBColor(15, 23, 42) # Obsidian Navy
    title_p2.paragraph_format.space_after = Pt(14)

    # Meta banner
    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_after = Pt(24)
    p_meta_run = p_meta.add_run("Tecnologías: Python 3.10+ | Flask | SQLite3 | PyJWT | Werkzeug Security | python-dotenv\nPatrones: RESTful Stateless API, RBAC (Role-Based Access Control), Decorator Pattern")
    p_meta_run.font.size = Pt(10)
    p_meta_run.font.italic = True
    p_meta_run.font.color.rgb = RGBColor(100, 116, 139)

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # Función auxiliar para títulos de sección
    def add_section_header(num, title):
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(20)
        h.paragraph_format.space_after = Pt(6)
        r_num = h.add_run(f"{num}. ")
        r_num.font.name = 'Calibri'
        r_num.font.size = Pt(14)
        r_num.font.bold = True
        r_num.font.color.rgb = RGBColor(99, 102, 241) # Indigo accent
        r_title = h.add_run(title)
        r_title.font.name = 'Calibri'
        r_title.font.size = Pt(14)
        r_title.font.bold = True
        r_title.font.color.rgb = RGBColor(15, 23, 42)

    def add_subsection_header(title):
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(12)
        h.paragraph_format.space_after = Pt(4)
        r = h.add_run(title)
        r.font.name = 'Calibri'
        r.font.size = Pt(12)
        r.font.bold = True
        r.font.color.rgb = RGBColor(30, 41, 59)

    def add_callout(text, prefix="PUNTO CLAVE PARA LA DEFENSA: "):
        table = doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = table.cell(0, 0)
        set_cell_background(cell, "F8FAFC")
        set_cell_margins(cell, top=140, bottom=140, left=180, right=180)
        cell.width = Inches(6.5)
        
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        r_p = p.add_run(prefix)
        r_p.font.bold = True
        r_p.font.size = Pt(9.5)
        r_p.font.color.rgb = RGBColor(15, 23, 42)
        
        r_t = p.add_run(text)
        r_t.font.size = Pt(9.5)
        r_t.font.color.rgb = RGBColor(51, 65, 85)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    # ==============================================================================
    # SECCIÓN 1: INTRODUCCIÓN Y ARQUITECTURA
    # ==============================================================================
    add_section_header("1", "Introducción y Arquitectura General del Sistema")
    
    p = doc.add_paragraph()
    p.add_run(
        "El proyecto implementa una API RESTful completamente desacoplada y construida bajo el principio de "
    )
    p.add_run("Statelessness (ausencia de estado en el servidor)").bold = True
    p.add_run(
        ". En este paradigma, cada solicitud HTTP entrante viaja con toda la información necesaria para ser autenticada, "
        "autorizada y procesada de forma independiente, eliminando la dependencia de sesiones volátiles en memoria."
    )

    p2 = doc.add_paragraph()
    p2.add_run("El diseño sigue los estándares de la metodología ")
    p2.add_run("12-Factor App").bold = True
    p2.add_run(
        ", asegurando que la configuración y secretos críticos (como la clave de firma del JWT, credenciales por defecto "
        "del administrador y el identificador de la base de datos) permanezcan aislados del código mediante el archivo "
    )
    p2.add_run(".env").bold = True
    p2.add_run(
        " y cargados dinámicamente con la librería `python-dotenv`. Esto garantiza que los secretos nunca se expongan en el control de versiones (Git)."
    )

    add_callout(
        "El microframework Flask fue seleccionado por su diseño minimalista y control total sobre el ciclo de vida de la petición HTTP, "
        "permitiendo gestionar directamente la factoría de conexiones a SQLite y la ejecución de middleware de autorización sin sobrecargas innecesarias."
    )

    # ==============================================================================
    # SECCIÓN 2: SEGURIDAD, JWT Y RBAC
    # ==============================================================================
    add_section_header("2", "Seguridad: Autenticación, Hashing y Control de Acceso por Roles (RBAC)")

    add_subsection_header("2.1 Almacenamiento Criptográfico de Contraseñas")
    p = doc.add_paragraph()
    p.add_run(
        "Para proteger las credenciales contra ataques de filtración o lectura directa de la base de datos, no se almacenan contraseñas en texto plano. "
        "Se utiliza la librería `werkzeug.security` con dos funciones primordiales:\n"
    )
    p.add_run("• generate_password_hash(password): ").bold = True
    p.add_run("Aplica funciones criptográficas de derivación de claves con sal (salt) aleatorio (por defecto pbkdf2/scrypt).\n")
    p.add_run("• check_password_hash(hash, password): ").bold = True
    p.add_run("Realiza una comparación en tiempo constante para mitigar ataques de temporización (timing attacks).")

    add_subsection_header("2.2 Implementación de JSON Web Tokens (PyJWT)")
    p = doc.add_paragraph()
    p.add_run(
        "El mecanismo de autenticación es sin estado. Al enviar credenciales válidas a `POST /login`, el servidor genera un token JWT firmado "
        "digitalmente con el algoritmo simétrico HMAC-SHA256 (HS256). El payload del token estructura los siguientes claims obligatorios:\n"
    )
    p.add_run("• user: ").bold = True
    p.add_run("Identificador único del usuario autenticado (username).\n")
    p.add_run("• rol: ").bold = True
    p.add_run("Rol asignado para control de acceso ('admin' o 'usuario').\n")
    p.add_run("• exp: ").bold = True
    p.add_run("Marca de tiempo (timestamp UTC) calculada dinámicamente a partir de la variable `JWT_EXPIRATION_HOURS` para limitar la ventana de exposición.")

    add_subsection_header("2.3 Middleware de Autorización: El Patrón Decorador (@token_requerido)")
    p = doc.add_paragraph()
    p.add_run(
        "Para desacoplar la lógica de seguridad de los controladores de rutas, se implementó el Patrón Decorador mediante "
        "`@token_requerido` utilizando `functools.wraps`. Este componente ejecuta tres fases de inspección:\n"
    )
    p.add_run("1. Extracción de Credenciales: ").bold = True
    p.add_run("Inspecciona la cabecera HTTP `Authorization`, validando el formato `Bearer <token>`.\n")
    p.add_run("2. Verificación de Firma y Expiración: ").bold = True
    p.add_run("Ejecuta `jwt.decode`. Si el token expiró (`ExpiredSignatureError`) o fue alterado (`InvalidTokenError`), responde con código 401 Unauthorized.\n")
    p.add_run("3. Validación de Roles (RBAC): ").bold = True
    p.add_run("Si el endpoint especifica roles requeridos (ej. `@token_requerido(roles=['admin'])` o `@solo_admin`), compara el rol del claim. Si el usuario no tiene los privilegios suficientes, deniega la petición con código 403 Forbidden.\n")
    p.add_run("4. Inyección de Contexto: ").bold = True
    p.add_run("Si todo es correcto, inyecta el payload en `request.usuario_actual` para registrar auditoría (campo `creado_por`).")

    add_callout(
        "Diferencia semántica clave entre 401 y 403: El código 401 Unauthorized indica un fallo de Autenticación (¿quién eres? No tienes token o expiró). "
        "El código 403 Forbidden indica un fallo de Autorización (sé quién eres, pero tu rol no tiene permiso para ejecutar esta acción).",
        "PREGUNTA TÍPICA DE EXAMEN: "
    )

    # ==============================================================================
    # SECCIÓN 3: PERSISTENCIA Y MODELADO DE DATOS (SQLITE)
    # ==============================================================================
    add_section_header("3", "Capa de Persistencia y Modelado de Datos (SQLite)")
    
    p = doc.add_paragraph()
    p.add_run(
        "La persistencia se apoya en SQLite3 configurado con `sqlite3.Row` como `row_factory`, lo que permite mapear columnas por nombre como diccionarios. "
        "En lugar de depender de un ORM pesado que oculte el costo computacional, se optó por sentencias SQL directas con restricciones relacionales explícitas:"
    )

    # Tabla de Esquemas
    table_db = doc.add_table(rows=4, cols=3)
    table_db.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_db.autofit = False

    headers = ["Tabla", "Columnas Principales", "Restricciones de Integridad (Constraints)"]
    for i, h in enumerate(headers):
        cell = table_db.cell(0, i)
        set_cell_background(cell, "0F172A")
        set_cell_margins(cell, top=100, bottom=100, left=120, right=120)
        p = cell.paragraphs[0]
        run = p.add_run(h)
        run.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)
        run.font.size = Pt(9.5)

    db_rows = [
        ("usuarios", "id, username, password, rol, email, fecha_creacion", "username UNIQUE NOT NULL, rol CHECK (rol IN ('admin', 'usuario'))"),
        ("pagos", "id, cliente, monto, moneda, metodo_pago, estado, creado_por, fecha_creacion", "monto REAL CHECK (monto > 0), estado y metodo_pago validados por catálogo"),
        ("facturas", "id, numero_factura, pago_id, cliente, items, subtotal, impuesto, total, moneda, estado, creado_por", "numero_factura UNIQUE NOT NULL, subtotal/impuesto/total >= 0, FOREIGN KEY (pago_id) REFERENCES pagos (id) ON DELETE SET NULL")
    ]

    for row_idx, data in enumerate(db_rows, start=1):
        bg = "FFFFFF" if row_idx % 2 != 0 else "F8FAFC"
        for col_idx, text in enumerate(data):
            cell = table_db.cell(row_idx, col_idx)
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
            p = cell.paragraphs[0]
            run = p.add_run(text)
            run.font.size = Pt(9)
            if col_idx == 0:
                run.bold = True

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    p_mig = doc.add_paragraph()
    p_mig.add_run("Manejo de Migración y Sembrado Defensivo (`init_db`):\n").bold = True
    p_mig.add_run(
        "Al arrancar la aplicación se asegura la existencia de las tablas mediante `CREATE TABLE IF NOT EXISTS`. "
        "Si la base de datos ya existía con esquemas previos, ejecuta una introspección de esquema vía `PRAGMA table_info` "
        "y agrega columnas faltantes (como `creado_por`) con `ALTER TABLE`. Adicionalmente, verifica si existen los usuarios `admin` y `usuario`; "
        "si no están presentes, los siembra automáticamente con sus contraseñas hasheadas a partir de las variables del `.env`."
    )

    # ==============================================================================
    # SECCIÓN 4: MOTOR DE FACTURACIÓN JSON
    # ==============================================================================
    add_section_header("4", "Motor de Facturación Electrónica en Formato JSON")

    p = doc.add_paragraph()
    p.add_run(
        "El módulo de facturación resuelve el almacenamiento estructurado y cálculo impositivo en formato JSON interoperable. "
        "Sus componentes de ingeniería principales son:"
    )

    add_subsection_header("4.1 Motor de Validación y Cálculo Matemático (`validar_factura`)")
    p = doc.add_paragraph()
    p.add_run(
        "Antes de persistir, la función valida semánticamente la petición:\n"
        "• Valida que cada artículo contenga descripción, cantidad mayor que cero y precio unitario finito positivo.\n"
        "• Calcula el subtotal exacto acumulado: subtotal = ∑ (cantidad * precio_unitario).\n"
        "• Aplica la tasa de impuesto (IVA) enviada o por defecto (19.0%) calculando: impuesto = round(subtotal * (tasa / 100), 2).\n"
        "• Calcula el importe total: total = round(subtotal + impuesto, 2)."
    )

    add_subsection_header("4.2 Emisión Polimórfica (Factura Manual vs Ligada a Pago)")
    p = doc.add_paragraph()
    p.add_run("El endpoint `POST /facturas` admite dos modalidades operativas:\n")
    p.add_run("1. Factura Directa: ").bold = True
    p.add_run("El cliente envía una lista libre de artículos en el array JSON `items`.\n")
    p.add_run("2. Factura Derivada de Pago (`pago_id`): ").bold = True
    p.add_run(
        "Si se referencia un pago existente, el backend consulta `pagos`, comprueba su existencia, hereda el cliente y la moneda, "
        "y si el array de items no viene provisto, autogenera una línea contable con la descripción del pago y su monto. Si el pago tiene estado "
        "'aprobado', la factura se emite directamente con estado 'pagada'."
    )

    add_subsection_header("4.3 Algoritmo de Correlativos sin Colisión (`generar_numero_factura`)")
    p = doc.add_paragraph()
    p.add_run(
        "Para evitar fallas de unicidad (`UNIQUE constraint failed`), el generador no usa un conteo estático `COUNT(*)`, ya que la eliminación de "
        "registros previos generaría duplicados. En su lugar, consulta `MAX(id)` de la tabla y ejecuta una verificación cíclica hasta encontrar "
        "el siguiente consecutivo disponible con formato formal: "
    )
    p.add_run("FAC-YYYY-NNNN").bold = True
    p.add_run(" (ejemplo: `FAC-2026-0001`).")

    add_subsection_header("4.4 Documento Oficial de Facturación Electrónica y Hash SHA-256 (`GET /facturas/<id>/json`)")
    p = doc.add_paragraph()
    p.add_run(
        "El backend expone un endpoint de exportación formal que serializa el documento en una estructura contable de intercambio:\n"
        "• Encabezado con versión del estándar (1.0), número de factura y estado.\n"
        "• Emisor fiscal: Datos de la empresa emisora parametrizados en el `.env` (Razón Social, NIT, Email, Ciudad).\n"
        "• Receptor: Cliente, documento de identidad o NIT y correo electrónico.\n"
        "• Pago asociado: Datos de trazabilidad de la pasarela si proviene de un pago.\n"
        "• Desglose impositivo: Subtotal, tasa y valor discriminado de IVA, y total a pagar.\n"
        "• Hash de Integridad SHA-256: Un digest digital generado mediante `hashlib.sha256` a partir de `numero_factura + total + fecha_emision + SECRET_KEY`. "
        "Permite que un tercero verifique si los datos de la factura sufrieron alguna alteración."
    )

    # ==============================================================================
    # SECCIÓN 5: TABLA DE ENDPOINTS Y CONTROL DE ACCESO
    # ==============================================================================
    add_section_header("5", "Mapeo de Endpoints y Matriz de Control de Acceso")

    table_ep = doc.add_table(rows=13, cols=4)
    table_ep.alignment = WD_TABLE_ALIGNMENT.CENTER
    table_ep.autofit = False


    ep_headers = ["Método", "Endpoint", "Acceso / Rol Mínimo", "Función y Códigos HTTP"]
    for i, h in enumerate(ep_headers):
        cell = table_ep.cell(0, i)
        set_cell_background(cell, "0F172A")
        set_cell_margins(cell, top=100, bottom=100, left=100, right=100)
        p = cell.paragraphs[0]
        run = p.add_run(h)
        run.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)
        run.font.size = Pt(9)

    endpoints_data = [
        ("POST", "/login", "Público", "Autentica credenciales y genera token JWT (200 / 401)."),
        ("POST", "/registro", "Público", "Registra usuario estándar. Rol 'admin' requiere token admin (201 / 400 / 403 / 409)."),
        ("GET", "/auth/me", "JWT (Cualquiera)", "Consulta perfil y rol del token activo (200 / 401)."),
        ("GET", "/usuarios", "JWT (Solo Admin)", "Lista todos los usuarios de la base de datos (200 / 403)."),
        ("GET", "/pagos", "Público", "Lista todos los pagos registrados (200)."),
        ("GET", "/pagos/<id>", "Público", "Consulta detalle de un pago por su ID (200 / 404)."),
        ("POST", "/pagos", "JWT (Cualquiera)", "Registra un pago simulado asociando su creador (201 / 400 / 401)."),
        ("PUT", "/pagos/<id>", "JWT (Solo Admin)", "Actualiza los datos de un pago existente (200 / 400 / 403 / 404)."),
        ("DELETE", "/pagos/<id>", "JWT (Solo Admin)", "Elimina físicamente un pago de la base de datos (200 / 403 / 404)."),
        ("POST", "/facturas", "JWT (Cualquiera)", "Emite una nueva factura con items en formato JSON (201 / 400 / 401)."),
        ("GET", "/facturas", "JWT (Cualquiera)", "Lista facturas con filtros (?cliente, ?estado, ?pago_id) (200 / 401)."),
        ("GET", "/facturas/<id>/json", "JWT (Cualquiera)", "Retorna documento estándar JSON con firma SHA-256 (200 / 401 / 404)."),
    ]

    for row_idx, data in enumerate(endpoints_data, start=1):
        bg = "FFFFFF" if row_idx % 2 != 0 else "F8FAFC"
        for col_idx, text in enumerate(data):
            cell = table_ep.cell(row_idx, col_idx)
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=70, bottom=70, left=100, right=100)
            p = cell.paragraphs[0]
            run = p.add_run(text)
            run.font.size = Pt(8.5)
            if col_idx == 0:
                run.bold = True
                if text == "POST": run.font.color.rgb = RGBColor(16, 185, 129)
                elif text == "GET": run.font.color.rgb = RGBColor(99, 102, 241)
                elif text == "DELETE": run.font.color.rgb = RGBColor(239, 68, 68)
                elif text == "PUT": run.font.color.rgb = RGBColor(245, 158, 11)

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # ==============================================================================
    # SECCIÓN 6: CALIDAD DE SOFTWARE Y TESTING
    # ==============================================================================
    add_section_header("6", "Garantía de Calidad: Suite de Pruebas Unitarias (`test_main.py`)")

    p = doc.add_paragraph()
    p.add_run(
        "El backend cuenta con una suite completa de 11 pruebas unitarias implementadas con el framework nativo `unittest`, "
        "diseñadas bajo los principios de pruebas atómicas e independientes:\n\n"
    )
    p.add_run("• Ciclo de Vida Aislado (setUp y tearDown): ").bold = True
    p.add_run(
        "En cada método de prueba se crea un archivo de base de datos temporal con `tempfile.NamedTemporaryFile`, se inicializan los esquemas "
        "con `init_db()` y se destruye el archivo al finalizar con `os.unlink`. Esto garantiza que los tests nunca interfieran con la base de datos real "
        "y sean 100% reproducibles.\n"
    )
    p.add_run("• Cobertura de Pruebas: ").bold = True
    p.add_run(
        "Se evalúan flujos positivos y negativos: autenticación con credenciales erróneas (401), validación de payloads con tipos erróneos o montos negativos (400), "
        "restricción estricta de roles donde un usuario común intenta mutar pagos o ver usuarios recibiendo 403 Forbidden, y el ciclo de vida completo de emisión, consulta y borrado de facturas."
    )

    # ==============================================================================
    # SECCIÓN 7: PREGUNTAS CLAVE PARA LA DEFENSA
    # ==============================================================================
    add_section_header("7", "Preguntas Frecuentes en una Sustentación Académica")

    faq_items = [
        (
            "¿Por qué elegiste JWT y no sesiones tradicionales basadas en Cookies / Session ID?",
            "Porque JWT es Stateless. En aplicaciones web modernas y arquitecturas de microservicios, el servidor no necesita consultar una base de datos o almacenamiento en caché (Redis) en cada petición para comprobar si la sesión existe. Permite escalabilidad horizontal inmediata detrás de cualquier balanceador de carga."
        ),
        (
            "¿Cómo se garantiza la seguridad si el token JWT puede ser decodificado en Base64 por cualquiera?",
            "La seguridad de JWT no reside en el cifrado de los datos (la información es legible), sino en su FIRMA DIGITAL. El payload viaja firmado criptográficamente con `JWT_SECRET_KEY` en el servidor. Si un atacante modifica el rol de 'usuario' a 'admin' en el token, la firma ya no coincidirá matemáticamente y la función `jwt.decode` rechazará la petición con un error 401."
        ),
        (
            "¿Cómo manejas los tipos de datos compuestos como listas de artículos en SQLite?",
            "SQLite no cuenta con un tipo de dato nativo ARRAY o JSONB como PostgreSQL. Por ello, la lista de artículos se serializa a texto JSON estándar (`json.dumps`) para su persistencia en disco, y se deserializa (`json.loads`) en la función `formatear_factura` al responder la petición HTTP, garantizando una respuesta como objeto JSON estructurado."
        ),
        (
            "¿Qué medidas se tomaron para la protección de secretos en entornos colaborativos (Git)?",
            "Se implementó el patrón de Variables de Entorno con `.env`. El archivo con secretos reales está explícitamente ignorado en `.gitignore` para prevenir fugas de credenciales en repositorios públicos. Simultáneamente, se construyó un archivo `.env.example` con la estructura de variables requerida como plantilla para nuevos despliegues."
        )
    ]

    for q, a in faq_items:
        p_q = doc.add_paragraph()
        p_q.paragraph_format.space_before = Pt(8)
        p_q.paragraph_format.space_after = Pt(2)
        r_q = p_q.add_run(f"P: {q}")
        r_q.bold = True
        r_q.font.color.rgb = RGBColor(15, 23, 42)

        p_a = doc.add_paragraph()
        p_a.paragraph_format.space_before = Pt(0)
        p_a.paragraph_format.space_after = Pt(8)
        r_a = p_a.add_run(f"R: {a}")
        r_a.font.color.rgb = RGBColor(71, 85, 105)

    # Pie de página final
    p_foot = doc.add_paragraph()
    p_foot.paragraph_format.space_before = Pt(24)
    p_foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_foot = p_foot.add_run("— Fin del Documento Técnico —")
    r_foot.font.italic = True
    r_foot.font.size = Pt(9)
    r_foot.font.color.rgb = RGBColor(148, 163, 184)

    output_path = Path("Explicacion_Backend_Pasarela_Pagos.docx").resolve()
    doc.save(str(output_path))
    print(f"Documento generado exitosamente en: {output_path}")

if __name__ == "__main__":
    create_document()
