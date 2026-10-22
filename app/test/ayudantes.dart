import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/data/sesion_local.dart';
import 'package:storydraw/domain/entidades.dart';
import 'package:storydraw/domain/repositorios.dart';

/// PNG de 1×1 válido, para Image.memory en las pruebas.
final pngMinimo = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

Cuento cuentoDePrueba({String id = 'c1', List<String> avisos = const [], bool conAudio = true}) =>
    Cuento(
      id: id,
      perfilId: 'p1',
      estado: EstadoCuento.listo,
      titulo: 'La aventura de un dragón $id',
      personaje: 'un dragón',
      avisos: avisos,
      creadoEn: DateTime(2026, 10, 17),
      paginas: [
        for (var n = 1; n <= 3; n++)
          Pagina(
            numero: n,
            texto: 'Texto de la página $n',
            imagenUrl: '/v1/cuentos/$id/paginas/$n/imagen',
            audioUrl: conAudio ? '/v1/cuentos/$id/paginas/$n/audio' : null,
            imagen: pngMinimo,
            audio: conAudio ? Uint8List.fromList([73, 68, 51, n]) : null,
          ),
      ],
    );

class ReproductorFalso implements Reproductor {
  final reproducidos = <Uint8List>[];
  final _estado = StreamController<bool>.broadcast();

  @override
  Stream<bool> get reproduciendo => _estado.stream;

  @override
  Future<void> reproducir(Uint8List mp3) async => reproducidos.add(mp3);

  @override
  Future<void> detener() async {}

  @override
  Future<void> liberar() => _estado.close();
}

class CuentosRepositorioFalso implements CuentosRepositorio {
  CuentosRepositorioFalso({List<Cuento>? cuentos}) : cuentos = cuentos ?? [];

  final List<Cuento> cuentos;
  final borrados = <String>[];
  Identificacion identificacion = const Identificacion(
    disponible: true,
    hipotesis: [Hipotesis('un dragón', 0.81), Hipotesis('un dinosaurio', 0.44)],
  );

  @override
  Future<Identificacion> identificar(Uint8List dibujo) async => identificacion;

  @override
  Future<String> crear({
    required String perfilId,
    required Uint8List dibujo,
    String? personaje,
  }) async => 'c1';

  @override
  Future<Cuento> esperar(String cuentoId) async => cuentoDePrueba(id: cuentoId);

  @override
  Future<Cuento> reintentarNarracion(String cuentoId) async => cuentoDePrueba(id: cuentoId);

  @override
  Future<List<Cuento>> biblioteca(String perfilId) async => List.of(cuentos);

  @override
  Future<void> borrar(String cuentoId) async {
    borrados.add(cuentoId);
    cuentos.removeWhere((c) => c.id == cuentoId);
  }
}

/// Pantalla de teléfono de gama media (360 × 780 dp).
void usarTelefono(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
}

/// Monta un widget con ProviderScope, sesión simulada y repositorios falsos.
Future<Widget> montar(
  Widget hijo, {
  List<Override> overrides = const [],
  Reproductor? reproductor,
  Map<String, Object> preferencias = const {
    'sesion.token': 'jwt-de-prueba',
    'sesion.perfil_id': 'p1',
    'sesion.perfil_apodo': 'Luna',
    'sesion.perfil_edad': 8,
  },
}) async {
  SharedPreferences.setMockInitialValues(preferencias);
  final prefs = await SharedPreferences.getInstance();
  return ProviderScope(
    retry: (_, _) => null,
    overrides: [
      sesionLocalProvider.overrideWithValue(SesionLocal(prefs)),
      reproductorProvider.overrideWithValue(reproductor ?? ReproductorFalso()),
      ...overrides,
    ],
    child: MaterialApp(home: hijo),
  );
}
