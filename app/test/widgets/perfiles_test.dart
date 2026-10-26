import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/domain/entidades.dart';
import 'package:storydraw/domain/repositorios.dart';
import 'package:storydraw/presentation/perfiles/pantalla_perfiles.dart';

import '../ayudantes.dart';

class CuentasRepositorioFalso implements CuentasRepositorio {
  CuentasRepositorioFalso([List<Perfil>? perfiles]) : lista = perfiles ?? [];

  final List<Perfil> lista;

  @override
  Future<List<Perfil>> perfiles() async => List.of(lista);

  @override
  Future<Perfil> crearPerfil({required String apodo, required int edad}) async {
    final p = Perfil(id: 'p${lista.length + 1}', apodo: apodo, edad: edad);
    lista.add(p);
    return p;
  }

  @override
  Future<void> borrarPerfil(String perfilId) async => lista.removeWhere((p) => p.id == perfilId);

  @override
  Future<void> registrar({
    required String email,
    required String contrasena,
    required bool aceptaConsentimiento,
  }) async {}

  @override
  Future<void> iniciarSesion({required String email, required String contrasena}) async {}

  @override
  Future<void> cerrarSesion() async {}
}

Future<Widget> montarPerfiles(CuentasRepositorioFalso repo) => montar(
  const PantallaPerfiles(),
  preferencias: const {'sesion.token': 'jwt-de-prueba'},
  overrides: [cuentasRepositorioProvider.overrideWithValue(repo)],
);

void main() {
  testWidgets('con cero perfiles se ve el estado vacío y no el botón flotante', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montarPerfiles(CuentasRepositorioFalso()));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('perfiles-vacio')), findsOneWidget);
    expect(find.byKey(const Key('boton-primer-perfil')), findsOneWidget);
    expect(find.text('Crear el primer dibujante'), findsOneWidget);
    expect(find.byKey(const Key('boton-nuevo-perfil')), findsNothing);

    // Botón grande y centrado: fácil de ver y de tocar.
    final tamano = tester.getSize(find.byKey(const Key('boton-primer-perfil')));
    expect(tamano.height, greaterThanOrEqualTo(64));
    final centro = tester.getCenter(find.byKey(const Key('boton-primer-perfil')));
    expect(centro.dx, closeTo(180, 1));
  });

  testWidgets('el botón del estado vacío abre el formulario y crea el perfil', (tester) async {
    usarTelefono(tester);
    final repo = CuentasRepositorioFalso();
    await tester.pumpWidget(await montarPerfiles(repo));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('boton-primer-perfil')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('campo-apodo')), findsOneWidget);
    expect(find.text('Nuevo perfil'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('campo-apodo')), 'Sol');
    await tester.tap(find.text('Crear'));
    await tester.pumpAndSettle();

    expect(repo.lista.single.apodo, 'Sol');
    expect(find.byKey(const Key('perfiles-vacio')), findsNothing);
    expect(find.byKey(const Key('perfil-p1')), findsOneWidget);
    expect(find.byKey(const Key('boton-nuevo-perfil')), findsOneWidget);
  });

  testWidgets('con perfiles hay tarjetas con lápiz y botón con etiqueta', (tester) async {
    usarTelefono(tester);
    final repo = CuentasRepositorioFalso([
      const Perfil(id: 'p1', apodo: 'Luna', edad: 8),
      const Perfil(id: 'p2', apodo: 'Teo', edad: 10),
    ]);
    await tester.pumpWidget(await montarPerfiles(repo));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('perfiles-vacio')), findsNothing);
    expect(find.byKey(const Key('boton-primer-perfil')), findsNothing);
    for (final id in ['p1', 'p2']) {
      expect(find.byKey(Key('perfil-$id')), findsOneWidget);
      expect(find.byKey(Key('perfil-$id-dibujar')), findsOneWidget);
      final tamano = tester.getSize(find.byKey(Key('perfil-$id')));
      expect(tamano.width, greaterThanOrEqualTo(120), reason: id);
      expect(tamano.height, greaterThanOrEqualTo(120), reason: id);
    }
    expect(find.text('Nuevo dibujante'), findsOneWidget);

    // El botón flotante abre el mismo formulario.
    await tester.tap(find.byKey(const Key('boton-nuevo-perfil')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('campo-apodo')), findsOneWidget);
  });
}
