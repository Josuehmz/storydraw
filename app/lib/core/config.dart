import 'package:flutter/foundation.dart';

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
    this.intervaloConsulta = const Duration(seconds: 2),
    this.esperaMaxima = const Duration(minutes: 3),
    this.reintentosHttp = 2,
    this.modoInvitado = false,
  });

  factory AppConfig.desdeEntorno() => const AppConfig(
    apiUrl: String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000'),
    modoInvitado: bool.fromEnvironment('MODO_INVITADO'),
  );

  final String apiUrl;

  /// Botón «Entrar como invitado». SOLO PRUEBAS LOCALES: se enciende con
  /// `--dart-define=MODO_INVITADO=true` y el backend además necesita
  /// `PERMITIR_INVITADOS=true`, que en producción está prohibido.
  final bool modoInvitado;

  /// Tiempo máximo de cada petición HTTP (contrato con el backend: 90 s).
  final Duration timeout;

  /// Cada cuánto se consulta el estado del cuento durante el momento mágico.
  final Duration intervaloConsulta;

  /// Tiempo máximo de espera de un cuento antes de ofrecer reintentar.
  final Duration esperaMaxima;

  final int reintentosHttp;
}
