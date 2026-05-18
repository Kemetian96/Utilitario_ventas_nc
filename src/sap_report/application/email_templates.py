_FIRMA_TEXTO = """Saludos

Eduardo Sencia
Analista Help Desk Senior | Platanitos

M: (+51) 967661024
A: Av. Vulcano 120, Ate
E: esencia@platanitos.com
W: www.platanitos.com"""


_FIRMA_HTML = """\
<table cellpadding="0" cellspacing="0" border="0" role="presentation"
       style="font-family:Arial,Helvetica,sans-serif;border-collapse:collapse;">
  <tr><td style="padding-top:20px;">
    <div style="font-size:11px;color:#9aa0a6;letter-spacing:.04em;
                text-transform:uppercase;margin-bottom:12px;">Saludos</div>
    <div style="font-size:17px;font-weight:700;color:#202124;">Eduardo Sencia</div>
    <div style="font-size:13px;color:#5f6368;padding:3px 0 12px;">
      Analista Help Desk Senior&nbsp;&middot;&nbsp;Platanitos
    </div>
    <div style="border-top:2px solid #e8a13a;width:48px;margin:0 0 14px;"></div>
    <table cellpadding="0" cellspacing="0" border="0" role="presentation"
           style="font-size:13px;color:#3c4043;border-collapse:collapse;">
      <tr>
        <td style="padding:3px 10px 3px 0;color:#9aa0a6;font-weight:600;
                   width:18px;vertical-align:top;">M</td>
        <td style="padding:3px 0;">(+51) 967661024</td>
      </tr>
      <tr>
        <td style="padding:3px 10px 3px 0;color:#9aa0a6;font-weight:600;
                   vertical-align:top;">A</td>
        <td style="padding:3px 0;">Av. Vulcano 120, Ate</td>
      </tr>
      <tr>
        <td style="padding:3px 10px 3px 0;color:#9aa0a6;font-weight:600;
                   vertical-align:top;">E</td>
        <td style="padding:3px 0;">
          <a href="mailto:esencia@platanitos.com"
             style="color:#1a73e8;text-decoration:none;">esencia@platanitos.com</a>
        </td>
      </tr>
      <tr>
        <td style="padding:3px 10px 3px 0;color:#9aa0a6;font-weight:600;
                   vertical-align:top;">W</td>
        <td style="padding:3px 0;">
          <a href="https://www.platanitos.com"
             style="color:#1a73e8;text-decoration:none;">www.platanitos.com</a>
        </td>
      </tr>
    </table>
  </td></tr>
</table>"""


EMAIL_TEMPLATES = [
    {
        "id": "cierre_cajas",
        "nombre": "Cierre de Cajas (Tutati)",
        "to": ["cierre.z@platanitos.com"],
        "cc": [],
        "asunto": "Cierre de Cajas (Tutati) {fecha}",
        "mensaje": "Se realizó la validación que todas las cajas fueron cerradas el {fecha} en TUTATI",
    },
    {
        "id": "carga_venta_sap",
        "nombre": "Carga de Venta (SAP)",
        "to": ["carga.ventas@platanitos.com"],
        "cc": [],
        "asunto": "Carga de Venta (SAP) {fecha}",
        "mensaje": "Se realizó la carga de las ventas hasta el día {fecha} en SAP",
    },
    {
        "id": "carga_venta_nubefact",
        "nombre": "Carga de Venta (Nubefact)",
        "to": ["carga.ventas@platanitos.com"],
        "cc": [],
        "asunto": "Carga de Venta (Nubefact) {fecha}",
        "mensaje": "Se realizó la carga de las ventas hasta el día {fecha} en Nubefact",
    },
]

_TEMPLATES_BY_ID = {t["id"]: t for t in EMAIL_TEMPLATES}


def _cuerpo_texto(mensaje: str) -> str:
    return f"Buen día\n\n{mensaje}\n\n{_FIRMA_TEXTO}"


def _cuerpo_html(mensaje: str) -> str:
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#3c4043;'
        'font-size:14px;line-height:1.65;">'
        '<p style="margin:0 0 14px;">Buen día</p>'
        f'<p style="margin:0 0 4px;">{mensaje}</p>'
        f"{_FIRMA_HTML}"
        "</div>"
    )


def construir_correo(template_id: str, fecha_str: str) -> dict:
    plantilla = _TEMPLATES_BY_ID.get(template_id)
    if plantilla is None:
        raise ValueError(f"Plantilla de correo desconocida: {template_id!r}")
    mensaje = plantilla["mensaje"].replace("{fecha}", fecha_str)
    return {
        "to": list(plantilla["to"]),
        "cc": list(plantilla["cc"]),
        "asunto": plantilla["asunto"].replace("{fecha}", fecha_str),
        "cuerpo": _cuerpo_texto(mensaje),
        "cuerpo_html": _cuerpo_html(mensaje),
    }
