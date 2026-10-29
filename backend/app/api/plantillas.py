"""Textos y páginas de la verificación de correo.

Son HTML simple con estilos en línea (los clientes de correo ignoran las hojas de estilo) y
los mismos colores de la app. Todo valor que viene de fuera se escapa antes de ir al HTML.
"""

from __future__ import annotations

from html import escape
from urllib.parse import quote

NARANJA = "#FF6B35"
VIOLETA = "#7C5CBF"
CREMA = "#FFF8F0"
TEXTO = "#2D2D2D"


def enlace_app(esquema: str, email: str) -> str:
    """Abre la app (esquema propio) y le pasa el correo confirmado para prellenar el login."""
    return f"{esquema}://verificado?email={quote(email, safe='')}"


def enlace_app_android(esquema: str, paquete: str, email: str) -> str:
    """Forma `intent://` que Chrome para Android acepta de forma más fiable que el esquema."""
    return (
        f"intent://verificado?email={quote(email, safe='')}"
        f"#Intent;scheme={esquema};package={paquete};end"
    )


def correo_verificacion(enlace: str) -> tuple[str, str, str]:
    """Devuelve (asunto, texto plano, html) del correo de confirmación."""
    asunto = "Confirma tu correo en StoryDraw"
    texto = (
        "¡Hola!\n\n"
        "Para activar tu cuenta de StoryDraw y crear el perfil de tu hijo o hija, confirma tu "
        f"correo en este enlace:\n\n{enlace}\n\n"
        "Al confirmar volverás a la app y ya podrás iniciar sesión.\n"
        "Si no creaste esta cuenta, ignora este mensaje."
    )
    url = escape(enlace, quote=True)
    html = f"""<!doctype html>
<html lang="es"><body style="margin:0;padding:0;background:{CREMA};">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{CREMA};">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
  style="max-width:480px;background:#ffffff;border-radius:24px;overflow:hidden;
  font-family:Arial,Helvetica,sans-serif;color:{TEXTO};">
<tr><td align="center" style="background:{NARANJA};padding:28px 16px;">
  <div style="font-size:30px;font-weight:bold;color:#ffffff;">StoryDraw</div>
  <div style="font-size:14px;color:#ffffff;opacity:.9;margin-top:4px;">
    El dibujo de tu peque, hecho cuento</div>
</td></tr>
<tr><td style="padding:28px 24px 8px 24px;">
  <h1 style="margin:0 0 12px 0;font-size:22px;">¡Hola! Confirma tu correo</h1>
  <p style="margin:0 0 20px 0;font-size:16px;line-height:1.5;">
    Para activar tu cuenta y crear el perfil de tu hijo o hija, toca el botón.
    Volverás a la app y ya podrás iniciar sesión.</p>
</td></tr>
<tr><td align="center" style="padding:0 24px 24px 24px;">
  <a href="{url}" style="display:inline-block;background:{NARANJA};color:#ffffff;
    text-decoration:none;font-weight:bold;font-size:18px;padding:16px 32px;
    border-radius:16px;">Confirmar mi correo</a>
</td></tr>
<tr><td style="padding:0 24px 24px 24px;font-size:13px;line-height:1.5;color:#666666;">
  Si el botón no funciona, copia este enlace en tu navegador:<br>
  <span style="word-break:break-all;color:{VIOLETA};">{url}</span><br><br>
  Si no creaste esta cuenta, ignora este mensaje.
</td></tr>
</table></td></tr></table></body></html>"""
    return asunto, texto, html


def _pagina(titulo: str, icono: str, color: str, cuerpo: str, extra: str = "") -> str:
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StoryDraw</title></head>
<body style="margin:0;background:{CREMA};font-family:Arial,Helvetica,sans-serif;color:{TEXTO};">
<div style="max-width:440px;margin:0 auto;padding:40px 20px;text-align:center;">
  <div style="font-size:26px;font-weight:bold;color:{NARANJA};margin-bottom:24px;">StoryDraw</div>
  <div style="background:#ffffff;border-radius:28px;padding:32px 24px;
    box-shadow:0 6px 18px rgba(0,0,0,.08);">
    <div style="width:84px;height:84px;line-height:84px;border-radius:50%;margin:0 auto 16px;
      background:{color};color:#ffffff;font-size:46px;font-weight:bold;">{icono}</div>
    <h1 style="font-size:26px;margin:0 0 12px 0;">{titulo}</h1>
    {cuerpo}
  </div>
</div>
{extra}
</body></html>"""


def pagina_confirmada(email: str, enlace_esquema: str, enlace_intent: str) -> str:
    """Correo confirmado: intenta abrir la app sola y deja un botón grande por si no puede."""
    esquema = escape(enlace_esquema, quote=True)
    intent = escape(enlace_intent, quote=True)
    cuerpo = f"""
    <p style="font-size:16px;line-height:1.5;margin:0 0 24px 0;">
      Tu correo <b>{escape(email)}</b> quedó confirmado. Ya puedes iniciar sesión cuando
      quieras.</p>
    <a id="abrir" href="{intent}" style="display:block;background:{NARANJA};color:#ffffff;
      text-decoration:none;font-weight:bold;font-size:20px;padding:18px 24px;
      border-radius:18px;">Abrir StoryDraw</a>
    <p style="font-size:13px;color:#666666;line-height:1.5;margin:20px 0 0 0;">
      Si la app no se abre sola, toca el botón. Si estás en un computador, abre StoryDraw en
      tu teléfono e inicia sesión.</p>"""
    # El navegador a veces bloquea abrir una app sin un toque; por eso también está el botón.
    extra = f"""<script>
(function () {{
  var esAndroid = /android/i.test(navigator.userAgent);
  if (!esAndroid) {{ return; }}
  setTimeout(function () {{ window.location.href = "{esquema}"; }}, 500);
}})();
</script>"""
    return _pagina("¡Correo confirmado!", "✓", "#2E9E4F", cuerpo, extra)


def pagina_error() -> str:
    cuerpo = """
    <p style="font-size:16px;line-height:1.5;margin:0;">
      Este enlace venció o no es válido. Abre StoryDraw, intenta iniciar sesión y toca
      <b>Reenviar correo</b> para recibir uno nuevo.</p>"""
    return _pagina("No pudimos confirmar", "!", "#D64545", cuerpo)
