import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:perfect_freehand/perfect_freehand.dart';

import '../../application/flujo_cuento.dart';
import '../../application/lienzo.dart';
import '../../application/proveedores.dart';
import '../../core/tema.dart';
import '../biblioteca/pantalla_biblioteca.dart';
import '../identificacion/pantalla_identificacion.dart';
import '../widgets/comunes.dart';

/// Lienzo de dibujo con perfect_freehand. Dos decisiones del niño: dibujar y crear.
class PantallaLienzo extends ConsumerStatefulWidget {
  const PantallaLienzo({super.key});

  @override
  ConsumerState<PantallaLienzo> createState() => _PantallaLienzoState();
}

class _PantallaLienzoState extends ConsumerState<PantallaLienzo> {
  final _clave = GlobalKey();

  static const _grosores = <double>[6, 12, 24];

  Future<void> _crear() async {
    final boundary = _clave.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final imagen = await boundary.toImage(pixelRatio: 2);
    final datos = await imagen.toByteData(format: ui.ImageByteFormat.png);
    if (datos == null || !mounted) return;
    ref.read(flujoProvider.notifier).identificar(datos.buffer.asUint8List());
    await Navigator.of(
      context,
    ).push(MaterialPageRoute<void>(builder: (_) => const PantallaIdentificacion()));
  }

  @override
  Widget build(BuildContext context) {
    final estado = ref.watch(lienzoProvider);
    final lienzo = ref.read(lienzoProvider.notifier);
    final perfil = ref.watch(sesionProvider).perfil;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  BotonIcono(
                    key: const Key('boton-perfil'),
                    icono: Icons.face,
                    etiqueta: 'Cambiar de niño: ${perfil?.apodo ?? ''}',
                    color: Colores.violeta,
                    tamano: 56,
                    alPulsar: () => ref.read(sesionProvider.notifier).cambiarPerfil(),
                  ),
                  const Spacer(),
                  BotonIcono(
                    key: const Key('boton-deshacer'),
                    icono: Icons.undo,
                    etiqueta: 'Deshacer',
                    color: Colores.azulInfo,
                    tamano: 56,
                    alPulsar: estado.trazos.isEmpty ? null : lienzo.deshacer,
                  ),
                  const SizedBox(width: 8),
                  BotonIcono(
                    key: const Key('boton-limpiar'),
                    icono: Icons.delete_sweep,
                    etiqueta: 'Borrar todo',
                    color: Colores.rojo,
                    tamano: 56,
                    alPulsar: estado.vacio ? null : lienzo.limpiar,
                  ),
                  const SizedBox(width: 8),
                  BotonIcono(
                    key: const Key('boton-biblioteca'),
                    icono: Icons.collections_bookmark,
                    etiqueta: 'Mis cuentos',
                    color: Colores.verde,
                    tamano: 56,
                    alPulsar: () => Navigator.of(
                      context,
                    ).push(MaterialPageRoute<void>(builder: (_) => const PantallaBiblioteca())),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: RepaintBoundary(
                    key: _clave,
                    child: GestureDetector(
                      key: const Key('lienzo'),
                      onPanStart: (d) => lienzo.empezar(d.localPosition),
                      onPanUpdate: (d) => lienzo.mover(d.localPosition),
                      onPanEnd: (_) => lienzo.terminar(),
                      child: CustomPaint(
                        painter: PintorLienzo(estado),
                        child: const SizedBox.expand(),
                      ),
                    ),
                  ),
                ),
              ),
            ),
            SizedBox(
              height: 64,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                children: [
                  for (final color in Colores.lienzo)
                    _Muestra(
                      color: color,
                      elegido: color == estado.color,
                      alPulsar: () => lienzo.elegirColor(color),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
              child: Row(
                children: [
                  for (final g in _grosores)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: _Grosor(
                        grosor: g,
                        elegido: g == estado.grosor,
                        alPulsar: () => lienzo.elegirGrosor(g),
                      ),
                    ),
                  const Spacer(),
                  // Solo aparece con al menos un trazo: evita toques accidentales.
                  if (!estado.vacio)
                    BotonIcono(
                      key: const Key('boton-crear'),
                      icono: Icons.auto_awesome,
                      etiqueta: '¡Crear cuento!',
                      tamano: 88,
                      alPulsar: _crear,
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Muestra extends StatelessWidget {
  const _Muestra({required this.color, required this.elegido, required this.alPulsar});

  final Color color;
  final bool elegido;
  final VoidCallback alPulsar;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: alPulsar,
      child: Container(
        width: 52,
        margin: const EdgeInsets.only(right: 8),
        decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          border: Border.all(color: elegido ? Colores.texto : Colors.white, width: elegido ? 4 : 2),
        ),
      ),
    );
  }
}

class _Grosor extends StatelessWidget {
  const _Grosor({required this.grosor, required this.elegido, required this.alPulsar});

  final double grosor;
  final bool elegido;
  final VoidCallback alPulsar;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: alPulsar,
      child: Container(
        width: kToqueMinimo,
        height: kToqueMinimo,
        decoration: BoxDecoration(
          color: elegido ? Colores.amarillo : Colors.white,
          shape: BoxShape.circle,
          border: Border.all(color: Colores.texto, width: 2),
        ),
        child: Center(
          child: Container(
            width: grosor + 4,
            height: grosor + 4,
            decoration: const BoxDecoration(color: Colores.texto, shape: BoxShape.circle),
          ),
        ),
      ),
    );
  }
}

/// Pinta el fondo blanco (nunca transparente) y cada trazo con perfect_freehand.
class PintorLienzo extends CustomPainter {
  PintorLienzo(this.estado);

  final EstadoLienzo estado;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = Colors.white);
    for (final trazo in [...estado.trazos, ?estado.actual]) {
      final contorno = getStroke(
        trazo.puntos,
        options: StrokeOptions(
          size: trazo.grosor,
          thinning: 0.6,
          smoothing: 0.5,
          streamline: 0.5,
          simulatePressure: true,
          isComplete: !identical(trazo, estado.actual),
        ),
      );
      if (contorno.isEmpty) continue;
      final path = Path()..moveTo(contorno.first.dx, contorno.first.dy);
      for (final p in contorno.skip(1)) {
        path.lineTo(p.dx, p.dy);
      }
      path.close();
      canvas.drawPath(path, Paint()..color = trazo.color);
    }
  }

  @override
  bool shouldRepaint(PintorLienzo viejo) => viejo.estado != estado;
}
