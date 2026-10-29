import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:storydraw/application/flujo_cuento.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/data/sesion_local.dart';
import 'package:storydraw/domain/entidades.dart';
import 'package:storydraw/domain/repositorios.dart';

/// PNG de 1×1 válido, para Image.memory en las pruebas.
final pngMinimo = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

Cuento cuentoDePrueba({String id = 'c1', List<String> avisos = const []}) => Cuento(
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
        imagen: pngMinimo,
      ),
  ],
);

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
    String? nombre,
  }) async => 'c1';

  @override
  Future<Cuento> esperar(String cuentoId) async => cuentoDePrueba(id: cuentoId);

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
    overrides: [sesionLocalProvider.overrideWithValue(SesionLocal(prefs)), ...overrides],
    child: MaterialApp(home: hijo),
  );
}

/// Flujo con un estado fijo que anota lo que se le pide crear, sin tocar la red.
class FlujoFijo extends FlujoCuentoNotifier {
  FlujoFijo(this.inicial);

  final EstadoFlujo inicial;
  final creados = <String>[];
  final nombres = <String?>[];

  @override
  EstadoFlujo build() => inicial;

  @override
  Future<void> crear(String personaje, {String? nombre}) async {
    creados.add(personaje);
    nombres.add(nombre);
  }
}
