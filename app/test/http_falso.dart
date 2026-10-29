import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

/// Adaptador HTTP falso para las pruebas del modo invitado: responde según la
/// ruta y registra cada petición.
class HttpFalso implements HttpClientAdapter {
  HttpFalso(this.manejar);

  ResponseBody Function(RequestOptions o) manejar;
  final peticiones = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    peticiones.add(options);
    return manejar(options);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody respuestaJson(Object datos, [int codigo = 200]) => ResponseBody.fromString(
  jsonEncode(datos),
  codigo,
  headers: {
    Headers.contentTypeHeader: [Headers.jsonContentType],
  },
);
