import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/presentation/app.dart';

import '../ayudantes.dart';

void main() {
  testWidgets('sin sesión se muestra el acceso del adulto', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(const StoryDrawApp(), preferencias: const {}));
    await tester.pump();
    expect(find.byKey(const Key('campo-email')), findsOneWidget);
    expect(find.byKey(const Key('consentimiento')), findsNothing);
  });

  testWidgets('crear cuenta exige marcar el consentimiento', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(const StoryDrawApp(), preferencias: const {}));
    await tester.pump();
    await tester.tap(find.text('Crear cuenta').first);
    await tester.pump();

    await tester.ensureVisible(find.byKey(const Key('boton-acceso'), skipOffstage: false));
    await tester.pump();
    ElevatedButton boton() => tester.widget<ElevatedButton>(find.byKey(const Key('boton-acceso')));
    expect(find.byKey(const Key('consentimiento')), findsOneWidget);
    expect(boton().onPressed, isNull);

    await tester.tap(find.byKey(const Key('consentimiento')));
    await tester.pump();
    expect(boton().onPressed, isNotNull);
  });

  testWidgets('con sesión y perfil se abre directo el lienzo', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(const StoryDrawApp()));
    await tester.pump();
    expect(find.byKey(const Key('lienzo')), findsOneWidget);
  });
}
