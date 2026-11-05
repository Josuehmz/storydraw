import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/flujo_cuento.dart';
import '../../application/lienzo.dart';
import '../../application/proveedores.dart';
import '../../core/errores.dart';
import '../../core/tema.dart';
import '../cuento/pantalla_cuento.dart';
import '../widgets/comunes.dart';
import '../widgets/estrellas.dart';

/// Momento mágico: la pantalla de espera mientras el backend arma el cuento.
class PantallaMomentoMagico extends ConsumerWidget {
  const PantallaMomentoMagico({super.key});

  void _volverAlLienzo(BuildContext context, WidgetRef ref) {
    ref.read(flujoProvider.notifier).reiniciar();
    ref.read(lienzoProvider.notifier).limpiar();
    Navigator.of(context).popUntil((r) => r.isFirst);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen<EstadoFlujo>(flujoProvider, (_, siguiente) {
      if (siguiente.fase == Fase.listo && siguiente.cuento != null) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute<void>(builder: (_) => const PantallaCuento(desdeFlujo: true)),
        );
      }
    });
    final flujo = ref.watch(flujoProvider);

    return Scaffold(
      backgroundColor: Colores.violeta,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: switch (flujo.fase) {
            Fase.rechazado => _Final(
              icono: Icons.palette,
              texto: 'Esta vez no me salió un buen cuento. ¡Probemos con otro dibujo!',
              acciones: [
                BotonIcono(
                  key: const Key('boton-dibujar-otra-vez'),
                  icono: Icons.brush,
                  etiqueta: 'Dibujar otra vez',
                  tamano: 96,
                  alPulsar: () => _volverAlLienzo(context, ref),
                ),
              ],
            ),
            Fase.error => _Final(
              icono: flujo.error == TipoError.sinConexion ? Icons.wifi_off : Icons.cloud_off,
              texto: flujo.error == TipoError.limite
                  ? '¡Eres un gran cuentista! Descansa un ratito y vuelve a crear.'
                  : 'La magia se tomó un descanso. ¿Lo intentamos otra vez?',
              acciones: [
                if (flujo.error != TipoError.limite)
                  BotonIcono(
                    key: const Key('boton-reintentar'),
                    icono: Icons.refresh,
                    etiqueta: 'Intentar otra vez',
                    tamano: 96,
                    alPulsar: () => ref
                        .read(flujoProvider.notifier)
                        .crear(flujo.personaje ?? '', nombre: flujo.nombre),
                  ),
                BotonIcono(
                  icono: Icons.home,
                  etiqueta: 'Volver a dibujar',
                  color: Colores.verde,
                  tamano: 96,
                  alPulsar: () => _volverAlLienzo(context, ref),
                ),
              ],
            ),
            // Con desplazamiento: el aviso de demora suma una fila y en un teléfono chico
            // no debe empujar el contenido fuera de la pantalla.
            _ => Center(
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Estrellas(),
                    const SizedBox(height: 24),
                    MensajeIA(
                      'Estoy creando un cuento sobre «${flujo.personaje ?? 'tu dibujo'}», '
                      'como tú me dijiste. Tu dibujo será el protagonista.',
                    ),
                    const SizedBox(height: 16),
                    const _Nota(
                      icono: Icons.shield,
                      texto: 'Un filtro revisa cada cuento antes de que lo veas.',
                    ),
                    const SizedBox(height: 8),
                    const _Nota(
                      icono: Icons.collections_bookmark,
                      texto: 'Puedes salir: el cuento te esperará en tu biblioteca.',
                    ),
                    const AvisoDemora(),
                  ],
                ),
              ),
            ),
          },
        ),
      ),
    );
  }
}

const textoAvisoDemora = 'Está tardando un poco más de lo normal…';

/// Aparece si el cuento pasa de `AppConfig.avisoDemora` (60 s). Para el niño que no lee,
/// el aviso es sobre todo visual: un reloj de arena que gira en un círculo amarillo.
class AvisoDemora extends ConsumerStatefulWidget {
  const AvisoDemora({super.key});

  @override
  ConsumerState<AvisoDemora> createState() => _AvisoDemoraState();
}

class _AvisoDemoraState extends ConsumerState<AvisoDemora> with SingleTickerProviderStateMixin {
  Timer? _temporizador;
  bool _visible = false;
  late final AnimationController _giro;

  @override
  void initState() {
    super.initState();
    _giro = AnimationController(vsync: this, duration: const Duration(seconds: 2));
    _temporizador = Timer(ref.read(configProvider).avisoDemora, () {
      if (!mounted) return;
      setState(() => _visible = true);
      _giro.repeat();
    });
  }

  @override
  void dispose() {
    _temporizador?.cancel();
    _giro.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_visible) return const SizedBox.shrink();
    return Semantics(
      key: const Key('aviso-demora'),
      label: textoAvisoDemora,
      child: Padding(
        padding: const EdgeInsets.only(top: 16),
        child: Row(
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: const BoxDecoration(color: Colores.amarillo, shape: BoxShape.circle),
              child: RotationTransition(
                turns: _giro,
                child: const Icon(Icons.hourglass_bottom, size: 40, color: Colores.violeta),
              ),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: ExcludeSemantics(
                child: Text(
                  textoAvisoDemora,
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Nota extends StatelessWidget {
  const _Nota({required this.icono, required this.texto});

  final IconData icono;
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icono, color: Colores.amarillo, size: 28),
        const SizedBox(width: 10),
        Expanded(
          child: Text(texto, style: const TextStyle(color: Colors.white, fontSize: 16)),
        ),
      ],
    );
  }
}

class _Final extends StatelessWidget {
  const _Final({required this.icono, required this.texto, required this.acciones});

  final IconData icono;
  final String texto;
  final List<Widget> acciones;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(icono, size: 120, color: Colores.amarillo),
        const SizedBox(height: 24),
        Text(
          texto,
          textAlign: TextAlign.center,
          style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 32),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            for (final a in acciones) Padding(padding: const EdgeInsets.all(12), child: a),
          ],
        ),
      ],
    );
  }
}
