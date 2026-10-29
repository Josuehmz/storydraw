import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../core/tema.dart';

/// Botón redondo solo con icono, grande, para el niño. Se siente «de bulto»: borde
/// blanco, sombra suave del mismo color y un pequeño rebote al pulsarlo.
class BotonIcono extends StatefulWidget {
  const BotonIcono({
    super.key,
    required this.icono,
    required this.alPulsar,
    required this.etiqueta,
    this.color = Colores.naranja,
    this.tamano = 72,
  });

  final IconData icono;
  final VoidCallback? alPulsar;

  /// Para lectores de pantalla; no se muestra.
  final String etiqueta;
  final Color color;

  /// Tamaño visual. El área que se toca nunca baja de [kToqueMinimo].
  final double tamano;

  @override
  State<BotonIcono> createState() => _BotonIconoState();
}

class _BotonIconoState extends State<BotonIcono> {
  bool _presionado = false;

  @override
  Widget build(BuildContext context) {
    final activo = widget.alPulsar != null;
    final lado = widget.tamano < kToqueMinimo ? kToqueMinimo : widget.tamano;
    final color = activo ? widget.color : Colors.grey.shade300;
    return Semantics(
      button: true,
      enabled: activo,
      label: widget.etiqueta,
      child: SizedBox(
        width: lado,
        height: lado,
        child: Center(
          child: AnimatedScale(
            scale: _presionado ? 0.92 : 1,
            duration: const Duration(milliseconds: 90),
            child: Container(
              width: widget.tamano,
              height: widget.tamano,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: color,
                border: Border.all(color: Colors.white, width: widget.tamano >= 80 ? 4 : 3),
                boxShadow: activo ? sombraSuave(widget.color) : null,
              ),
              child: Material(
                type: MaterialType.transparency,
                shape: const CircleBorder(),
                child: InkWell(
                  customBorder: const CircleBorder(),
                  onTap: widget.alPulsar,
                  onHighlightChanged: (v) => setState(() => _presionado = v),
                  child: Icon(widget.icono, color: Colors.white, size: widget.tamano * 0.5),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Bloque violeta: la voz de la máquina, en primera persona y con duda.
class MensajeIA extends StatelessWidget {
  const MensajeIA(this.texto, {super.key});

  final String texto;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('mensaje-ia'),
      padding: const EdgeInsets.fromLTRB(14, 14, 18, 14),
      decoration: BoxDecoration(
        color: Colores.violeta,
        borderRadius: BorderRadius.circular(Radios.grande),
        boxShadow: sombraSuave(Colores.violeta),
      ),
      child: Row(
        children: [
          Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white.withValues(alpha: 0.22),
            ),
            child: const Icon(Icons.auto_awesome, color: Colores.amarillo, size: 32),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              texto,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 19,
                height: 1.3,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Aviso de información (no de error): icono de información y fondo azul claro.
class AvisoInfo extends StatelessWidget {
  const AvisoInfo({super.key, required this.texto, this.accion});

  final String texto;
  final Widget? accion;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colores.azulInfo.withValues(alpha: 0.1),
        border: Border.all(color: Colores.azulInfo, width: 2),
        borderRadius: BorderRadius.circular(Radios.medio),
      ),
      child: Row(
        children: [
          const Icon(Icons.info_outline, color: Colores.azulInfo, size: 32),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Información importante',
                  style: TextStyle(
                    fontFamily: 'Fredoka',
                    fontSize: 17,
                    fontWeight: FontWeight.w600,
                    color: Colores.azulInfo,
                  ),
                ),
                Text(texto, style: const TextStyle(fontSize: 16)),
              ],
            ),
          ),
          ?accion,
        ],
      ),
    );
  }
}

/// El dibujo del niño, enmarcado como una lámina: borde amarillo, sombra y esquinas suaves.
class LaminaDibujo extends StatelessWidget {
  const LaminaDibujo({super.key, required this.dibujo});

  final Uint8List dibujo;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(Radios.medio),
          border: Border.all(color: Colores.amarillo, width: 4),
          boxShadow: sombraSuave(),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(Radios.chico - 2),
          child: Image.memory(dibujo, height: 120),
        ),
      ),
    );
  }
}
