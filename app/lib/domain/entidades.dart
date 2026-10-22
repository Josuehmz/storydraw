import 'package:flutter/foundation.dart';

/// Entidades del dominio: no saben nada de HTTP, Hive ni widgets.

@immutable
class Perfil {
  const Perfil({required this.id, required this.apodo, required this.edad});

  final String id;
  final String apodo;
  final int edad;

  factory Perfil.desdeJson(Map<String, dynamic> j) =>
      Perfil(id: j['id'] as String, apodo: j['apodo'] as String, edad: j['edad'] as int);
}

@immutable
class Hipotesis {
  const Hipotesis(this.etiqueta, this.confianza);

  final String etiqueta;

  /// De 0 a 1.
  final double confianza;

  int get porcentaje => (confianza * 100).round();

  NivelConfianza get nivel => confianza >= 0.7
      ? NivelConfianza.alta
      : confianza >= 0.4
      ? NivelConfianza.media
      : NivelConfianza.baja;
}

enum NivelConfianza { alta, media, baja }

@immutable
class Identificacion {
  const Identificacion({required this.disponible, required this.hipotesis});

  const Identificacion.noDisponible() : disponible = false, hipotesis = const [];

  final bool disponible;
  final List<Hipotesis> hipotesis;

  factory Identificacion.desdeJson(Map<String, dynamic> j) => Identificacion(
    disponible: j['disponible'] as bool,
    hipotesis: [
      for (final h in (j['hipotesis'] as List).cast<Map<String, dynamic>>())
        Hipotesis(h['etiqueta'] as String, (h['confianza'] as num).toDouble()),
    ],
  );
}

enum EstadoCuento { enProceso, listo, rechazado, fallido }

EstadoCuento estadoDesde(String valor) => switch (valor) {
  'listo' => EstadoCuento.listo,
  'rechazado' => EstadoCuento.rechazado,
  'fallido' => EstadoCuento.fallido,
  _ => EstadoCuento.enProceso,
};

/// Avisos de degradación que manda el backend.
abstract final class Avisos {
  static const sinEscenarios = 'sin_escenarios';
  static const sinIdentificacion = 'sin_identificacion';
}

@immutable
class Pagina {
  const Pagina({required this.numero, required this.texto, required this.imagenUrl, this.imagen});

  final int numero;
  final String texto;
  final String imagenUrl;

  /// Bytes ya descargados (caché local para releer sin conexión).
  final Uint8List? imagen;

  Pagina conMedios({Uint8List? imagen}) =>
      Pagina(numero: numero, texto: texto, imagenUrl: imagenUrl, imagen: imagen ?? this.imagen);

  factory Pagina.desdeJson(Map<String, dynamic> j) => Pagina(
    numero: j['numero'] as int,
    texto: j['texto'] as String,
    imagenUrl: j['imagen_url'] as String,
  );

  Map<String, dynamic> aJson() => {'numero': numero, 'texto': texto, 'imagen_url': imagenUrl};
}

@immutable
class Cuento {
  const Cuento({
    required this.id,
    required this.perfilId,
    required this.estado,
    this.titulo,
    this.personaje,
    this.avisos = const [],
    this.paginas = const [],
    required this.creadoEn,
  });

  final String id;
  final String perfilId;
  final EstadoCuento estado;
  final String? titulo;
  final String? personaje;
  final List<String> avisos;
  final List<Pagina> paginas;
  final DateTime creadoEn;

  Cuento conPaginas(List<Pagina> nuevas) => Cuento(
    id: id,
    perfilId: perfilId,
    estado: estado,
    titulo: titulo,
    personaje: personaje,
    avisos: avisos,
    paginas: nuevas,
    creadoEn: creadoEn,
  );

  factory Cuento.desdeJson(Map<String, dynamic> j) => Cuento(
    id: j['id'] as String,
    perfilId: j['perfil_id'] as String,
    estado: estadoDesde(j['estado'] as String),
    titulo: j['titulo'] as String?,
    personaje: j['personaje'] as String?,
    avisos: (j['avisos'] as List? ?? const []).cast<String>(),
    paginas: [
      for (final p in (j['paginas'] as List? ?? const []).cast<Map<String, dynamic>>())
        Pagina.desdeJson(p),
    ],
    creadoEn: DateTime.parse(j['creado_en'] as String),
  );

  Map<String, dynamic> aJson() => {
    'id': id,
    'perfil_id': perfilId,
    'estado': switch (estado) {
      EstadoCuento.listo => 'listo',
      EstadoCuento.rechazado => 'rechazado',
      EstadoCuento.fallido => 'fallido',
      EstadoCuento.enProceso => 'en_proceso',
    },
    'titulo': titulo,
    'personaje': personaje,
    'avisos': avisos,
    'paginas': [for (final p in paginas) p.aJson()],
    'creado_en': creadoEn.toIso8601String(),
  };
}
