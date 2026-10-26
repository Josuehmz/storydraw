import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../core/config.dart';
import '../core/errores.dart';
import '../domain/entidades.dart';
import '../domain/repositorios.dart';
import 'cache_cuentos.dart';
import 'sesion_local.dart';

/// Modo invitado: SOLO PRUEBAS LOCALES (`--dart-define=MODO_INVITADO=true` y
/// `PERMITIR_INVITADOS=true` en el backend).
///
/// Sin cuenta ni consentimiento: los perfiles y los cuentos viven solo en este
/// dispositivo (SharedPreferences y Hive). Si se borra la app, se pierden. El
/// servidor genera el cuento (con la misma moderación) y lo entrega una vez.

Future<T> _envolver<T>(Future<T> Function() f) async {
  try {
    return await f();
  } catch (e) {
    throw ErrorApi.desde(e);
  }
}

class CuentasRepositorioInvitado implements CuentasRepositorio {
  CuentasRepositorioInvitado(this._dio, this._sesion, this._cache);

  final Dio _dio;
  final SesionLocal _sesion;
  final CacheCuentos? _cache;

  /// Pide un token de invitado (corto) y lo guarda.
  Future<void> entrar() => _envolver(() async {
    final r = await _dio.post<Map<String, dynamic>>('/v1/invitado');
    await _sesion.guardarTokenInvitado(r.data!['access_token'] as String);
  });

  @override
  Future<void> registrar({
    required String email,
    required String contrasena,
    required bool aceptaConsentimiento,
  }) => throw UnsupportedError('El invitado no tiene cuenta');

  @override
  Future<void> iniciarSesion({required String email, required String contrasena}) =>
      throw UnsupportedError('El invitado no tiene cuenta');

  @override
  Future<void> cerrarSesion() => _sesion.cerrar();

  @override
  Future<List<Perfil>> perfiles() async => _sesion.perfilesInvitado;

  @override
  Future<Perfil> crearPerfil({required String apodo, required int edad}) async {
    final perfil = Perfil(
      id: 'invitado-${DateTime.now().microsecondsSinceEpoch}',
      apodo: apodo,
      edad: edad.clamp(6, 12),
    );
    await _sesion.guardarPerfilesInvitado([..._sesion.perfilesInvitado, perfil]);
    return perfil;
  }

  @override
  Future<void> borrarPerfil(String perfilId) async {
    await _sesion.guardarPerfilesInvitado([
      for (final p in _sesion.perfilesInvitado)
        if (p.id != perfilId) p,
    ]);
    await _cache?.borrarPerfil(perfilId);
    if (_sesion.perfilId == perfilId) await _sesion.olvidarPerfil();
  }
}

class CuentosRepositorioInvitado implements CuentosRepositorio {
  CuentosRepositorioInvitado(this._dio, this._cache, this._config, this._sesion, this._cuentas);

  final Dio _dio;
  final CacheCuentos _cache;
  final AppConfig _config;
  final SesionLocal _sesion;
  final CuentasRepositorioInvitado _cuentas;

  /// A qué perfil local va cada cuento pedido (el servidor no sabe de perfiles).
  final _perfilDe = <String, String>{};

  /// Si el token de invitado venció, pide otro y repite una vez.
  Future<T> _conToken<T>(Future<T> Function() f) => _envolver(() async {
    try {
      return await f();
    } on DioException catch (e) {
      if (e.response?.statusCode != 401) rethrow;
      await _cuentas.entrar();
      return f();
    }
  });

  MultipartFile _archivo(Uint8List dibujo) => MultipartFile.fromBytes(
    dibujo,
    filename: 'dibujo.png',
    contentType: DioMediaType('image', 'png'),
  );

  @override
  Future<Identificacion> identificar(Uint8List dibujo) => _conToken(() async {
    final r = await _dio.post<Map<String, dynamic>>(
      '/v1/invitado/dibujos/identificar',
      data: FormData.fromMap({'dibujo': _archivo(dibujo)}),
    );
    return Identificacion.desdeJson(r.data!);
  });

  Perfil? _perfil(String perfilId) {
    for (final p in _sesion.perfilesInvitado) {
      if (p.id == perfilId) return p;
    }
    return null;
  }

  @override
  Future<String> crear({required String perfilId, required Uint8List dibujo, String? personaje}) =>
      _conToken(() async {
        final edad = _perfil(perfilId)?.edad ?? _sesion.perfilEdad ?? 8;
        final r = await _dio.post<Map<String, dynamic>>(
          '/v1/invitado/cuentos',
          data: FormData.fromMap({
            'dibujo': _archivo(dibujo),
            'edad': '$edad',
            if (personaje != null && personaje.trim().isNotEmpty) 'personaje': personaje.trim(),
          }),
        );
        final id = r.data!['id'] as String;
        _perfilDe[id] = perfilId;
        return id;
      });

  /// Convierte la respuesta del servidor en un cuento local, con sus imágenes.
  Cuento _desdeServidor(Map<String, dynamic> j, String perfilId) {
    final id = j['id'] as String;
    return Cuento(
      id: id,
      perfilId: perfilId,
      estado: estadoDesde(j['estado'] as String),
      titulo: j['titulo'] as String?,
      personaje: j['personaje'] as String?,
      avisos: (j['avisos'] as List? ?? const []).cast<String>(),
      creadoEn: DateTime.now(),
      paginas: [
        for (final p in (j['paginas'] as List? ?? const []).cast<Map<String, dynamic>>())
          Pagina(
            numero: p['numero'] as int,
            texto: p['texto'] as String,
            imagenUrl: 'invitado:$id/${p['numero']}',
            imagen: base64Decode(p['imagen_png_base64'] as String),
          ),
      ],
    );
  }

  @override
  Future<Cuento> esperar(String cuentoId) => _conToken(() async {
    final perfilId = _perfilDe[cuentoId] ?? _sesion.perfilId ?? '';
    final limite = DateTime.now().add(_config.esperaMaxima);
    while (true) {
      final r = await _dio.get<Map<String, dynamic>>('/v1/invitado/cuentos/$cuentoId');
      final cuento = _desdeServidor(r.data!, perfilId);
      if (cuento.estado == EstadoCuento.listo) {
        // El servidor ya lo olvidó: desde aquí solo existe en este dispositivo.
        await _cache.guardar(cuento);
        _perfilDe.remove(cuentoId);
        return cuento;
      }
      if (cuento.estado != EstadoCuento.enProceso) {
        _perfilDe.remove(cuentoId);
        return cuento;
      }
      if (DateTime.now().isAfter(limite)) {
        throw TimeoutException('El cuento tarda más de lo esperado');
      }
      await Future<void>.delayed(_config.intervaloConsulta);
    }
  });

  @override
  Future<List<Cuento>> biblioteca(String perfilId) async => _cache.dePerfil(perfilId);

  @override
  Future<void> borrar(String cuentoId) => _cache.borrar(cuentoId);
}
