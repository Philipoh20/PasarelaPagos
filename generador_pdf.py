"""
Módulo para generación de facturas en formato PDF de alta calidad profesional.
Diseñado para clientes comunes: limpio, elegante, sin terminología técnica ni JSON.
"""

import io
import hashlib
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """Canvas personalizado que agrega pie de página profesional con numeración."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        
        # Barra superior decorativa sutil
        self.setFillColor(colors.HexColor("#1E3A8A"))  # Azul corporativo profundo
        self.rect(0, letter[1] - 6, letter[0], 6, stroke=0, fill=1)
        
        # Pie de página
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(36, 40, letter[0] - 36, 40)

        # Texto del pie
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(
            36,
            26,
            "Documento emitido electrónicamente · Pasarela de Pagos Global S.A.S. · NIT 901.876.543-1"
        )
        pag_str = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(letter[0] - 36, 26, pag_str)

        self.restoreState()


def formatear_dinero(monto, moneda="COP"):
    """Formatea cantidades monetarias de forma estándar y comprensible."""
    try:
        val = float(monto or 0)
    except (ValueError, TypeError):
        val = 0.0

    moneda_upper = (moneda or "COP").upper()
    if moneda_upper == "COP":
        # Formato colombiano: $ 1.250.000 COP
        val_str = f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"${val_str} {moneda_upper}"
    else:
        # Formato internacional: $1,250.00 USD / EUR
        return f"${val:,.2f} {moneda_upper}"


def obtener_colores_estado(estado):
    """Devuelve color de fondo y texto para el sello de estado."""
    estado_normal = (estado or "").lower()
    if estado_normal == "pagada":
        return colors.HexColor("#DCFCE7"), colors.HexColor("#15803D"), "PAGADA"
    elif estado_normal == "anulada":
        return colors.HexColor("#FEE2E2"), colors.HexColor("#B91C1C"), "ANULADA"
    else:
        return colors.HexColor("#DBEAFE"), colors.HexColor("#1D4ED8"), "EMITIDA"


def generar_factura_pdf(factura, pago=None, empresa_info=None, secret_key=""):
    """
    Genera el PDF en memoria (bytes) con un diseño ejecutivo de nivel profesional.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=54,
    )

    if not empresa_info:
        empresa_info = {
            "nombre": "Pasarela de Pagos Global S.A.S.",
            "nit": "901.876.543-1",
            "email": "facturacion@pasarela.local",
            "ciudad": "Bogotá, Colombia",
            "telefono": "+57 (601) 800-PAGO",
            "web": "https://pasarela.local",
        }

    styles = getSampleStyleSheet()

    # Estilos tipográficos refinados
    style_empresa_nombre = ParagraphStyle(
        "EmpresaNombre",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor=colors.HexColor("#0F172A"),
    )
    style_empresa_detalles = ParagraphStyle(
        "EmpresaDetalles",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#475569"),
    )
    style_factura_titulo = ParagraphStyle(
        "FacturaTitulo",
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=2,  # Derecha
        textColor=colors.HexColor("#1E3A8A"),
    )
    style_factura_num = ParagraphStyle(
        "FacturaNum",
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        alignment=2,
        textColor=colors.HexColor("#0F172A"),
    )
    style_factura_meta = ParagraphStyle(
        "FacturaMeta",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        alignment=2,
        textColor=colors.HexColor("#64748B"),
    )

    style_card_header = ParagraphStyle(
        "CardHeader",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1E3A8A"),
    )
    style_card_body = ParagraphStyle(
        "CardBody",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1E293B"),
    )
    style_card_body_bold = ParagraphStyle(
        "CardBodyBold",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#0F172A"),
    )

    style_th = ParagraphStyle(
        "TableHead",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
    )
    style_th_right = ParagraphStyle(
        "TableHeadRight",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        alignment=2,
        textColor=colors.white,
    )
    style_th_center = ParagraphStyle(
        "TableHeadCenter",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        alignment=1,
        textColor=colors.white,
    )

    style_td = ParagraphStyle(
        "TableBody",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1E293B"),
    )
    style_td_right = ParagraphStyle(
        "TableBodyRight",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        alignment=2,
        textColor=colors.HexColor("#1E293B"),
    )
    style_td_center = ParagraphStyle(
        "TableBodyCenter",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        alignment=1,
        textColor=colors.HexColor("#1E293B"),
    )

    style_total_label = ParagraphStyle(
        "TotalLabel",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        alignment=2,
        textColor=colors.HexColor("#475569"),
    )
    style_total_val = ParagraphStyle(
        "TotalVal",
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        alignment=2,
        textColor=colors.HexColor("#0F172A"),
    )
    style_gran_total_label = ParagraphStyle(
        "GranTotalLabel",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        alignment=2,
        textColor=colors.white,
    )
    style_gran_total_val = ParagraphStyle(
        "GranTotalVal",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        alignment=2,
        textColor=colors.white,
    )

    style_nota = ParagraphStyle(
        "Nota",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#475569"),
    )

    story = []

    # 1. ENCABEZADO: Emisor a la izquierda, Factura & Estado a la derecha
    bg_estado, color_estado, texto_estado = obtener_colores_estado(factura.get("estado"))

    fecha_emision = factura.get("fecha_emision") or ""
    try:
        # Formatear fecha legible
        dt = datetime.strptime(fecha_emision, "%Y-%m-%d %H:%M:%S")
        fecha_legible = dt.strftime("%d/%m/%Y %I:%M %p")
    except Exception:
        fecha_legible = fecha_emision

    # Caja decorativa del estado
    tabla_estado = Table(
        [[Paragraph(f"<b>{texto_estado}</b>", ParagraphStyle(
            "Badge", fontName="Helvetica-Bold", fontSize=8.5, alignment=1, textColor=color_estado
        ))]],
        colWidths=[100],
        rowHeights=[18]
    )
    tabla_estado.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_estado),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))

    info_emisor = [
        Paragraph(empresa_info["nombre"], style_empresa_nombre),
        Paragraph(
            f"NIT: {empresa_info['nit']} · Régimen Común<br/>"
            f"Dirección: {empresa_info['ciudad']}<br/>"
            f"Correo: {empresa_info['email']} · Tel: {empresa_info.get('telefono', '')}",
            style_empresa_detalles,
        ),
    ]

    info_doc = [
        Paragraph("FACTURA DE VENTA", style_factura_titulo),
        Paragraph(f"N° {factura.get('numero_factura', 'N/A')}", style_factura_num),
        Paragraph(f"Fecha de emisión: {fecha_legible}", style_factura_meta),
        Spacer(1, 4),
        tabla_estado,
    ]

    header_table = Table([[info_emisor, info_doc]], colWidths=[310, 230])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceBefore=0, spaceAfter=14))

    # 2. TARJETAS DE INFORMACIÓN (CLIENTE Y DETALLES DE PAGO)
    cliente_nombre = factura.get("cliente") or "Cliente General"
    cliente_doc = factura.get("documento_cliente") or "No registrado"
    cliente_email = factura.get("email_cliente") or "No registrado"

    pago_id = factura.get("pago_id")
    metodo_pago = (pago.get("metodo_pago") if pago else None) or "Directo / En Línea"
    pago_ref = f"#{pago_id}" if pago_id else "No aplica (Venta directa)"

    tarjeta_cliente = [
        Paragraph("FACTURADO A (CLIENTE)", style_card_header),
        Spacer(1, 3),
        Paragraph(cliente_nombre, style_card_body_bold),
        Paragraph(f"<b>Identificación / NIT:</b> {cliente_doc}", style_card_body),
        Paragraph(f"<b>Correo Electrónico:</b> {cliente_email}", style_card_body),
    ]

    tarjeta_pago = [
        Paragraph("DETALLES DE LA TRANSACCIÓN", style_card_header),
        Spacer(1, 3),
        Paragraph(f"<b>Método de Pago:</b> {metodo_pago}", style_card_body),
        Paragraph(f"<b>Transacción Asociada:</b> {pago_ref}", style_card_body),
        Paragraph(f"<b>Moneda de Facturación:</b> {factura.get('moneda', 'COP')}", style_card_body),
    ]

    cards_table = Table([[tarjeta_cliente, tarjeta_pago]], colWidths=[270, 270])
    cards_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F8FAFC")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (0, 0), 1, colors.HexColor("#E2E8F0")),
        ("BOX", (1, 0), (1, 0), 1, colors.HexColor("#E2E8F0")),
        ("PADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(cards_table)

    story.append(Spacer(1, 16))

    # 3. TABLA DE CONCEPTOS / ÍTEMS
    items = factura.get("items") or []
    moneda = factura.get("moneda") or "COP"

    filas_tabla = [
        [
            Paragraph("#", style_th_center),
            Paragraph("DESCRIPCIÓN DEL CONCEPTO O SERVICIO", style_th),
            Paragraph("CANT.", style_th_center),
            Paragraph("PRECIO UNIT.", style_th_right),
            Paragraph("SUBTOTAL", style_th_right),
        ]
    ]

    for idx, item in enumerate(items, 1):
        desc = item.get("descripcion", "Artículo / Servicio")
        cant = item.get("cantidad", 1)
        pu = formatear_dinero(item.get("precio_unitario", 0), moneda)
        sub = formatear_dinero(item.get("subtotal", 0), moneda)

        filas_tabla.append([
            Paragraph(str(idx), style_td_center),
            Paragraph(desc, style_td),
            Paragraph(str(cant), style_td_center),
            Paragraph(pu, style_td_right),
            Paragraph(sub, style_td_right),
        ])

    if len(filas_tabla) == 1:
        # Si no había ítems explícitos
        filas_tabla.append([
            Paragraph("1", style_td_center),
            Paragraph("Servicio de procesamiento de pago comercial", style_td),
            Paragraph("1", style_td_center),
            Paragraph(formatear_dinero(factura.get("subtotal", 0), moneda), style_td_right),
            Paragraph(formatear_dinero(factura.get("subtotal", 0), moneda), style_td_right),
        ])

    table_items = Table(filas_tabla, colWidths=[28, 256, 46, 105, 105])
    t_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]

    for i in range(1, len(filas_tabla)):
        bg = colors.HexColor("#FFFFFF") if i % 2 != 0 else colors.HexColor("#F8FAFC")
        t_style.append(("BACKGROUND", (0, i), (-1, i), bg))

    table_items.setStyle(TableStyle(t_style))
    story.append(table_items)

    story.append(Spacer(1, 14))

    # 4. TOTALES Y BLOQUE DE NOTAS / CONVERSIÓN
    subtotal_str = formatear_dinero(factura.get("subtotal", 0), moneda)
    iva_pct = factura.get("porcentaje_impuesto", 0)
    iva_val_str = formatear_dinero(factura.get("impuesto", 0), moneda)
    total_str = formatear_dinero(factura.get("total", 0), moneda)

    # Bloque de notas informativas para el cliente
    notas_contenido = [
        Paragraph("<b>INFORMACIÓN IMPORTANTE:</b>", ParagraphStyle(
            "NotaTitle", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=colors.HexColor("#1E3A8A")
        )),
        Paragraph("• Este comprobante certifica la prestación de los servicios y conceptos detallados anteriormente.", style_nota),
        Paragraph("• Conserve este documento para efectos de control, garantía y soporte de su transacción.", style_nota),
    ]

    # Si hay conversión de moneda, mostrar nota clarísima para el cliente
    if factura.get("tasa_conversion") is not None and factura.get("moneda_origen"):
        orig = factura.get("moneda_origen")
        tasa = factura.get("tasa_conversion")
        fuente = factura.get("fuente_tasa") or "Mercado Oficial"
        fecha_t = factura.get("fecha_tasa") or ""
        notas_contenido.append(Spacer(1, 3))
        notas_contenido.append(
            Paragraph(
                f"<b>Conversión de Divisa:</b> Liquidado desde <b>{orig}</b> con tasa de cambio <b>1 {orig} = {tasa} {moneda}</b> (Fuente: {fuente} {fecha_t}).",
                ParagraphStyle("NotaDivisa", fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor("#0369A1"))
            )
        )

    # Tabla de totales
    filas_totales = [
        [Paragraph("SUBTOTAL:", style_total_label), Paragraph(subtotal_str, style_total_val)],
        [Paragraph(f"IMPUESTO IVA ({iva_pct}%):", style_total_label), Paragraph(iva_val_str, style_total_val)],
        [Paragraph("TOTAL A PAGAR:", style_gran_total_label), Paragraph(total_str, style_gran_total_val)],
    ]

    tabla_totales = Table(filas_totales, colWidths=[130, 110])
    tabla_totales.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 2), (1, 2), colors.HexColor("#1E3A8A")),
        ("TOPPADDING", (0, 2), (1, 2), 6),
        ("BOTTOMPADDING", (0, 2), (1, 2), 6),
        ("BOX", (0, 0), (-1, 1), 0.5, colors.HexColor("#E2E8F0")),
    ]))

    tabla_cierre = Table([[notas_contenido, tabla_totales]], colWidths=[300, 240])
    tabla_cierre.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    story.append(KeepTogether(tabla_cierre))

    story.append(Spacer(1, 20))

    # 5. SELLO DE SEGURIDAD DIGITAL Y PIE DE CONFIANZA
    firma_base = f"{factura.get('numero_factura')}:{factura.get('total')}:{factura.get('fecha_emision')}:{secret_key}".encode()
    hash_seguridad = hashlib.sha256(firma_base).hexdigest()

    bloque_seguridad = Table([
        [
            Paragraph(
                f"<b>Sello de Autenticidad Digital:</b> {hash_seguridad}<br/>"
                f"Emitido por el operador: <b>{factura.get('creado_por', 'sistema')}</b> · Documento verificado e inalterable.",
                ParagraphStyle("Sello", fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#64748B"))
            )
        ]
    ], colWidths=[540])
    bloque_seguridad.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(bloque_seguridad)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()

