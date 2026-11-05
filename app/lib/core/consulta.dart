import 'dart:async';
import 'dart:math';

/// Consulta el estado de un cuento cada [intervalo] hasta que deje de estar en proceso.
///
/// Lo usan el repositorio con cuenta y el de invitado. Hace como mucho
/// `esperaMaxima / intervalo` esperas (y nunca espera más de [esperaMaxima] de reloj);
/// después lanza [TimeoutException] y la pantalla ofrece reintentar con un mensaje amable.
Future<T> consultarCadaIntervalo<T>({
  required Future<T> Function() consultar,
  required bool Function(T) enProceso,
  required Duration intervalo,
  required Duration esperaMaxima,
}) async {
  final esperas = max(1, esperaMaxima.inMicroseconds ~/ max(1, intervalo.inMicroseconds));
  final reloj = Stopwatch()..start();
  for (var i = 0; ; i++) {
    final resultado = await consultar();
    if (!enProceso(resultado)) return resultado;
    if (i >= esperas || reloj.elapsed >= esperaMaxima) {
      throw TimeoutException('El cuento tarda más de lo esperado', esperaMaxima);
    }
    await Future<void>.delayed(intervalo);
  }
}
