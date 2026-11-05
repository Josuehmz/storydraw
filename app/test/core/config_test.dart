import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/core/config.dart';

void main() {
  test('sin --dart-define la configuración arranca con sus valores por defecto', () {
    // Las demás pruebas sustituyen configProvider; esta pasa por el camino real de la app.
    final config = AppConfig.desdeEntorno();
    expect(config.apiUrl, 'http://10.0.2.2:8000');
    expect(config.modoInvitado, isFalse);
    expect(config.dominiosCorreo, isEmpty);
  });
}
