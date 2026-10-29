import 'dart:convert';
import 'dart:typed_data';

import 'package:hive/hive.dart';

import '../domain/entidades.dart';

/// Caché de cuentos leídos en Hive, para releerlos sin conexión.
///
/// Sin generación de código: el cuento se guarda como JSON y los medios como
/// bytes, cada uno en su caja. El dibujo original del niño no se guarda nunca.
class CacheCuentos {
  CacheCuentos(this._cuentos, this._medios);

  static const cajaCuentos = 'cuentos';
  static const cajaMedios = 'medios';

  static Future<CacheCuentos> abrir() async => CacheCuentos(
    await Hive.openBox<String>(cajaCuentos),
    await Hive.openBox<Uint8List>(cajaMedios),
  );

  final Box<String> _cuentos;
  final Box<Uint8List> _medios;

  static String _claveImagen(String id, int n) => '$id/$n/imagen';
  static String _claveAudio(String id, int n) => '$id/$n/audio';

  Future<void> guardar(Cuento cuento) async {
    await _cuentos.put(cuento.id, jsonEncode(cuento.aJson()));
    for (final p in cuento.paginas) {
      if (p.imagen != null) await _medios.put(_claveImagen(cuento.id, p.numero), p.imagen!);
      if (p.audio != null) await _medios.put(_claveAudio(cuento.id, p.numero), p.audio!);
    }
  }

  bool contiene(String id) => _cuentos.containsKey(id);

  Cuento? leer(String id) {
    final json = _cuentos.get(id);
    if (json == null) return null;
    final cuento = Cuento.desdeJson(jsonDecode(json) as Map<String, dynamic>);
    return cuento.conPaginas([
      for (final p in cuento.paginas)
        p.conMedios(
          imagen: _medios.get(_claveImagen(id, p.numero)),
          audio: _medios.get(_claveAudio(id, p.numero)),
        ),
    ]);
  }

  List<Cuento> dePerfil(String perfilId) {
    final lista = [
      for (final id in _cuentos.keys.cast<String>())
        if (leer(id) case final c? when c.perfilId == perfilId) c,
    ];
    lista.sort((a, b) => b.creadoEn.compareTo(a.creadoEn));
    return lista;
  }

  Future<void> borrar(String id) async {
    final cuento = leer(id);
    await _cuentos.delete(id);
    for (final p in cuento?.paginas ?? const <Pagina>[]) {
      await _medios.delete(_claveImagen(id, p.numero));
      await _medios.delete(_claveAudio(id, p.numero));
    }
  }

  Future<void> borrarPerfil(String perfilId) async {
    for (final c in dePerfil(perfilId)) {
      await borrar(c.id);
    }
  }
}
