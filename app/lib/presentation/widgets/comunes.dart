import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/proveedores.dart';
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

/// Texto del aviso del modo invitado (solo pruebas locales).
const textoAvisoInvitado = 'Modo invitado: tus cuentos se guardan solo en este dispositivo';

/// Franja del modo invitado. Solo se ve si se entró como invitado.
class AvisoInvitado extends ConsumerWidget {
  const AvisoInvitado({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (!ref.watch(sesionProvider.select((s) => s.invitado))) return const SizedBox.shrink();
    return Container(
      key: const Key('aviso-invitado'),
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Colores.azul.withValues(alpha: 0.12),
        border: Border.all(color: Colores.azul, width: 2),
        borderRadius: BorderRadius.circular(16),
      ),
      child: const Row(
        children: [
          Icon(Icons.phone_android, color: Colores.azul, size: 28),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              textoAvisoInvitado,
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: Colores.texto),
            ),
          ),
        ],
      ),
    );
  }
}
