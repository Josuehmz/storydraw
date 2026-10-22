import 'dart:math';

import 'package:flutter/material.dart';

import '../../core/tema.dart';

/// Estrellas que giran y laten: la espera se cubre con animación, sin porcentajes
/// ni barras de progreso. Pintado a mano, sin assets de Lottie.
class Estrellas extends StatefulWidget {
  const Estrellas({super.key, this.tamano = 260});

  final double tamano;

  @override
  State<Estrellas> createState() => _EstrellasState();
}

class _EstrellasState extends State<Estrellas> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 4),
  )..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: widget.tamano,
      child: AnimatedBuilder(
        animation: _c,
        builder: (_, _) => CustomPaint(painter: _PintorEstrellas(_c.value)),
      ),
    );
  }
}

class _PintorEstrellas extends CustomPainter {
  _PintorEstrellas(this.t);

  final double t;

  static const _colores = [Colores.amarillo, Colores.naranja, Colors.white, Colores.amarillo];

  Path _estrella(Offset centro, double r) {
    final path = Path();
    for (var i = 0; i < 10; i++) {
      final radio = i.isEven ? r : r * 0.45;
      final a = -pi / 2 + i * pi / 5;
      final p = centro + Offset(cos(a) * radio, sin(a) * radio);
      i == 0 ? path.moveTo(p.dx, p.dy) : path.lineTo(p.dx, p.dy);
    }
    return path..close();
  }

  @override
  void paint(Canvas canvas, Size size) {
    final centro = size.center(Offset.zero);
    final base = size.shortestSide;
    for (var i = 0; i < 7; i++) {
      final a = 2 * pi * (t + i / 7);
      final orbita = base * (0.22 + 0.12 * sin(2 * pi * t + i));
      final p = centro + Offset(cos(a) * orbita, sin(a) * orbita);
      final r = base * (0.05 + 0.025 * (1 + sin(4 * pi * t + i)));
      canvas.drawPath(_estrella(p, r), Paint()..color = _colores[i % _colores.length]);
    }
    final latido = 1 + 0.08 * sin(2 * pi * t * 2);
    canvas.drawPath(_estrella(centro, base * 0.16 * latido), Paint()..color = Colores.amarillo);
  }

  @override
  bool shouldRepaint(_PintorEstrellas viejo) => viejo.t != t;
}
