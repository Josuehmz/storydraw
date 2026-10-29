import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:storydraw/core/config.dart';
import 'package:storydraw/core/errores.dart';
import 'package:storydraw/core/http.dart';
import 'package:storydraw/data/cache_cuentos.dart';
import 'package:storydraw/data/repositorios_api.dart';
import 'package:storydraw/data/sesion_local.dart';
import 'package:storydraw/domain/entidades.dart';

/// Adaptador HTTP falso: responde según la ruta y registra cada petición.
class AdaptadorFalso implements HttpClientAdapter {
  AdaptadorFalso(this.manejar);

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

ResponseBody json(Object datos, [int codigo = 200]) => ResponseBody.fromString(
  jsonEncode(datos),
  codigo,
  headers: {
    Headers.contentTypeHeader: [Headers.jsonContentType],
  },
);

ResponseBody bytes(List<int> datos) => ResponseBody.fromBytes(
  datos,
  200,
  headers: {
    Headers.contentTypeHeader: ['application/octet-stream'],
  },
);

Map<String, dynamic> cuentoJson(String id, String estado, {bool conAudio = true}) => {
  'id': id,
  'perfil_id': 'p1',
  'estado': estado,
  'titulo': estado == 'listo' ? 'El dragón' : null,
  'personaje': estado == 'listo' ? 'un dragón' : null,
  'avisos': <String>[],
  'creado_en': '2026-10-17T10:00:00Z',
  'paginas': estado != 'listo'
      ? <Object>[]
      : [
          for (var n = 1; n <= 3; n++)
            {
              'numero': n,
              'texto': 'Página $n',
              'imagen_url': '/v1/cuentos/$id/paginas/$n/imagen',
              'audio_url': conAudio ? '/v1/cuentos/$id/paginas/$n/audio' : null,
            },
        ],
};

const config = AppConfig(
  apiUrl: 'http://backend.prueba',
  intervaloConsulta: Duration(milliseconds: 1),
  esperaMaxima: Duration(seconds: 5),
);

void main() {
  late Directory dir;
  late CacheCuentos cache;
  late Dio dio;
  late AdaptadorFalso http;
  late CuentosRepositorioApi repo;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('storydraw_hive_');
    Hive.init(dir.path);
    cache = await CacheCuentos.abrir();
    http = AdaptadorFalso((o) => json({'detail': 'sin ruta'}, 404));
    dio = crearDio(config, token: () => 'jwt-de-prueba')..httpClientAdapter = http;
    repo = CuentosRepositorioApi(dio, cache, config);
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
    await Hive.close();
    await dir.delete(recursive: true);
  });

  test('identificar envía el dibujo en memoria con el token y lee las hipótesis', () async {
    http.manejar = (o) => json({
      'disponible': true,
      'hipotesis': [
        {'etiqueta': 'un gato', 'confianza': 0.7},
      ],
    });
    final res = await repo.identificar(Uint8List.fromList([1, 2, 3]));
    final peticion = http.peticiones.single;
    expect(peticion.path, '/v1/dibujos/identificar');
    expect(peticion.headers['Authorization'], 'Bearer jwt-de-prueba');
    expect((peticion.data as FormData).files.single.key, 'dibujo');
    expect(res.hipotesis.single.porcentaje, 70);
  });

  test('crear manda perfil y personaje; esperar consulta y guarda en caché', () async {
    var consultas = 0;
    http.manejar = (o) {
      if (o.method == 'POST' && o.path == '/v1/cuentos') {
        return json({'id': 'c9', 'estado': 'en_proceso'}, 202);
      }
      if (o.path == '/v1/cuentos/c9') {
        consultas++;
        return json(cuentoJson('c9', consultas < 3 ? 'en_proceso' : 'listo'));
      }
      if (o.path.endsWith('/imagen')) return bytes([137, 80, 78, 71]);
      if (o.path.endsWith('/audio')) return bytes([73, 68, 51]);
      return json({}, 404);
    };

    final id = await repo.crear(perfilId: 'p1', dibujo: Uint8List(4), personaje: ' un dragón ');
    final campos = Map.fromEntries((http.peticiones.first.data as FormData).fields);
    expect(campos, {'perfil_id': 'p1', 'personaje': 'un dragón'});

    final cuento = await repo.esperar(id);
    expect(consultas, 3);
    expect(cuento.estado, EstadoCuento.listo);
    expect(cuento.paginas.every((p) => p.imagen != null), isTrue);
    // Cada página baja también su narración
    expect(cuento.paginas.every((p) => p.tieneAudio), isTrue);
    expect(http.peticiones.where((o) => o.path.endsWith('/audio')), hasLength(3));

    final guardado = cache.leer('c9')!;
    expect(guardado.titulo, 'El dragón');
    expect(guardado.paginas.first.imagen, [137, 80, 78, 71]);
    // La narración queda en Hive: se relee sin conexión
    expect(guardado.paginas.first.audio, [73, 68, 51]);
  });

  test('un cuento sin narración no pide audio y se guarda igual', () async {
    http.manejar = (o) {
      if (o.path == '/v1/cuentos/c5') return json(cuentoJson('c5', 'listo', conAudio: false));
      if (o.path.endsWith('/imagen')) return bytes([1]);
      return json({}, 404);
    };
    final cuento = await repo.esperar('c5');
    expect(cuento.paginas.any((p) => p.tieneAudio), isFalse);
    expect(http.peticiones.where((o) => o.path.endsWith('/audio')), isEmpty);
    expect(cache.leer('c5')!.paginas, hasLength(3));
  });

  test('si falla bajar un audio, el cuento llega igual y esa página queda muda', () async {
    http.manejar = (o) {
      if (o.path == '/v1/cuentos/c6') return json(cuentoJson('c6', 'listo'));
      if (o.path.endsWith('/imagen')) return bytes([1]);
      if (o.path.endsWith('/paginas/2/audio')) return json({}, 500);
      if (o.path.endsWith('/audio')) return bytes([9]);
      return json({}, 404);
    };
    final cuento = await repo.esperar('c6');
    expect(cuento.estado, EstadoCuento.listo);
    expect(cuento.paginas.map((p) => p.tieneAudio), [true, false, true]);
  });

  test('un cuento rechazado no se descarga ni se guarda', () async {
    http.manejar = (o) => json(cuentoJson('c3', 'rechazado'));
    final cuento = await repo.esperar('c3');
    expect(cuento.estado, EstadoCuento.rechazado);
    expect(cache.contiene('c3'), isFalse);
  });

  test('sin conexión, la biblioteca se relee desde Hive', () async {
    http.manejar = (o) {
      if (o.path == '/v1/cuentos/c1') return json(cuentoJson('c1', 'listo'));
      return bytes([1, 2, 3]);
    };
    await repo.esperar('c1');

    http.manejar = (o) =>
        throw DioException(requestOptions: o, type: DioExceptionType.connectionError);
    final lista = await repo.biblioteca('p1');
    expect(lista.map((c) => c.id), ['c1']);
    expect(lista.single.paginas.first.imagen, isNotNull);
  });

  test('la biblioteca se sincroniza: descarga lo nuevo y olvida lo borrado', () async {
    await cache.guardar(Cuento.desdeJson(cuentoJson('viejo', 'listo')));
    http.manejar = (o) {
      if (o.path == '/v1/perfiles/p1/cuentos') {
        return json([
          {
            'id': 'nuevo',
            'titulo': 'x',
            'personaje': 'y',
            'portada_url': null,
            'creado_en': '2026-10-17T10:00:00Z',
          },
        ]);
      }
      if (o.path == '/v1/cuentos/nuevo') return json(cuentoJson('nuevo', 'listo'));
      return bytes([9]);
    };
    final lista = await repo.biblioteca('p1');
    expect(lista.map((c) => c.id), ['nuevo']);
    expect(cache.contiene('viejo'), isFalse);
  });

  test('borrar a petición llama al servidor y limpia la caché', () async {
    await cache.guardar(Cuento.desdeJson(cuentoJson('c1', 'listo')));
    http.manejar = (o) => ResponseBody.fromString('', 204);
    await repo.borrar('c1');
    expect(http.peticiones.single.method, 'DELETE');
    expect(http.peticiones.single.path, '/v1/cuentos/c1');
    expect(cache.contiene('c1'), isFalse);
  });

  group('cliente HTTP', () {
    test('reintenta un GET ante 503 y termina bien', () async {
      var llamadas = 0;
      http.manejar = (o) => ++llamadas < 3 ? json({}, 503) : json(cuentoJson('c1', 'en_proceso'));
      final r = await dio.get<Map<String, dynamic>>('/v1/cuentos/c1');
      expect(r.statusCode, 200);
      expect(llamadas, 3);
    });

    test('no reintenta un POST que llegó al servidor', () async {
      http.manejar = (o) => json({}, 500);
      await expectLater(
        repo.crear(perfilId: 'p1', dibujo: Uint8List(1)),
        throwsA(isA<ErrorApi>().having((e) => e.tipo, 'tipo', TipoError.servidor)),
      );
      expect(http.peticiones.length, 1);
    });

    test('un 429 se traduce en límite y no se reintenta', () async {
      http.manejar = (o) => json({'error': 'Rate limit exceeded'}, 429);
      await expectLater(
        repo.identificar(Uint8List(1)),
        throwsA(isA<ErrorApi>().having((e) => e.tipo, 'tipo', TipoError.limite)),
      );
      expect(http.peticiones.length, 1);
    });

    test('la URL del backend y el timeout de 90 s vienen de la configuración', () {
      final d = crearDio(AppConfig.desdeEntorno(), token: () => null);
      expect(d.options.baseUrl, 'http://10.0.2.2:8000');
      expect(d.options.receiveTimeout, const Duration(seconds: 90));
    });
  });

  test('cerrar sesión borra del teléfono los cuentos guardados y la sesión', () async {
    SharedPreferences.setMockInitialValues({});
    final sesion = SesionLocal(await SharedPreferences.getInstance());
    await sesion.guardarToken('t');
    await sesion.elegirPerfil(id: 'p1', apodo: 'Luna', edad: 7);
    final cuento = Cuento.desdeJson(cuentoJson('c1', 'listo'));
    await cache.guardar(
      cuento.conPaginas([
        for (final p in cuento.paginas) p.conMedios(imagen: Uint8List(2), audio: Uint8List(2)),
      ]),
    );
    expect(cache.contiene('c1'), isTrue);

    await CuentasRepositorioApi(dio, sesion, cache).cerrarSesion();

    expect(cache.contiene('c1'), isFalse);
    expect(cache.dePerfil('p1'), isEmpty);
    expect([sesion.token, sesion.perfilId], [null, null]);
  });

  test('la sesión guarda el token y el perfil en SharedPreferences', () async {
    SharedPreferences.setMockInitialValues({});
    final sesion = SesionLocal(await SharedPreferences.getInstance());
    await sesion.guardarToken('t');
    await sesion.elegirPerfil(id: 'p1', apodo: 'Luna', edad: 7);
    expect([sesion.token, sesion.perfilId, sesion.perfilEdad], ['t', 'p1', 7]);
    await sesion.cerrar();
    expect([sesion.token, sesion.perfilId], [null, null]);
  });
}
