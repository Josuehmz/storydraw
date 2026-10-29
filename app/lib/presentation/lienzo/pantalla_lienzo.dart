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
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: Row(
                children: [
                  BotonIcono(
                    key: const Key('boton-perfil'),
                    icono: Icons.face,
                    etiqueta: 'Cambiar de niño: ${perfil?.apodo ?? ''}',
                    color: Colores.violeta,
                    tamano: kToqueMinimo,
                    alPulsar: () => ref.read(sesionProvider.notifier).cambiarPerfil(),
                  ),
                  const Spacer(),
                  BotonIcono(
                    key: const Key('boton-deshacer'),
                    icono: Icons.undo,
                    etiqueta: 'Deshacer',
                    color: Colores.azulInfo,
                    tamano: kToqueMinimo,
                    alPulsar: estado.trazos.isEmpty ? null : lienzo.deshacer,
                  ),
                  const SizedBox(width: 4),
                  BotonIcono(
                    key: const Key('boton-limpiar'),
                    icono: Icons.delete_sweep,
                    etiqueta: 'Borrar todo',
                    color: Colores.rojo,
                    tamano: kToqueMinimo,
                    alPulsar: estado.vacio ? null : lienzo.limpiar,
                  ),
                  const SizedBox(width: 4),
                  BotonIcono(
                    key: const Key('boton-biblioteca'),
                    icono: Icons.collections_bookmark,
                    etiqueta: 'Mis cuentos',
                    color: Colores.verde,
                    tamano: kToqueMinimo,
                    alPulsar: () => Navigator.of(
                      context,
                    ).push(MaterialPageRoute<void>(builder: (_) => const PantallaBiblioteca())),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                child: Container(
                  // Marco de «hoja de papel»: borde de color, sombra y esquinas redondas.
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(Radios.grande),
                    border: Border.all(color: Colores.amarillo, width: 5),
                    boxShadow: sombraSuave(),
                  ),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(Radios.grande - 5),
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        RepaintBoundary(
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
                        // Encima y fuera del RepaintBoundary: nunca entra en el dibujo exportado.
                        if (estado.vacio) const Positioned.fill(child: _PistaLienzoVacio()),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            _Bandeja(
              child: SizedBox(
                height: 60,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
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
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
              child: Row(
                children: [
                  _Bandeja(
                    margen: EdgeInsets.zero,
                    child: Padding(
                      padding: const EdgeInsets.all(6),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          for (final g in _grosores)
                            _Grosor(
                              grosor: g,
                              elegido: g == estado.grosor,
                              alPulsar: () => lienzo.elegirGrosor(g),
                            ),
                        ],
                      ),
                    ),
                  ),
                  const Spacer(),
                  // El espacio está reservado: el botón aparece sin mover nada. Solo se
                  // muestra con al menos un trazo, para evitar toques accidentales.
                  SizedBox(
                    width: 104,
                    height: 104,
                    child: estado.vacio
                        ? null
                        : _Latido(
                            child: BotonIcono(
                              key: const Key('boton-crear'),
                              icono: Icons.auto_awesome,
                              etiqueta: '¡Crear cuento!',
                              tamano: 96,
                              alPulsar: _crear,
                            ),
                          ),
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

/// Bandeja blanca y redondeada donde descansan los colores y los grosores.
class _Bandeja extends StatelessWidget {
  const _Bandeja({required this.child, this.margen = const EdgeInsets.symmetric(horizontal: 12)});

  final Widget child;
  final EdgeInsets margen;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: margen,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(Radios.grande),
        boxShadow: sombraSuave(),
      ),
      child: child,
    );
  }
}

/// Pista sin texto en el lienzo vacío: un dedo sobre un garabato punteado = «dibuja aquí».
/// No recibe toques (IgnorePointer) y desaparece con el primer trazo.
class _PistaLienzoVacio extends StatelessWidget {
  const _PistaLienzoVacio();

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Center(
        key: const Key('pista-lienzo'),
        child: SizedBox(
          width: 220,
          height: 180,
          child: Stack(
            children: [
              Positioned.fill(child: CustomPaint(painter: _GarabatoPunteado())),
              const Positioned(
                right: 18,
                bottom: 4,
                child: Icon(Icons.touch_app, size: 96, color: Colores.naranja),
              ),
              Positioned(
                left: 6,
                top: 0,
                child: Icon(Icons.brush, size: 56, color: Colores.azul.withValues(alpha: 0.8)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GarabatoPunteado extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final pintura = Paint()
      ..color = Colores.azul.withValues(alpha: 0.55)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.round;
    final camino = Path()
      ..moveTo(size.width * 0.12, size.height * 0.62)
      ..cubicTo(
        size.width * 0.3,
        size.height * 0.2,
        size.width * 0.45,
        size.height * 0.95,
        size.width * 0.62,
        size.height * 0.55,
      )
      ..cubicTo(
        size.width * 0.72,
        size.height * 0.3,
        size.width * 0.8,
        size.height * 0.35,
        size.width * 0.84,
        size.height * 0.5,
      );
    // Raya punteada: tramos de 14 px con huecos de 12 px.
    for (final metrica in camino.computeMetrics()) {
      for (var d = 0.0; d < metrica.length; d += 26) {
        canvas.drawPath(metrica.extractPath(d, d + 14), pintura);
      }
    }
  }

  @override
  bool shouldRepaint(_GarabatoPunteado viejo) => false;
}

/// Latido suave del botón de crear: llama la atención sin ser molesto. Se apaga si el
/// sistema pide menos animaciones.
class _Latido extends StatefulWidget {
  const _Latido({required this.child});

  final Widget child;

  @override
  State<_Latido> createState() => _LatidoState();
}

class _LatidoState extends State<_Latido> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.disableAnimationsOf(context)) {
      _c.stop();
    } else if (!_c.isAnimating) {
      _c.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ScaleTransition(
      scale: Tween(
        begin: 0.95,
        end: 1.05,
      ).animate(CurvedAnimation(parent: _c, curve: Curves.easeInOut)),
      child: widget.child,
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
      child: Center(
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 140),
          width: elegido ? 52 : 42,
          height: elegido ? 52 : 42,
          margin: const EdgeInsets.symmetric(horizontal: 5),
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
            border: Border.all(
              color: elegido ? Colores.texto : Colors.white,
              width: elegido ? 4 : 3,
            ),
            boxShadow: [
              BoxShadow(
                color: color.withValues(alpha: 0.4),
                blurRadius: elegido ? 8 : 4,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          child: elegido ? const Icon(Icons.check, color: Colors.white, size: 26) : null,
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
        width: kToqueMinimo - 8,
        height: kToqueMinimo - 8,
        margin: const EdgeInsets.symmetric(horizontal: 3),
        decoration: BoxDecoration(
          color: elegido ? Colores.amarillo : Colores.crema,
          shape: BoxShape.circle,
          border: Border.all(color: elegido ? Colores.naranja : Colors.transparent, width: 3),
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
