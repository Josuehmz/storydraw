import 'package:shared_preferences/shared_preferences.dart';

/// Sesión y preferencias en SharedPreferences: token JWT y perfil activo.
class SesionLocal {
  SesionLocal(this._prefs);

  final SharedPreferences _prefs;

  static const _token = 'sesion.token';
  static const _perfilId = 'sesion.perfil_id';
  static const _perfilApodo = 'sesion.perfil_apodo';
  static const _perfilEdad = 'sesion.perfil_edad';

  String? get token => _prefs.getString(_token);

  Future<void> guardarToken(String token) => _prefs.setString(_token, token);

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

  Future<void> cerrar() async {
    await _prefs.remove(_token);
    await olvidarPerfil();
  }
}
