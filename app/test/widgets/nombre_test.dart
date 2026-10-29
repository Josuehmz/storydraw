import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/application/flujo_cuento.dart';
import 'package:storydraw/presentation/nombre/pantalla_nombre.dart';

import '../ayudantes.dart';

void main() {
  test('la pregunta usa lo que dibujó, sin el artículo', () {
    expect(sustantivoDe('un pez'), 'pez');
    expect(sustantivoDe('una caja'), 'caja');
    expect(sustantivoDe('Un carro'), 'carro');
    expect(sustantivoDe('las nubes'), 'nubes');
    expect(sustantivoDe('dragón'), 'dragón');
    expect(sustantivoDe('un'), 'un'); // no deja la pregunta vacía
  });

  Future<FlujoFijo> abrir(WidgetTester tester, String personaje) async {
    usarTelefono(tester);
    final flujo = FlujoFijo(
      EstadoFlujo(fase: Fase.eligiendo, dibujo: Uint8List.fromList(pngMinimo)),
    );
    await tester.pumpWidget(
      await montar(
        PantallaNombre(personaje: personaje),
        overrides: [flujoProvider.overrideWith(() => flujo)],
      ),
    );
    await tester.pump();
    return flujo;
  }

  testWidgets('pregunta por el nombre de lo que dibujó', (tester) async {
    await abrir(tester, 'un pez');
    expect(find.text('¿Cuál es el nombre de tu pez?'), findsOneWidget);
    expect(find.byKey(const Key('boton-ver-cuento')), findsOneWidget);
  });

  testWidgets('«Ver cuento» crea el cuento con el nombre que escribió', (tester) async {
    final flujo = await abrir(tester, 'un carro');
    await tester.enterText(find.byKey(const Key('campo-nombre')), ' Rayo ');
    await tester.tap(find.byKey(const Key('boton-ver-cuento')));
    await tester.pump();
    expect(flujo.creados, ['un carro']);
    expect(flujo.nombres, ['Rayo']);
  });

  testWidgets('el nombre es opcional: vacío también crea el cuento', (tester) async {
    final flujo = await abrir(tester, 'un pez');
    await tester.tap(find.byKey(const Key('boton-ver-cuento')));
    await tester.pump();
    expect(flujo.creados, ['un pez']);
    expect(flujo.nombres, ['']);
  });
}
