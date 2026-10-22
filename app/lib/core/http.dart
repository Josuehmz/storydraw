import 'dart:async';

import 'package:dio/dio.dart';

import 'config.dart';

/// Crea el cliente HTTP: URL inyectable, timeout de 90 s, token JWT y reintentos.
Dio crearDio(AppConfig config, {required String? Function() token}) {
  final dio = Dio(
    BaseOptions(
      baseUrl: config.apiUrl,
      connectTimeout: config.timeout,
      sendTimeout: config.timeout,
      receiveTimeout: config.timeout,
    ),
  );
  dio.interceptors.add(InterceptorToken(token));
  dio.interceptors.add(InterceptorReintentos(dio, maximo: config.reintentosHttp));
  return dio;
}

class InterceptorToken extends Interceptor {
  InterceptorToken(this._token);

  final String? Function() _token;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final token = _token();
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }
}

/// Reintenta solo lo que es seguro repetir.
///
/// - GET y DELETE: ante caída de red, timeouts o 502/503/504.
/// - POST: solo si la petición ni siquiera salió (error de conexión), para no
///   crear dos cuentos con el mismo dibujo.
/// - Nunca ante 4xx: un 429 o un 422 no se arreglan insistiendo.
class InterceptorReintentos extends Interceptor {
  InterceptorReintentos(
    this._dio, {
    this.maximo = 2,
    this.esperaBase = const Duration(milliseconds: 400),
  });

  final Dio _dio;
  final int maximo;
  final Duration esperaBase;

  static const _clave = 'reintento';

  bool _debeReintentar(DioException e) {
    final metodo = e.requestOptions.method.toUpperCase();
    final idempotente = metodo == 'GET' || metodo == 'DELETE' || metodo == 'HEAD';
    if (e.type == DioExceptionType.connectionError) return true;
    if (!idempotente) return false;
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout ||
        e.type == DioExceptionType.sendTimeout) {
      return true;
    }
    final codigo = e.response?.statusCode;
    return codigo == 502 || codigo == 503 || codigo == 504;
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final intento = (err.requestOptions.extra[_clave] as int?) ?? 0;
    if (intento >= maximo || !_debeReintentar(err)) {
      handler.next(err);
      return;
    }
    await Future<void>.delayed(esperaBase * (1 << intento));
    final opciones = err.requestOptions;
    opciones.extra[_clave] = intento + 1;
    final datos = opciones.data;
    if (datos is FormData) opciones.data = datos.clone();
    try {
      handler.resolve(await _dio.fetch<dynamic>(opciones));
    } on DioException catch (e) {
      handler.next(e);
    }
  }
}
