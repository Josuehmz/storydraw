import 'package:flutter/foundation.dart';

import 'correo.dart';

/// Configuración inyectada en la compilación.
///
/// La URL del backend nunca se escribe en el código: llega con
/// `--dart-define=API_URL=https://...`. Por defecto apunta al backend local
/// visto desde el emulador de Android (10.0.2.2 es el host).
@immutable
class AppConfig {
  const AppConfig({
    required this.apiUrl,
    this.timeout = const Duration(seconds: 90),
    this.intervaloConsulta = const Duration(seconds: 3),
    this.esperaMaxima = const Duration(minutes: 4),
    this.avisoDemora = const Duration(seconds: 60),
    this.reintentosHttp = 2,
    this.modoInvitado = false,
    this.dominiosCorreo = const [],
  });

  factory AppConfig.desdeEntorno() => AppConfig(
    apiUrl: String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000'),
    modoInvitado: bool.fromEnvironment('MODO_INVITADO'),
    dominiosCorreo: dominiosDesde(const String.fromEnvironment('DOMINIOS_CORREO')),
  );

  final String apiUrl;

  /// Botón «Entrar como invitado». SOLO PRUEBAS LOCALES: se enciende con
  /// `--dart-define=MODO_INVITADO=true` y el backend además necesita
  /// `PERMITIR_INVITADOS=true`, que en producción está prohibido.
  final bool modoInvitado;

  /// Dominios que pueden crear cuenta (vacío = cualquiera). Debe ser la misma lista que
  /// `DOMINIOS_CORREO` del backend: la app solo avisa antes; el servidor es quien manda.
  final List<String> dominiosCorreo;

  /// Tiempo máximo de cada petición HTTP (contrato con el backend: 90 s).
  final Duration timeout;

  /// Cada cuánto se consulta el estado del cuento durante el momento mágico.
  final Duration intervaloConsulta;

  /// Tiempo máximo de espera de un cuento antes de ofrecer reintentar. Es mayor que el
  /// tope del cuento en el backend (180 s), para que el servidor falle limpio primero.
  final Duration esperaMaxima;

  /// Desde cuándo el momento mágico avisa que está tardando más de lo normal.
  final Duration avisoDemora;

  final int reintentosHttp;
}
