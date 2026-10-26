import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:storydraw/core/config.dart';
import 'package:storydraw/core/http.dart';
import 'package:storydraw/data/cache_cuentos.dart';
import 'package:storydraw/data/repositorios_invitado.dart';
import 'package:storydraw/data/sesion_local.dart';
import 'package:storydraw/domain/entidades.dart';

import '../http_falso.dart';

const config = AppConfig(
  apiUrl: 'http://backend.prueba',
  intervaloConsulta: Duration(milliseconds: 1),
  esperaMaxima: Duration(seconds: 5),
  modoInvitado: true,
);

final png = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

Map<String, dynamic> cuentoInvitado(String id, String estado) => {
  'id': id,
  'estado': estado,
  'titulo': estado == 'listo' ? 'El dragón' : null,
  'personaje': estado == 'listo' ? 'un dragón' : null,
  'avisos': <String>[],
  'paginas': estado != 'listo'
      ? <Object>[]
      : [
          for (var n = 1; n <= 3; n++)
            {'numero': n, 'texto': 'Página $n', 'imagen_png_base64': base64Encode(png)},
        ],
};

void main() {
  late Directory dir;
  late CacheCuentos cache;
  late SesionLocal sesion;
  late HttpFalso http;
  late CuentasRepositorioInvitado cuentas;
  late CuentosRepositorioInvitado cuentos;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('storydraw_invitado_');
    Hive.init(dir.path);
    cache = await CacheCuentos.abrir();
    SharedPreferences.setMockInitialValues({});
    sesion = SesionLocal(await SharedPreferences.getInstance());
    http = HttpFalso((o) => respuestaJson({'detail': 'sin ruta'}, 404));
    final dio = crearDio(config, token: () => sesion.token)..httpClientAdapter = http;
    cuentas = CuentasRepositorioInvitado(dio, sesion, cache);
    cuentos = CuentosRepositorioInvitado(dio, cache, config, sesion, cuentas);
  });

  tearDown(() async {
    await Hive.deleteFromDisk();
    await Hive.close();
    await dir.delete(recursive: true);
  });

  test('entrar pide un token de invitado y marca la sesión', () async {
    http.manejar = (o) => respuestaJson({'access_token': 'jwt-invitado', 'rol': 'invitado'}, 201);
    await cuentas.entrar();
    expect(http.peticiones.single.path, '/v1/invitado');
    expect(sesion.token, 'jwt-invitado');
    expect(sesion.invitado, isTrue);
  });

  test('los perfiles del invitado viven solo en el dispositivo', () async {
    final luna = await cuentas.crearPerfil(apodo: 'Luna', edad: 7);
    await cuentas.crearPerfil(apodo: 'Sol', edad: 10);
    expect((await cuentas.perfiles()).map((p) => p.apodo), ['Luna', 'Sol']);
    await cuentas.borrarPerfil(luna.id);
    expect((await cuentas.perfiles()).map((p) => p.apodo), ['Sol']);
    expect(http.peticiones, isEmpty);
  });

  test('crear manda la edad del perfil local; el cuento listo se guarda en Hive', () async {
    await sesion.guardarTokenInvitado('jwt-invitado');
    final perfil = await cuentas.crearPerfil(apodo: 'Luna', edad: 7);
    var consultas = 0;
    http.manejar = (o) {
      if (o.method == 'POST' && o.path == '/v1/invitado/cuentos') {
        return respuestaJson({'id': 'g1', 'estado': 'en_proceso'}, 202);
      }
      if (o.path == '/v1/invitado/cuentos/g1') {
        consultas++;
        return respuestaJson(cuentoInvitado('g1', consultas < 2 ? 'en_proceso' : 'listo'));
      }
      return respuestaJson({}, 404);
    };

    final id = await cuentos.crear(perfilId: perfil.id, dibujo: Uint8List(4), personaje: 'dragón');
    final peticion = http.peticiones.first;
    expect(peticion.headers['Authorization'], 'Bearer jwt-invitado');
    expect(Map.fromEntries((peticion.data as FormData).fields), {
      'edad': '7',
      'personaje': 'dragón',
    });

    final cuento = await cuentos.esperar(id);
    expect(cuento.estado, EstadoCuento.listo);
    expect(cuento.perfilId, perfil.id);
    expect(cuento.paginas.map((p) => p.imagen), everyElement(png));

    // Desde aquí el cuento existe solo en el dispositivo: la biblioteca y el
    // borrado no tocan la red.
    http.peticiones.clear();
    final lista = await cuentos.biblioteca(perfil.id);
    expect(lista.single.titulo, 'El dragón');
    expect(lista.single.paginas.first.imagen, png);
    await cuentos.borrar('g1');
    expect(await cuentos.biblioteca(perfil.id), isEmpty);
    expect(http.peticiones, isEmpty);
  });

  test('un cuento rechazado no se guarda', () async {
    http.manejar = (o) => respuestaJson(cuentoInvitado('g2', 'rechazado'));
    final cuento = await cuentos.esperar('g2');
    expect(cuento.estado, EstadoCuento.rechazado);
    expect(cache.contiene('g2'), isFalse);
  });

  test('si el token de invitado venció, pide otro y repite', () async {
    await sesion.guardarTokenInvitado('jwt-viejo');
    http.manejar = (o) {
      if (o.path == '/v1/invitado') {
        return respuestaJson({'access_token': 'jwt-nuevo', 'rol': 'invitado'}, 201);
      }
      if (o.headers['Authorization'] == 'Bearer jwt-viejo') {
        return respuestaJson({'detail': 'no_autenticado'}, 401);
      }
      return respuestaJson({'disponible': false, 'hipotesis': <Object>[]});
    };
    final res = await cuentos.identificar(Uint8List(4));
    expect(res.disponible, isFalse);
    expect(http.peticiones.map((o) => o.path), [
      '/v1/invitado/dibujos/identificar',
      '/v1/invitado',
      '/v1/invitado/dibujos/identificar',
    ]);
    expect(sesion.token, 'jwt-nuevo');
  });
}
