/// Reglas del correo de la cuenta del adulto.
///
/// Solo se crean cuentas con estos dominios. El servidor es quien manda (`DOMINIOS_CORREO`);
/// la app repite la regla para avisar antes de enviar nada.
const dominiosPermitidos = ['gmail.com', 'hotmail.com'];

/// Esquema con el que el backend vuelve a abrir la app al confirmar el correo:
/// `storydraw://verificado?email=...`. Debe coincidir con el `intent-filter` del manifest.
const esquemaApp = 'storydraw';
const hostCorreoConfirmado = 'verificado';

/// ¿El correo es de Gmail u Hotmail? (el dominio completo debe coincidir, sin subdominios)
bool esCorreoPermitido(String correo) {
  final limpio = correo.trim().toLowerCase();
  final arroba = limpio.lastIndexOf('@');
  if (arroba <= 0) return false;
  return dominiosPermitidos.contains(limpio.substring(arroba + 1));
}

/// Si el enlace abierto es el de «correo confirmado», devuelve el correo que trae
/// (puede ser vacío); si es cualquier otro enlace, devuelve null.
String? correoConfirmadoDe(Uri enlace) {
  if (enlace.scheme != esquemaApp || enlace.host != hostCorreoConfirmado) return null;
  return enlace.queryParameters['email'] ?? '';
}
