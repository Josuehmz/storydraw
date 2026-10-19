import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/application/flujo_cuento.dart';
import 'package:storydraw/domain/entidades.dart';
import 'package:storydraw/presentation/identificacion/pantalla_identificacion.dart';

import '../ayudantes.dart';

class FlujoFijo extends FlujoCuentoNotifier {
  FlujoFijo(this.inicial);

  final EstadoFlujo inicial;
  final creados = <String>[];

  @override
  EstadoFlujo build() => inicial;

  @override
  Future<void> crear(String personaje) async => creados.add(personaje);
}

void main() {
  final dibujo = Uint8List.fromList(pngMinimo);

  testWidgets('muestra cada hipótesis con su confianza y el campo libre', (tester) async {
    usarTelefono(tester);
    final flujo = FlujoFijo(
      EstadoFlujo(
        fase: Fase.eligiendo,
        dibujo: dibujo,
        identificacion: const Identificacion(
          disponible: true,
          hipotesis: [Hipotesis('un dragón', 0.81), Hipotesis('un dinosaurio', 0.44)],
        ),
      ),
    );
    await tester.pumpWidget(
      await montar(
        const PantallaIdentificacion(),
        overrides: [flujoProvider.overrideWith(() => flujo)],
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('mensaje-ia')), findsOneWidget);
    expect(find.byKey(const Key('etiqueta-confianza')), findsOneWidget);
    expect(find.text('un dragón'), findsOneWidget);
    expect(find.text('81 %'), findsOneWidget);
    expect(find.text('44 %'), findsOneWidget);
    // El campo libre está siempre visible, no escondido.
    expect(find.byKey(const Key('campo-libre')), findsOneWidget);

    await tester.ensureVisible(find.text('un dinosaurio'));
    await tester.pump();
    await tester.tap(find.text('un dinosaurio'));
    await tester.pump();
    expect(flujo.creados, ['un dinosaurio']);
  });

  testWidgets('lo que escribe el niño manda sobre el modelo', (tester) async {
    usarTelefono(tester);
    final flujo = FlujoFijo(
      EstadoFlujo(
        fase: Fase.eligiendo,
        dibujo: dibujo,
        identificacion: const Identificacion(
          disponible: true,
          hipotesis: [Hipotesis('un dragón', 0.81)],
        ),
      ),
    );
    await tester.pumpWidget(
      await montar(
        const PantallaIdentificacion(),
        overrides: [flujoProvider.overrideWith(() => flujo)],
      ),
    );
    await tester.pump();
    await tester.enterText(find.byKey(const Key('campo-libre')), 'mi gata Nube');
    await tester.ensureVisible(find.byKey(const Key('boton-enviar-libre')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('boton-enviar-libre')));
    await tester.pump();
    expect(flujo.creados, ['mi gata Nube']);
  });

  testWidgets('sin visión, solo queda el campo libre', (tester) async {
    usarTelefono(tester);
    final flujo = FlujoFijo(
      EstadoFlujo(
        fase: Fase.eligiendo,
        dibujo: dibujo,
        identificacion: const Identificacion.noDisponible(),
      ),
    );
    await tester.pumpWidget(
      await montar(
        const PantallaIdentificacion(),
        overrides: [flujoProvider.overrideWith(() => flujo)],
      ),
    );
    await tester.pump();
    expect(find.text('No pude ver bien tu dibujo. ¿Me cuentas qué es?'), findsOneWidget);
    expect(find.byKey(const Key('etiqueta-confianza')), findsNothing);
    expect(find.byKey(const Key('campo-libre')), findsOneWidget);
  });

  test('el color sigue el nivel de confianza', () {
    expect(const Hipotesis('a', 0.81).nivel, NivelConfianza.alta);
    expect(const Hipotesis('a', 0.44).nivel, NivelConfianza.media);
    expect(const Hipotesis('a', 0.12).nivel, NivelConfianza.baja);
  });
}
