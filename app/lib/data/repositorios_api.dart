import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../core/config.dart';
import '../core/errores.dart';
import '../domain/entidades.dart';
import '../domain/repositorios.dart';
import 'cache_cuentos.dart';
import 'sesion_local.dart';

class CuentasRepositorioApi implements CuentasRepositorio {
  CuentasRepositorioApi(this._dio, this._sesion, this._cache);

  final Dio _dio;
  final SesionLocal _sesion;
  final CacheCuentos? _cache;

  Future<T> _envolver<T>(Future<T> Function() f) async {
    try {
      return await f();
    } catch (e) {
      throw ErrorApi.desde(e);
    }
  }

  @override
  Future<void> registrar({
    required String email,
    required String contrasena,
    required bool aceptaConsentimiento,
  }) => _envolver(
    () => _dio.post<dynamic>(
      '/v1/auth/registro',
      data: {
        'email': email,
        'contrasena': contrasena,
        'acepta_consentimiento': aceptaConsentimiento,
      },
    ),
  );

  @override
  Future<void> iniciarSesion({required String email, required String contrasena}) =>
      _envolver(() async {
        final r = await _dio.post<Map<String, dynamic>>(
          '/v1/auth/login',
          data: {'email': email, 'contrasena': contrasena},
        );
        await _sesion.guardarToken(r.data!['access_token'] as String);
      });

  @override
  Future<void> cerrarSesion() => _sesion.cerrar();

  @override
  Future<List<Perfil>> perfiles() => _envolver(() async {
    final r = await _dio.get<List<dynamic>>('/v1/perfiles');
    return [for (final p in r.data!.cast<Map<String, dynamic>>()) Perfil.desdeJson(p)];
  });

  @override
  Future<Perfil> crearPerfil({required String apodo, required int edad}) => _envolver(() async {
    final r = await _dio.post<Map<String, dynamic>>(
      '/v1/perfiles',
      data: {'apodo': apodo, 'edad': edad},
    );
    return Perfil.desdeJson(r.data!);
  });

  @override
  Future<void> borrarPerfil(String perfilId) => _envolver(() async {
    await _dio.delete<void>('/v1/perfiles/$perfilId');
    await _cache?.borrarPerfil(perfilId);
    if (_sesion.perfilId == perfilId) await _sesion.olvidarPerfil();
  });
}

class CuentosRepositorioApi implements CuentosRepositorio {
  CuentosRepositorioApi(this._dio, this._cache, this._config);

  final Dio _dio;
  final CacheCuentos _cache;
  final AppConfig _config;

  Future<T> _envolver<T>(Future<T> Function() f) async {
    try {
      return await f();
    } catch (e) {
      throw ErrorApi.desde(e);
    }
  }

  MultipartFile _archivo(Uint8List dibujo) => MultipartFile.fromBytes(
    dibujo,
    filename: 'dibujo.png',
    contentType: DioMediaType('image', 'png'),
  );

  @override
  Future<Identificacion> identificar(Uint8List dibujo) => _envolver(() async {
    final r = await _dio.post<Map<String, dynamic>>(
      '/v1/dibujos/identificar',
      data: FormData.fromMap({'dibujo': _archivo(dibujo)}),
    );
    return Identificacion.desdeJson(r.data!);
  });

  @override
  Future<String> crear({
    required String perfilId,
    required Uint8List dibujo,
    String? personaje,
    String? nombre,
  }) => _envolver(() async {
    final r = await _dio.post<Map<String, dynamic>>(
      '/v1/cuentos',
      data: FormData.fromMap({
        'dibujo': _archivo(dibujo),
        'perfil_id': perfilId,
        if (personaje != null && personaje.trim().isNotEmpty) 'personaje': personaje.trim(),
        if (nombre != null && nombre.trim().isNotEmpty) 'nombre': nombre.trim(),
      }),
    );
    return r.data!['id'] as String;
  });

  Future<Cuento> _consultar(String id) async {
    final r = await _dio.get<Map<String, dynamic>>('/v1/cuentos/$id');
    return Cuento.desdeJson(r.data!);
  }

  Future<Uint8List> _bytes(String ruta) async {
    final r = await _dio.get<List<int>>(ruta, options: Options(responseType: ResponseType.bytes));
    return Uint8List.fromList(r.data!);
  }

  /// Descarga las imágenes y la narración de las páginas y guarda el cuento en la caché.
  /// Si la narración de una página no se puede bajar, el cuento se entrega igual: solo esa
  /// página queda sin botón de escuchar.
  Future<Cuento> _descargar(Cuento cuento) async {
    final paginas = <Pagina>[];
    for (final p in cuento.paginas) {
      Uint8List? audio;
      if (p.audioUrl != null) {
        try {
          audio = await _bytes(p.audioUrl!);
        } on DioException {
          audio = null;
        }
      }
      paginas.add(p.conMedios(imagen: await _bytes(p.imagenUrl), audio: audio));
    }
    final completo = cuento.conPaginas(paginas);
    await _cache.guardar(completo);
    return completo;
  }

  @override
  Future<Cuento> esperar(String cuentoId) => _envolver(() async {
    final limite = DateTime.now().add(_config.esperaMaxima);
    while (true) {
      final cuento = await _consultar(cuentoId);
      if (cuento.estado == EstadoCuento.listo) return _descargar(cuento);
      if (cuento.estado != EstadoCuento.enProceso) return cuento;
      if (DateTime.now().isAfter(limite)) {
        throw TimeoutException('El cuento tarda más de lo esperado');
      }
      await Future<void>.delayed(_config.intervaloConsulta);
    }
  });

  @override
  Future<List<Cuento>> biblioteca(String perfilId) async {
    try {
      final r = await _dio.get<List<dynamic>>('/v1/perfiles/$perfilId/cuentos');
      final remotos = [for (final c in r.data!.cast<Map<String, dynamic>>()) c['id'] as String];
      // Lo borrado desde otro dispositivo también desaparece de la caché.
      for (final local in _cache.dePerfil(perfilId)) {
        if (!remotos.contains(local.id)) await _cache.borrar(local.id);
      }
      for (final id in remotos) {
        if (!_cache.contiene(id)) await _descargar(await _consultar(id));
      }
    } on DioException catch (e) {
      final error = ErrorApi.desde(e);
      // Sin conexión se relee lo que hay en la caché; lo demás sí se reporta.
      if (error.tipo != TipoError.sinConexion) throw error;
    }
    return _cache.dePerfil(perfilId);
  }

  @override
  Future<void> borrar(String cuentoId) => _envolver(() async {
    try {
      await _dio.delete<void>('/v1/cuentos/$cuentoId');
    } on DioException catch (e) {
      if (e.response?.statusCode != 404) rethrow;
    }
    await _cache.borrar(cuentoId);
  });
}
