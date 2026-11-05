import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/core/config.dart';
import 'package:storydraw/core/correo.dart';
import 'package:storydraw/core/errores.dart';
import 'package:storydraw/domain/repositorios.dart';
import 'package:storydraw/presentation/app.dart';

import '../ayudantes.dart';

void main() {
  group('reglas del correo', () {
    const gmailHotmail = ['gmail.com', 'hotmail.com'];

    test('la lista llega de la compilación, sin espacios, arrobas ni mayúsculas', () {
      expect(dominiosDesde(''), isEmpty);
      expect(dominiosDesde(' gmail.com, @Hotmail.com ,'), gmailHotmail);
      expect(nombresDominios(gmailHotmail), 'Gmail y Hotmail');
      expect(nombresDominios(['gmail.com']), 'Gmail');
    });

    test('sin lista, cualquier dominio pasa (el servidor revisa el formato)', () {
      for (final correo in ['ana@yahoo.com', 'ana@gmail.com', 'luis@colegio.edu.co']) {
        expect(esCorreoPermitido(correo, const []), isTrue, reason: correo);
      }
    });

    test('con Gmail y Hotmail, solo esos, sin importar mayúsculas ni espacios', () {
      for (final ok in ['ana@gmail.com', ' Ana@GMAIL.com ', 'luis@hotmail.com']) {
        expect(esCorreoPermitido(ok, gmailHotmail), isTrue, reason: ok);
      }
      for (final mal in [
        'ana@yahoo.com',
        'ana@outlook.com',
        'ana@gmail.com.evil.com',
        'ana@evilgmail.com',
        'ana@mail.hotmail.com',
        'gmail.com',
        '@gmail.com',
        '',
      ]) {
        expect(esCorreoPermitido(mal, gmailHotmail), isFalse, reason: mal);
      }
    });

    test('solo el enlace de «correo confirmado» cuenta', () {
      expect(
        correoConfirmadoDe(Uri.parse('storydraw://verificado?email=ana%40gmail.com')),
        'ana@gmail.com',
      );
      expect(correoConfirmadoDe(Uri.parse('storydraw://verificado')), '');
      expect(correoConfirmadoDe(Uri.parse('storydraw://otra-cosa?email=a%40gmail.com')), isNull);
      expect(correoConfirmadoDe(Uri.parse('https://verificado/?email=a%40gmail.com')), isNull);
    });
  });

  /// Por defecto la app se compila con la lista de Gmail y Hotmail, como la rama de Tomás;
  /// `dominios: const []` es la configuración por defecto (cualquier correo).
  Future<CuentasRepositorioFalso> abrir(
    WidgetTester tester, {
    EnlacesFalso? enlaces,
    List<String> dominios = const ['gmail.com', 'hotmail.com'],
  }) async {
    usarTelefono(tester);
    final cuentas = CuentasRepositorioFalso();
    await tester.pumpWidget(
      await montar(
        const StoryDrawApp(),
        preferencias: const {},
        enlaces: enlaces,
        overrides: [
          cuentasRepositorioProvider.overrideWithValue(cuentas),
          // Iniciar sesión pasa por cuentasApiProvider (el notifier de la sesión no lee
          // cuentasRepositorioProvider: dependería de sí mismo).
          cuentasApiProvider.overrideWithValue(cuentas),
          configProvider.overrideWithValue(
            AppConfig(apiUrl: 'http://backend.prueba', dominiosCorreo: dominios),
          ),
        ],
      ),
    );
    await tester.pump();
    return cuentas;
  }

  Future<void> registrarse(WidgetTester tester, String correo) async {
    await tester.tap(find.text('Crear cuenta').first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('campo-email')), correo);
    await tester.enterText(find.byKey(const Key('campo-contrasena')), 'una-clave-larga-123');
    await tester.ensureVisible(find.byKey(const Key('consentimiento')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('consentimiento')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('boton-acceso')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('boton-acceso')));
    await tester.pumpAndSettle();
  }

  testWidgets('un correo que no es de Gmail ni Hotmail se rechaza sin llamar al servidor', (
    tester,
  ) async {
    final cuentas = await abrir(tester);
    await registrarse(tester, 'ana@yahoo.com');
    expect(find.text('Solo se aceptan correos de Gmail y Hotmail.'), findsOneWidget);
    expect(cuentas.registrados, isEmpty);
    expect(find.byKey(const Key('boton-reenviar')), findsNothing);
  });

  testWidgets('el servidor también puede rechazar el dominio', (tester) async {
    final cuentas = await abrir(tester);
    cuentas.errorAlRegistrar = const ErrorApi(TipoError.dominioNoPermitido, 'dominio_no_permitido');
    await registrarse(tester, 'ana@gmail.com');
    expect(find.text('Solo se aceptan correos de Gmail y Hotmail.'), findsOneWidget);
  });

  testWidgets('sin lista de dominios, cualquier correo llega al servidor y no hay pista', (
    tester,
  ) async {
    final cuentas = await abrir(tester, dominios: const []);
    await tester.tap(find.text('Crear cuenta').first);
    await tester.pumpAndSettle();
    expect(find.textContaining('Solo Gmail'), findsNothing);
    await registrarse(tester, 'ana@yahoo.com');
    expect(cuentas.registrados, ['ana@yahoo.com']);
  });

  testWidgets('sin lista en la app, el rechazo del servidor se explica en general', (tester) async {
    final cuentas = await abrir(tester, dominios: const []);
    cuentas.errorAlRegistrar = const ErrorApi(TipoError.dominioNoPermitido, 'dominio_no_permitido');
    await registrarse(tester, 'ana@yahoo.com');
    expect(find.text('Ese correo no se acepta para crear una cuenta.'), findsOneWidget);
  });

  testWidgets('con Gmail se crea la cuenta, se explica el correo y se puede reenviar', (
    tester,
  ) async {
    final cuentas = await abrir(tester);
    await registrarse(tester, 'ana@gmail.com');
    expect(cuentas.registrados, ['ana@gmail.com']);
    expect(find.textContaining('Te enviamos un correo a ana@gmail.com'), findsOneWidget);

    await tester.tap(find.byKey(const Key('boton-reenviar')));
    await tester.pumpAndSettle();
    expect(cuentas.reenviados, ['ana@gmail.com']);
    expect(find.textContaining('te reenviamos el correo'), findsOneWidget);
  });

  testWidgets('si el servidor no pide confirmar el correo, crear la cuenta ya entra', (
    tester,
  ) async {
    final cuentas = await abrir(tester);
    cuentas.resultadoRegistro = ResultadoRegistro.listaParaEntrar;
    await registrarse(tester, 'ana@gmail.com');
    expect(cuentas.registrados, ['ana@gmail.com']);
    expect(cuentas.entradas, ['ana@gmail.com']);
    // Ya no está el acceso: pasó a elegir quién va a dibujar.
    expect(find.byKey(const Key('campo-email')), findsNothing);
    expect(find.byKey(const Key('boton-reenviar')), findsNothing);
    expect(find.textContaining('Te enviamos un correo'), findsNothing);
  });

  testWidgets('si el correo no pudo salir, se avisa y se ofrece reenviar', (tester) async {
    final cuentas = await abrir(tester);
    cuentas.correoEnviado = false;
    await registrarse(tester, 'luis@hotmail.com');
    expect(find.textContaining('el correo no pudo salir'), findsOneWidget);
    expect(find.byKey(const Key('boton-reenviar')), findsOneWidget);
  });

  testWidgets('entrar sin confirmar el correo ofrece reenviarlo', (tester) async {
    final cuentas = await abrir(tester);
    cuentas.errorAlEntrar = const ErrorApi(TipoError.correoSinVerificar);
    await tester.enterText(find.byKey(const Key('campo-email')), 'ana@gmail.com');
    await tester.enterText(find.byKey(const Key('campo-contrasena')), 'una-clave-larga-123');
    await tester.tap(find.byKey(const Key('boton-acceso')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Primero confirma tu correo'), findsOneWidget);
    expect(find.byKey(const Key('boton-reenviar')), findsOneWidget);
  });

  testWidgets('con la app abierta, el enlace del correo prellena el acceso y avisa', (
    tester,
  ) async {
    final enlaces = EnlacesFalso();
    await abrir(tester, enlaces: enlaces);
    // Estaba en «Crear cuenta»; al confirmar pasa a «Entrar»
    await tester.tap(find.text('Crear cuenta').first);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('consentimiento')), findsOneWidget);

    enlaces.llegar(Uri.parse('storydraw://verificado?email=ana%40gmail.com'));
    await tester.pumpAndSettle();

    expect(find.text('¡Correo confirmado! Ya puedes iniciar sesión.'), findsOneWidget);
    expect(find.byKey(const Key('consentimiento')), findsNothing);
    final campo = tester.widget<TextField>(find.byKey(const Key('campo-email')));
    expect(campo.controller!.text, 'ana@gmail.com');
  });

  testWidgets('con la app cerrada, el enlace del correo la abre ya confirmada', (tester) async {
    await abrir(
      tester,
      enlaces: EnlacesFalso(
        inicialUri: Uri.parse('storydraw://verificado?email=luis%40hotmail.com'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('¡Correo confirmado! Ya puedes iniciar sesión.'), findsOneWidget);
    final campo = tester.widget<TextField>(find.byKey(const Key('campo-email')));
    expect(campo.controller!.text, 'luis@hotmail.com');
  });

  testWidgets('otros enlaces no cambian nada', (tester) async {
    final enlaces = EnlacesFalso();
    await abrir(tester, enlaces: enlaces);
    enlaces.llegar(Uri.parse('storydraw://otra-cosa?email=ana%40gmail.com'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Correo confirmado'), findsNothing);
  });
}
