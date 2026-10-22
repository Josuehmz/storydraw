import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/presentation/lienzo/pantalla_lienzo.dart';

import '../ayudantes.dart';

void main() {
  testWidgets('el botón de crear solo aparece cuando hay al menos un trazo', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(const PantallaLienzo()));
    await tester.pump();

    expect(find.byKey(const Key('boton-crear')), findsNothing);

    await tester.drag(find.byKey(const Key('lienzo')), const Offset(120, 80));
    await tester.pump();
    expect(find.byKey(const Key('boton-crear')), findsOneWidget);

    await tester.tap(find.byKey(const Key('boton-deshacer')));
    await tester.pump();
    expect(find.byKey(const Key('boton-crear')), findsNothing);
  });

  testWidgets('los botones del niño miden al menos 48 dp', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(const PantallaLienzo()));
    await tester.drag(find.byKey(const Key('lienzo')), const Offset(60, 60));
    await tester.pump();
    for (final clave in ['boton-crear', 'boton-deshacer', 'boton-limpiar', 'boton-biblioteca']) {
      final tamano = tester.getSize(find.byKey(Key(clave)));
      expect(tamano.width, greaterThanOrEqualTo(48), reason: clave);
      expect(tamano.height, greaterThanOrEqualTo(48), reason: clave);
    }
  });

  testWidgets('borrar todo deja el lienzo vacío', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(const PantallaLienzo()));
    await tester.drag(find.byKey(const Key('lienzo')), const Offset(50, 0));
    await tester.drag(find.byKey(const Key('lienzo')), const Offset(0, 50));
    await tester.pump();
    await tester.tap(find.byKey(const Key('boton-limpiar')));
    await tester.pump();
    expect(find.byKey(const Key('boton-crear')), findsNothing);
  });
}
