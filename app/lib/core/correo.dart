/// Reglas del correo de la cuenta del adulto.
///
/// Los dominios que pueden crear cuenta los decide el servidor (`DOMINIOS_CORREO`, vacío =
/// cualquiera). La app repite la regla, con la misma lista inyectada en la compilación
/// (`--dart-define=DOMINIOS_CORREO=gmail.com,hotmail.com`), para avisar antes de enviar nada.
List<String> dominiosDesde(String valor) => [
  for (final d in valor.split(','))
    if (d.trim().isNotEmpty) d.trim().toLowerCase().replaceFirst(RegExp('^@'), ''),
];

/// Esquema con el que el backend vuelve a abrir la app al confirmar el correo:
/// `storydraw://verificado?email=...`. Debe coincidir con el `intent-filter` del manifest.
const esquemaApp = 'storydraw';
const hostCorreoConfirmado = 'verificado';

/// ¿El dominio del correo está permitido? Sin lista, cualquiera lo está (el formato lo revisa
/// el servidor). Con lista, el dominio completo debe coincidir, sin subdominios.
bool esCorreoPermitido(String correo, List<String> permitidos) {
  if (permitidos.isEmpty) return true;
  final limpio = correo.trim().toLowerCase();
  final arroba = limpio.lastIndexOf('@');
  if (arroba <= 0) return false;
  return permitidos.contains(limpio.substring(arroba + 1));
}

/// «gmail.com, hotmail.com» → «Gmail y Hotmail»: los nombres que ve el adulto.
String nombresDominios(List<String> dominios) {
  final nombres = [
    for (final d in dominios) d.split('.').first.replaceRange(0, 1, d[0].toUpperCase()),
  ];
  if (nombres.length <= 1) return nombres.join();
  return '${nombres.sublist(0, nombres.length - 1).join(', ')} y ${nombres.last}';
}

/// Si el enlace abierto es el de «correo confirmado», devuelve el correo que trae
/// (puede ser vacío); si es cualquier otro enlace, devuelve null.
String? correoConfirmadoDe(Uri enlace) {
  if (enlace.scheme != esquemaApp || enlace.host != hostCorreoConfirmado) return null;
  return enlace.queryParameters['email'] ?? '';
}
