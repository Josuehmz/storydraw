import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/application/flujo_cuento.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/core/config.dart';
import 'package:storydraw/presentation/momento_magico/pantalla_momento_magico.dart';

import '../ayudantes.dart';

class FlujoGenerando extends FlujoCuentoNotifier {
  @override
  EstadoFlujo build() => const EstadoFlujo(fase: Fase.generando, personaje: 'un dragón');
}

class FlujoConError extends FlujoCuentoNotifier {
  @override
  EstadoFlujo build() => const EstadoFlujo(fase: Fase.generando, personaje: 'un dragón');

  void fallar() => state = state.copiar(fase: Fase.error);
}

Future<void> _montar(WidgetTester tester, FlujoCuentoNotifier Function() flujo) async {
  usarTelefono(tester);
  await tester.pumpWidget(
    await montar(
      const PantallaMomentoMagico(),
      overrides: [
        flujoProvider.overrideWith(flujo),
        configProvider.overrideWithValue(const AppConfig(apiUrl: 'http://backend.prueba')),
      ],
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('pasados 60 s aparece el aviso de demora, con reloj de arena', (tester) async {
    await _montar(tester, FlujoGenerando.new);
    expect(find.byKey(const Key('aviso-demora')), findsNothing);

    await tester.pump(const Duration(seconds: 59));
    expect(find.byKey(const Key('aviso-demora')), findsNothing);
    expect(find.text(textoAvisoDemora), findsNothing);

    await tester.pump(const Duration(seconds: 2));
    expect(find.byKey(const Key('aviso-demora')), findsOneWidget);
    expect(find.text(textoAvisoDemora), findsOneWidget);
    // Lo visual, para el niño que no lee: el reloj de arena que gira
    expect(find.byIcon(Icons.hourglass_bottom), findsOneWidget);
    expect(
      find.ancestor(
        of: find.byIcon(Icons.hourglass_bottom),
        matching: find.byType(RotationTransition),
      ),
      findsOneWidget,
    );
  });

  testWidgets('si el cuento falla antes de 60 s, el aviso no llega a salir', (tester) async {
    late FlujoConError flujo;
    await _montar(tester, () => flujo = FlujoConError());
    await tester.pump(const Duration(seconds: 10));
    flujo.fallar();
    await tester.pump();
    await tester.pump(const Duration(seconds: 60));
    expect(find.byKey(const Key('aviso-demora')), findsNothing);
    expect(find.byKey(const Key('boton-reintentar')), findsOneWidget);
  });
}
