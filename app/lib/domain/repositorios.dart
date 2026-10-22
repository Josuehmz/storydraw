import 'dart:typed_data';

import 'entidades.dart';

/// Contratos que la interfaz usa. Las implementaciones viven en `data/`;
/// la presentación nunca habla con Dio ni con Hive directamente.

abstract interface class CuentasRepositorio {
  Future<void> registrar({
    required String email,
    required String contrasena,
    required bool aceptaConsentimiento,
  });

  Future<void> iniciarSesion({required String email, required String contrasena});

  Future<void> cerrarSesion();

  Future<List<Perfil>> perfiles();

  Future<Perfil> crearPerfil({required String apodo, required int edad});

  Future<void> borrarPerfil(String perfilId);
}

abstract interface class CuentosRepositorio {
  /// Paso 1: hipótesis de qué dibujó el niño. El dibujo viaja en memoria.
  Future<Identificacion> identificar(Uint8List dibujo);

  /// Encola el cuento y devuelve su id.
  Future<String> crear({required String perfilId, required Uint8List dibujo, String? personaje});

  /// Consulta hasta que el cuento sale de `en_proceso` y, si está listo,
  /// descarga páginas y audio a la caché local.
  Future<Cuento> esperar(String cuentoId);

  /// Reintenta solo la narración que faltó.
  Future<Cuento> reintentarNarracion(String cuentoId);

  /// Cuentos del perfil: los de la caché siempre; los del servidor si hay red.
  Future<List<Cuento>> biblioteca(String perfilId);

  /// Borrado a petición (servidor y caché).
  Future<void> borrar(String cuentoId);
}

/// Reproductor de la narración (just_audio en la app, falso en las pruebas).
abstract interface class Reproductor {
  Stream<bool> get reproduciendo;

  Future<void> reproducir(Uint8List mp3);

  Future<void> detener();

  Future<void> liberar();
}
