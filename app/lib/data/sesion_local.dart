import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../domain/entidades.dart';

/// Sesión y preferencias en SharedPreferences: token JWT y perfil activo.
///
/// En modo invitado (solo pruebas locales) también guarda los perfiles del
/// invitado: viven solo en este dispositivo.
class SesionLocal {
  SesionLocal(this._prefs);

  final SharedPreferences _prefs;

  static const _token = 'sesion.token';
  static const _invitado = 'sesion.invitado';
  static const _perfilId = 'sesion.perfil_id';
  static const _perfilApodo = 'sesion.perfil_apodo';
  static const _perfilEdad = 'sesion.perfil_edad';
  static const _perfilesInvitado = 'invitado.perfiles';

  String? get token => _prefs.getString(_token);

  Future<void> guardarToken(String token) => _prefs.setString(_token, token);

  bool get invitado => _prefs.getBool(_invitado) ?? false;

  Future<void> guardarTokenInvitado(String token) async {
    await _prefs.setString(_token, token);
    await _prefs.setBool(_invitado, true);
  }

  String? get perfilId => _prefs.getString(_perfilId);
  String? get perfilApodo => _prefs.getString(_perfilApodo);
  int? get perfilEdad => _prefs.getInt(_perfilEdad);

  Future<void> elegirPerfil({required String id, required String apodo, required int edad}) async {
    await _prefs.setString(_perfilId, id);
    await _prefs.setString(_perfilApodo, apodo);
    await _prefs.setInt(_perfilEdad, edad);
  }

  Future<void> olvidarPerfil() async {
    await _prefs.remove(_perfilId);
    await _prefs.remove(_perfilApodo);
    await _prefs.remove(_perfilEdad);
  }

  /// Cierra la sesión. Los perfiles y cuentos del invitado se quedan en el
  /// dispositivo para la próxima vez.
  Future<void> cerrar() async {
    await _prefs.remove(_token);
    await _prefs.remove(_invitado);
    await olvidarPerfil();
  }

  List<Perfil> get perfilesInvitado {
    final json = _prefs.getString(_perfilesInvitado);
    if (json == null) return const [];
    return [
      for (final p in (jsonDecode(json) as List).cast<Map<String, dynamic>>()) Perfil.desdeJson(p),
    ];
  }

  Future<void> guardarPerfilesInvitado(List<Perfil> perfiles) => _prefs.setString(
    _perfilesInvitado,
    jsonEncode([
      for (final p in perfiles) {'id': p.id, 'apodo': p.apodo, 'edad': p.edad},
    ]),
  );
}
