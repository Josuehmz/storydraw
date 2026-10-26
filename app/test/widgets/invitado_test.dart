import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/core/config.dart';
import 'package:storydraw/core/http.dart';
import 'package:storydraw/data/repositorios_invitado.dart';
import 'package:storydraw/data/sesion_local.dart';
import 'package:storydraw/presentation/app.dart';
import 'package:storydraw/presentation/widgets/comunes.dart';

import '../ayudantes.dart';
import '../http_falso.dart';

void main() {
  testWidgets('sin MODO_INVITADO no hay botón de invitado; el logo sí está', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(const StoryDrawApp(), preferencias: const {}));
    await tester.pump();
    expect(find.byKey(const Key('logo')), findsOneWidget);
    expect(find.byKey(const Key('boton-invitado')), findsNothing);
    expect(find.text('Entrar como invitado'), findsNothing);
  });

  testWidgets('con MODO_INVITADO se entra sin cuenta y se ve el aviso', (tester) async {
    usarTelefono(tester);
    const config = AppConfig(apiUrl: 'http://backend.prueba', modoInvitado: true);
    final http = HttpFalso(
      (o) => o.path == '/v1/invitado'
          ? respuestaJson({'access_token': 'jwt-invitado', 'rol': 'invitado'}, 201)
          : respuestaJson({}, 404),
    );
    SharedPreferences.setMockInitialValues({});
    final sesion = SesionLocal(await SharedPreferences.getInstance());
    final Dio dio = crearDio(config, token: () => sesion.token)..httpClientAdapter = http;

    await tester.pumpWidget(
      await montar(
        const StoryDrawApp(),
        preferencias: const {},
        overrides: [
          configProvider.overrideWithValue(config),
          cuentasInvitadoProvider.overrideWithValue(CuentasRepositorioInvitado(dio, sesion, null)),
        ],
      ),
    );
    await tester.pump();

    final boton = find.byKey(const Key('boton-invitado'));
    await tester.ensureVisible(boton);
    expect(find.text('Entrar como invitado'), findsOneWidget);
    await tester.tap(boton);
    await tester.pumpAndSettle();

    expect(http.peticiones.single.path, '/v1/invitado');
    expect(sesion.invitado, isTrue);
    // Pantalla de perfiles (locales) con el aviso del modo invitado
    expect(find.byKey(const Key('boton-nuevo-perfil')), findsOneWidget);
    expect(find.byKey(const Key('aviso-invitado')), findsOneWidget);
    expect(find.text(textoAvisoInvitado), findsOneWidget);
  });

  testWidgets('con cuenta normal no aparece el aviso de invitado', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(
      await montar(
        const Scaffold(body: AvisoInvitado()),
        preferencias: const {'sesion.token': 'jwt-de-prueba'},
      ),
    );
    await tester.pump();
    expect(find.byKey(const Key('aviso-invitado')), findsNothing);
  });
}
