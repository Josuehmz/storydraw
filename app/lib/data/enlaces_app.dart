import 'package:app_links/app_links.dart';

/// Enlaces que abren la app desde fuera (el de «correo confirmado», por ejemplo).
/// Una interfaz propia permite probar sin la plataforma.
abstract interface class EnlacesApp {
  /// El enlace con el que se abrió la app si estaba cerrada.
  Future<Uri?> inicial();

  /// Los enlaces que llegan con la app ya abierta.
  Stream<Uri> get nuevos;
}

class EnlacesAppReal implements EnlacesApp {
  final _links = AppLinks();

  @override
  Future<Uri?> inicial() => _links.getInitialLink();

  @override
  Stream<Uri> get nuevos => _links.uriLinkStream;
}
