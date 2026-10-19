import 'package:flutter/material.dart';

import '../../core/tema.dart';

/// Botón redondo solo con icono, grande, para el niño.
class BotonIcono extends StatelessWidget {
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
  final double tamano;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: etiqueta,
      child: SizedBox(
        width: tamano,
        height: tamano,
        child: Material(
          color: alPulsar == null ? Colors.grey.shade300 : color,
          shape: const CircleBorder(),
          elevation: 3,
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: alPulsar,
            child: Icon(icono, color: Colors.white, size: tamano * 0.5),
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
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: Colores.violeta, borderRadius: BorderRadius.circular(20)),
      child: Row(
        children: [
          const Icon(Icons.auto_awesome, color: Colors.white, size: 36),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              texto,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 19,
                fontWeight: FontWeight.w600,
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
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colores.azulInfo.withValues(alpha: 0.12),
        border: Border.all(color: Colores.azulInfo, width: 2),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          const Icon(Icons.info_outline, color: Colores.azulInfo, size: 32),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Información importante',
                  style: TextStyle(fontWeight: FontWeight.w800, color: Colores.azulInfo),
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
