import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:storydraw/application/flujo_cuento.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/core/errores.dart';
import 'package:storydraw/data/sesion_local.dart';
import 'package:storydraw/domain/entidades.dart';

import '../ayudantes.dart';

class RepoQueFalla extends CuentosRepositorioFalso {
  @override
  Future<Identificacion> identificar(Uint8List dibujo) async =>
      throw const ErrorApi(TipoError.servidor);

  @override
  Future<Cuento> esperar(String cuentoId) async => Cuento(
    id: cuentoId,
    perfilId: 'p1',
    estado: EstadoCuento.rechazado,
    creadoEn: DateTime(2026),
  );
}

Future<ProviderContainer> contenedor(CuentosRepositorioFalso repo) async {
  SharedPreferences.setMockInitialValues({
    'sesion.token': 't',
    'sesion.perfil_id': 'p1',
    'sesion.perfil_apodo': 'Luna',
    'sesion.perfil_edad': 8,
  });
  final prefs = await SharedPreferences.getInstance();
  final c = ProviderContainer(
    retry: (_, _) => null,
    overrides: [
      sesionLocalProvider.overrideWithValue(SesionLocal(prefs)),
      cuentosRepositorioProvider.overrideWithValue(repo),
    ],
  );
  addTearDown(c.dispose);
  return c;
}

void main() {
  final dibujo = Uint8List.fromList([1, 2, 3]);

  test('dibujo → identificar → elegir → cuento listo; reiniciar suelta el dibujo', () async {
    final c = await contenedor(CuentosRepositorioFalso());
    final flujo = c.read(flujoProvider.notifier);

    await flujo.identificar(dibujo);
    expect(c.read(flujoProvider).fase, Fase.eligiendo);
    expect(c.read(flujoProvider).identificacion!.hipotesis.first.etiqueta, 'un dragón');

    await flujo.crear('un dragón');
    final estado = c.read(flujoProvider);
    expect(estado.fase, Fase.listo);
    expect(estado.cuento!.paginas, hasLength(3));

    flujo.noEraAsi();
    expect(c.read(flujoProvider).fase, Fase.eligiendo);
    expect(c.read(flujoProvider).dibujo, isNotNull);

    flujo.reiniciar();
    expect(c.read(flujoProvider).dibujo, isNull);
  });

  test('si la visión falla, el flujo sigue con el campo libre', () async {
    final c = await contenedor(RepoQueFalla());
    await c.read(flujoProvider.notifier).identificar(dibujo);
    final estado = c.read(flujoProvider);
    expect(estado.fase, Fase.eligiendo);
    expect(estado.identificacion!.disponible, isFalse);
  });

  test('un cuento rechazado no llega al niño', () async {
    final c = await contenedor(RepoQueFalla());
    final flujo = c.read(flujoProvider.notifier);
    await flujo.identificar(dibujo);
    await flujo.crear('algo');
    expect(c.read(flujoProvider).fase, Fase.rechazado);
    expect(c.read(flujoProvider).cuento, isNull);
  });
}
