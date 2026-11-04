import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/domain/entidades.dart';
import 'package:storydraw/presentation/biblioteca/pantalla_biblioteca.dart';
import 'package:storydraw/presentation/cuento/pantalla_cuento.dart';

import '../ayudantes.dart';

void main() {
  testWidgets('el visor avanza y retrocede con botones', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(PantallaCuento(cuento: cuentoDePrueba())));
    await tester.pump();

    expect(find.text('Texto de la página 1'), findsOneWidget);
    expect(find.byType(Image), findsOneWidget);
    expect(find.byKey(const Key('aviso-sin-escenarios')), findsNothing);

    await tester.tap(find.byKey(const Key('boton-siguiente')));
    await tester.pump();
    expect(find.text('Texto de la página 2'), findsOneWidget);

    await tester.tap(find.byKey(const Key('boton-siguiente')));
    await tester.pump();
    expect(find.byKey(const Key('boton-fin')), findsOneWidget);
    expect(find.byKey(const Key('boton-siguiente')), findsNothing);

    await tester.tap(find.byKey(const Key('boton-anterior')));
    await tester.pump();
    expect(find.text('Texto de la página 2'), findsOneWidget);
  });

  testWidgets('el botón de escuchar lee solo la página que se ve', (tester) async {
    usarTelefono(tester);
    final voz = ReproductorFalso();
    await tester.pumpWidget(
      await montar(PantallaCuento(cuento: cuentoDePrueba()), reproductor: voz),
    );
    await tester.pump();

    await tester.tap(find.byKey(const Key('boton-escuchar')));
    await tester.pump();
    expect(voz.reproducidos, [
      [1, 1],
    ]);

    // Al pasar de página, la lectura anterior se corta y el botón lee la nueva
    final antes = voz.detenciones;
    await tester.tap(find.byKey(const Key('boton-siguiente')));
    await tester.pump();
    expect(voz.detenciones, greaterThan(antes));
    await tester.tap(find.byKey(const Key('boton-escuchar')));
    await tester.pump();
    expect(voz.reproducidos.last, [2, 2]);
  });

  testWidgets('mientras suena el botón es de parar, y al tocarlo se detiene', (tester) async {
    usarTelefono(tester);
    final voz = ReproductorFalso();
    await tester.pumpWidget(
      await montar(PantallaCuento(cuento: cuentoDePrueba()), reproductor: voz),
    );
    await tester.pump();
    expect(find.byIcon(Icons.volume_up_rounded), findsOneWidget);

    await tester.tap(find.byKey(const Key('boton-escuchar')));
    await tester.pump();
    expect(find.byIcon(Icons.stop_rounded), findsOneWidget);

    final antes = voz.detenciones;
    await tester.tap(find.byKey(const Key('boton-escuchar')));
    await tester.pump();
    expect(voz.detenciones, antes + 1);
    expect(find.byIcon(Icons.volume_up_rounded), findsOneWidget);
  });

  testWidgets('una página sin narración no muestra el botón de escuchar', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(PantallaCuento(cuento: cuentoDePrueba(conAudio: false))));
    await tester.pump();
    expect(find.byKey(const Key('boton-escuchar')), findsNothing);
    expect(find.text('Texto de la página 1'), findsOneWidget);
  });

  testWidgets('el botón de escuchar mide al menos 64 dp', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(await montar(PantallaCuento(cuento: cuentoDePrueba())));
    await tester.pump();
    final tamano = tester.getSize(find.byKey(const Key('boton-escuchar')));
    expect(tamano.width, greaterThanOrEqualTo(64));
    expect(tamano.height, greaterThanOrEqualTo(64));
  });

  testWidgets('al salir del cuento la narración deja de sonar', (tester) async {
    usarTelefono(tester);
    final voz = ReproductorFalso();
    await tester.pumpWidget(
      await montar(PantallaCuento(cuento: cuentoDePrueba()), reproductor: voz),
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('boton-escuchar')));
    await tester.pump();

    final antes = voz.detenciones;
    await tester.pumpWidget(const SizedBox());
    expect(voz.detenciones, greaterThan(antes));
  });

  testWidgets('sin escenarios, el aviso es informativo', (tester) async {
    usarTelefono(tester);
    await tester.pumpWidget(
      await montar(PantallaCuento(cuento: cuentoDePrueba(avisos: [Avisos.sinEscenarios]))),
    );
    await tester.pump();
    expect(find.byKey(const Key('aviso-sin-escenarios')), findsOneWidget);
    expect(find.text('Información importante'), findsOneWidget);
    expect(find.byIcon(Icons.info_outline), findsOneWidget);
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
