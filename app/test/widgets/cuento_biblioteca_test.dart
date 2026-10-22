import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/domain/entidades.dart';
import 'package:storydraw/presentation/biblioteca/pantalla_biblioteca.dart';
import 'package:storydraw/presentation/cuento/pantalla_cuento.dart';

import '../ayudantes.dart';

void main() {
  testWidgets('el visor avanza y retrocede con botones y narra cada página', (tester) async {
    usarTelefono(tester);
    final reproductor = ReproductorFalso();
    await tester.pumpWidget(
      await montar(PantallaCuento(cuento: cuentoDePrueba()), reproductor: reproductor),
    );
    await tester.pump();

    expect(find.text('Texto de la página 1'), findsOneWidget);
    expect(find.byKey(const Key('aviso-sin-voz')), findsNothing);
    expect(reproductor.reproducidos.length, 1);

    await tester.tap(find.byKey(const Key('boton-siguiente')));
    await tester.pump();
    expect(find.text('Texto de la página 2'), findsOneWidget);
    expect(reproductor.reproducidos.last.last, 2);

    await tester.tap(find.byKey(const Key('boton-siguiente')));
    await tester.pump();
    expect(find.byKey(const Key('boton-fin')), findsOneWidget);
    expect(find.byKey(const Key('boton-siguiente')), findsNothing);

    await tester.tap(find.byKey(const Key('boton-anterior')));
    await tester.pump();
    expect(find.text('Texto de la página 2'), findsOneWidget);
  });

  testWidgets('sin narración, el aviso es informativo y no hay botón de audio', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(
      await montar(
        PantallaCuento(cuento: cuentoDePrueba(avisos: [Avisos.sinNarracion], conAudio: false)),
      ),
    );
    await tester.pump();
    expect(find.byKey(const Key('aviso-sin-voz')), findsOneWidget);
    expect(find.text('Información importante'), findsOneWidget);
    expect(find.byIcon(Icons.info_outline), findsOneWidget);
    expect(find.byKey(const Key('boton-narrar')), findsNothing);
  });

  testWidgets('la biblioteca muestra los cuentos y borra a petición', (tester) async {
    usarTelefono(tester);
    final repo = CuentosRepositorioFalso(
      cuentos: [
        cuentoDePrueba(id: 'c1'),
        cuentoDePrueba(id: 'c2'),
      ],
    );
    await tester.pumpWidget(
      await montar(
        const PantallaBiblioteca(),
        overrides: [cuentosRepositorioProvider.overrideWithValue(repo)],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('portada-c1')), findsOneWidget);
    expect(find.byKey(const Key('portada-c2')), findsOneWidget);

    await tester.tap(find.byKey(const Key('borrar-c1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('confirmar-si')));
    await tester.pumpAndSettle();

    expect(repo.borrados, ['c1']);
    expect(find.byKey(const Key('portada-c1')), findsNothing);
    expect(find.byKey(const Key('portada-c2')), findsOneWidget);
  });

  testWidgets('biblioteca vacía', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(
      await montar(
        const PantallaBiblioteca(),
        overrides: [cuentosRepositorioProvider.overrideWithValue(CuentosRepositorioFalso())],
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('biblioteca-vacia')), findsOneWidget);
  });
}
