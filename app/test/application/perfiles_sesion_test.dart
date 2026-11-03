import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:storydraw/application/proveedores.dart';
import 'package:storydraw/data/sesion_local.dart';
import 'package:storydraw/domain/entidades.dart';
import 'package:storydraw/domain/repositorios.dart';
import 'package:storydraw/presentation/perfiles/pantalla_perfiles.dart';

import '../ayudantes.dart';

/// Devuelve los perfiles de la cuenta con la que se entró por última vez.
class _CuentasPorCorreo extends CuentasRepositorioFalso {
  final porCorreo = <String, List<Perfil>>{};
  String? actual;

  @override
  Future<void> iniciarSesion({required String email, required String contrasena}) async =>
      actual = email;

  @override
  Future<List<Perfil>> perfiles() async => porCorreo[actual] ?? [];
}

void main() {
  test(
    'al cambiar de cuenta se piden de nuevo los perfiles y no se ven los de la anterior',
    () async {
      SharedPreferences.setMockInitialValues({'sesion.token': 'jwt-de-ana'});
      final prefs = await SharedPreferences.getInstance();
      final cuentas = _CuentasPorCorreo()
        ..actual = 'ana@gmail.com'
        ..porCorreo.addAll({
          'ana@gmail.com': const [Perfil(id: 'a1', apodo: 'Luna', edad: 8)],
          'luis@hotmail.com': const [Perfil(id: 'l1', apodo: 'Mateo', edad: 10)],
        });
      final c = ProviderContainer(
        overrides: [
          sesionLocalProvider.overrideWithValue(SesionLocal(prefs)),
          cuentasRepositorioProvider.overrideWith((ref) => cuentas as CuentasRepositorio),
        ],
      );
      addTearDown(c.dispose);

      final deAna = await c.read(perfilesProvider.future);
      expect(deAna.map((p) => p.apodo), ['Luna']);

      // Ana cierra sesión y entra Luis en el mismo teléfono
      await c.read(sesionProvider.notifier).cerrar();
      await c.read(sesionProvider.notifier).iniciar('luis@hotmail.com', 'una-clave-larga-123');

      final deLuis = await c.read(perfilesProvider.future);
      expect(deLuis.map((p) => p.apodo), ['Mateo']);
    },
  );

  test('iniciar sesión olvida un perfil guardado de otra cuenta', () async {
    SharedPreferences.setMockInitialValues({
      'sesion.token': 'jwt-viejo',
      'sesion.perfil_id': 'perfil-de-otra-cuenta',
      'sesion.perfil_apodo': 'Ajeno',
      'sesion.perfil_edad': 8,
    });
    final prefs = await SharedPreferences.getInstance();
    final c = ProviderContainer(
      overrides: [
        sesionLocalProvider.overrideWithValue(SesionLocal(prefs)),
        cuentasRepositorioProvider.overrideWith((ref) => CuentasRepositorioFalso()),
      ],
    );
    addTearDown(c.dispose);
    expect(c.read(sesionProvider).perfil?.apodo, 'Ajeno');

    await c.read(sesionProvider.notifier).iniciar('luis@hotmail.com', 'una-clave-larga-123');

    expect(c.read(sesionProvider).perfil, isNull);
    expect(prefs.getString('sesion.perfil_id'), isNull);
  });
}
