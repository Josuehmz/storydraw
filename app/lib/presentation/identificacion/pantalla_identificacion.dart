import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/flujo_cuento.dart';
import '../../core/tema.dart';
import '../../domain/entidades.dart';
import '../momento_magico/pantalla_momento_magico.dart';
import '../widgets/comunes.dart';
import '../widgets/estrellas.dart';

/// Identificación asistida: la IA propone con su confianza; el niño decide.
/// El campo libre está siempre visible y lo que el niño escriba manda.
class PantallaIdentificacion extends ConsumerStatefulWidget {
  const PantallaIdentificacion({super.key});

  @override
  ConsumerState<PantallaIdentificacion> createState() => _PantallaIdentificacionState();
}

class _PantallaIdentificacionState extends ConsumerState<PantallaIdentificacion> {
  final _libre = TextEditingController();

  @override
  void dispose() {
    _libre.dispose();
    super.dispose();
  }

  void _elegir(String personaje) {
    if (personaje.trim().isEmpty) return;
    ref.read(flujoProvider.notifier).crear(personaje.trim());
    Navigator.of(
      context,
    ).pushReplacement(MaterialPageRoute<void>(builder: (_) => const PantallaMomentoMagico()));
  }

  @override
  Widget build(BuildContext context) {
    final flujo = ref.watch(flujoProvider);
    final identificacion = flujo.identificacion;

    return Scaffold(
      appBar: AppBar(backgroundColor: Colores.crema, toolbarHeight: 72),
      body: SafeArea(
        child: switch (flujo.fase) {
          Fase.identificando => const Center(child: Estrellas(tamano: 220)),
          _ => Column(
            children: [
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    if (flujo.dibujo != null)
                      Center(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(16),
                          child: Image.memory(flujo.dibujo!, height: 120),
                        ),
                      ),
                    const SizedBox(height: 16),
                    MensajeIA(
                      identificacion != null && identificacion.disponible
                          ? 'Creo que dibujaste una de estas cosas. ¿Acerté? Tú sabes mejor que yo.'
                          : 'No pude ver bien tu dibujo. ¿Me cuentas qué es?',
                    ),
                    const SizedBox(height: 16),
                    if (identificacion != null && identificacion.disponible) ...[
                      const Text(
                        'Nivel de confianza de la IA',
                        key: Key('etiqueta-confianza'),
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 8),
                      for (final h in identificacion.hipotesis)
                        TarjetaHipotesis(hipotesis: h, alPulsar: () => _elegir(h.etiqueta)),
                    ],
                  ],
                ),
              ),
              // Fuera de la lista: el campo libre está siempre a la vista.
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: _CampoLibre(controlador: _libre, alEnviar: () => _elegir(_libre.text)),
              ),
            ],
          ),
        },
      ),
    );
  }
}

Color colorDeNivel(NivelConfianza n) => switch (n) {
  NivelConfianza.alta => Colores.verde,
  NivelConfianza.media => Colores.ambar,
  NivelConfianza.baja => Colores.rojo,
};

/// Una hipótesis: su confianza como número y como barra proporcional, con color.
class TarjetaHipotesis extends StatelessWidget {
  const TarjetaHipotesis({super.key, required this.hipotesis, required this.alPulsar});

  final Hipotesis hipotesis;
  final VoidCallback alPulsar;

  @override
  Widget build(BuildContext context) {
    final color = colorDeNivel(hipotesis.nivel);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(color: color, width: 3),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: alPulsar,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kToqueMinimo + 16),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        hipotesis.etiqueta,
                        style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800),
                      ),
                    ),
                    Text(
                      '${hipotesis.porcentaje} %',
                      style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: color),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: SizedBox(
                    height: 14,
                    child: Stack(
                      children: [
                        Container(color: color.withValues(alpha: 0.18)),
                        FractionallySizedBox(
                          widthFactor: hipotesis.confianza.clamp(0.0, 1.0),
                          child: Container(color: color),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CampoLibre extends StatelessWidget {
  const _CampoLibre({required this.controlador, required this.alEnviar});

  final TextEditingController controlador;
  final VoidCallback alEnviar;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colores.naranja.withValues(alpha: 0.12),
        border: Border.all(color: Colores.naranja, width: 3),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        children: [
          const Icon(Icons.edit, color: Colores.naranja, size: 32),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              key: const Key('campo-libre'),
              controller: controlador,
              maxLength: 60,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => alEnviar(),
              style: const TextStyle(fontSize: 22),
              decoration: const InputDecoration(
                hintText: 'Es otra cosa: escribe qué es',
                counterText: '',
                border: InputBorder.none,
              ),
            ),
          ),
          BotonIcono(
            key: const Key('boton-enviar-libre'),
            icono: Icons.check,
            etiqueta: 'Usar lo que escribí',
            tamano: 64,
            alPulsar: alEnviar,
          ),
        ],
      ),
    );
  }
}
