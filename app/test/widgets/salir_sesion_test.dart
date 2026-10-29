import 'package:flutter/material.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/core/config.dart';
import 'package:storydraw/core/http.dart';
import 'package:storydraw/data/repositorios_api.dart';
import 'package:storydraw/data/repositorios_invitado.dart';
import 'package:storydraw/presentation/app.dart';

import '../ayudantes.dart';
import '../http_falso.dart';

/// Regresión: «Salir del modo invitado» y «Cerrar sesión» no hacían nada porque
/// `SesionNotifier.cerrar` leía `cuentasRepositorioProvider`, que depende de
/// `sesionProvider` (Riverpod 3 lanza `CircularDependencyError`).
void main() {
  const config = AppConfig(apiUrl: 'http://backend.prueba', modoInvitado: true);

  List<Override> overrides(HttpFalso http) => [
    configProvider.overrideWithValue(config),
    dioProvider.overrideWith((ref) {
      final s = ref.watch(sesionLocalProvider);
      return crearDio(config, token: () => s.token)..httpClientAdapter = http;
    }),
    cuentasInvitadoProvider.overrideWith(
      (ref) =>
          CuentasRepositorioInvitado(ref.watch(dioProvider), ref.watch(sesionLocalProvider), null),
    ),
    cuentasApiProvider.overrideWith(
      (ref) => CuentasRepositorioApi(ref.watch(dioProvider), ref.watch(sesionLocalProvider), null),
    ),
  ];

  testWidgets('salir del modo invitado vuelve al acceso', (tester) async {
    usarTelefono(tester);
    final http = HttpFalso(
      (o) => o.path == '/v1/invitado'
          ? respuestaJson({'access_token': 'jwt-invitado', 'rol': 'invitado'}, 201)
          : respuestaJson({}, 404),
    );
    await tester.pumpWidget(
      await montar(const StoryDrawApp(), preferencias: const {}, overrides: overrides(http)),
    );
    await tester.pump();
    final boton = find.byKey(const Key('boton-invitado'));
    await tester.ensureVisible(boton);
    await tester.tap(boton);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('perfiles-vacio')), findsOneWidget);

    await tester.tap(find.byTooltip('Salir del modo invitado'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('boton-invitado')), findsOneWidget);
    expect(find.byKey(const Key('perfiles-vacio')), findsNothing);
  });

  testWidgets('cerrar sesión con cuenta vuelve al acceso', (tester) async {
    usarTelefono(tester);
    final http = HttpFalso(
      (o) => o.path == '/v1/perfiles' ? respuestaJson(<Object>[], 200) : respuestaJson({}, 404),
    );
    await tester.pumpWidget(
      await montar(
        const StoryDrawApp(),
        preferencias: const {'sesion.token': 'jwt-de-prueba'},
        overrides: overrides(http),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('perfiles-vacio')), findsOneWidget);

    await tester.tap(find.byTooltip('Cerrar sesión'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('boton-invitado')), findsOneWidget);
  });
}
