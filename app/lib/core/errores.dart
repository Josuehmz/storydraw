import 'package:dio/dio.dart';

/// Errores que la interfaz sabe convertir en una pantalla amable.
enum TipoError {
  sinConexion,
  sesionVencida,
  correoSinVerificar,
  limite,
  datosInvalidos,
  noEncontrado,
  conflicto,
  dominioNoPermitido,
  servidor,
}

class ErrorApi implements Exception {
  const ErrorApi(this.tipo, [this.detalle]);

  final TipoError tipo;
  final String? detalle;

  factory ErrorApi.desde(Object error) {
    if (error is ErrorApi) return error;
    if (error is DioException) {
      switch (error.type) {
        case DioExceptionType.connectionError:
        case DioExceptionType.connectionTimeout:
        case DioExceptionType.sendTimeout:
        case DioExceptionType.receiveTimeout:
          return const ErrorApi(TipoError.sinConexion);
        default:
          break;
      }
      final codigo = error.response?.statusCode;
      final datos = error.response?.data;
      final detalle = datos is Map && datos['detail'] is String ? datos['detail'] as String : null;
      switch (codigo) {
        case 401:
          return ErrorApi(TipoError.sesionVencida, detalle);
        case 403:
          return ErrorApi(
            detalle == 'correo_sin_verificar'
                ? TipoError.correoSinVerificar
                : TipoError.sesionVencida,
            detalle,
          );
        case 404:
          return ErrorApi(TipoError.noEncontrado, detalle);
        case 409:
          return ErrorApi(TipoError.conflicto, detalle);
        case 413:
        case 422:
          return ErrorApi(
            detalle == 'dominio_no_permitido'
                ? TipoError.dominioNoPermitido
                : TipoError.datosInvalidos,
            detalle,
          );
        case 429:
          return ErrorApi(TipoError.limite, detalle);
      }
      return ErrorApi(TipoError.servidor, detalle);
    }
    return ErrorApi(TipoError.servidor, error.toString());
  }

  @override
  String toString() => 'ErrorApi($tipo, $detalle)';
}
