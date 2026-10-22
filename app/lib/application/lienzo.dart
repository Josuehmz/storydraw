import 'dart:ui';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:perfect_freehand/perfect_freehand.dart';

/// Un trazo del niño: puntos con presión, color y grosor.
class Trazo {
  const Trazo({required this.puntos, required this.color, required this.grosor});

  final List<PointVector> puntos;
  final Color color;
  final double grosor;

  Trazo conPunto(PointVector p) => Trazo(puntos: [...puntos, p], color: color, grosor: grosor);
}

class EstadoLienzo {
  const EstadoLienzo({
    this.trazos = const [],
    this.actual,
    this.color = const Color(0xFF212121),
    this.grosor = 12,
  });

  final List<Trazo> trazos;
  final Trazo? actual;
  final Color color;
  final double grosor;

  bool get vacio => trazos.isEmpty && actual == null;

  EstadoLienzo copiar({
    List<Trazo>? trazos,
    Trazo? actual,
    bool sinActual = false,
    Color? color,
    double? grosor,
  }) => EstadoLienzo(
    trazos: trazos ?? this.trazos,
    actual: sinActual ? null : (actual ?? this.actual),
    color: color ?? this.color,
    grosor: grosor ?? this.grosor,
  );
}

class LienzoNotifier extends Notifier<EstadoLienzo> {
  @override
  EstadoLienzo build() => const EstadoLienzo();

  void empezar(Offset p, [double presion = 0.5]) {
    state = state.copiar(
      actual: Trazo(
        puntos: [PointVector(p.dx, p.dy, presion)],
        color: state.color,
        grosor: state.grosor,
      ),
    );
  }

  void mover(Offset p, [double presion = 0.5]) {
    final actual = state.actual;
    if (actual == null) return;
    state = state.copiar(actual: actual.conPunto(PointVector(p.dx, p.dy, presion)));
  }

  void terminar() {
    final actual = state.actual;
    if (actual == null) return;
    state = state.copiar(trazos: [...state.trazos, actual], sinActual: true);
  }

  void deshacer() {
    if (state.trazos.isEmpty) return;
    state = state.copiar(trazos: state.trazos.sublist(0, state.trazos.length - 1));
  }

  void limpiar() => state = EstadoLienzo(color: state.color, grosor: state.grosor);

  void elegirColor(Color c) => state = state.copiar(color: c);

  void elegirGrosor(double g) => state = state.copiar(grosor: g);
}

final lienzoProvider = NotifierProvider<LienzoNotifier, EstadoLienzo>(LienzoNotifier.new);
