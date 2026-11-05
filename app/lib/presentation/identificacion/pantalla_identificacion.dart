import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/flujo_cuento.dart';
import '../../core/tema.dart';
import '../../domain/entidades.dart';
import '../nombre/pantalla_nombre.dart';
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

  /// Lo que el niño eligió o escribió: sigue la pregunta por el nombre, y recién ahí el cuento.
  void _elegir(String personaje) {
    if (personaje.trim().isEmpty) return;
    Navigator.of(
      context,
    ).push(MaterialPageRoute<void>(builder: (_) => PantallaNombre(personaje: personaje.trim())));
  }

  @override
  Widget build(BuildContext context) {
    final flujo = ref.watch(flujoProvider);
    final identificacion = flujo.identificacion;

    return Scaffold(
      appBar: AppBar(toolbarHeight: 64),
      body: SafeArea(
        child: switch (flujo.fase) {
          Fase.identificando => const Center(child: _Pensando()),
          _ => Column(
            children: [
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                  children: [
                    if (flujo.dibujo != null) LaminaDibujo(dibujo: flujo.dibujo!),
                    const SizedBox(height: 16),
                    MensajeIA(
                      identificacion != null && identificacion.disponible
                          ? 'Creo que dibujaste una de estas cosas. ¿Acerté? Tú sabes mejor que yo.'
                          : 'No pude ver bien tu dibujo. ¿Me cuentas qué es?',
                    ),
                    const SizedBox(height: 18),
                    if (identificacion != null && identificacion.disponible) ...[
                      Padding(
                        padding: const EdgeInsets.only(left: 4, bottom: 10),
                        child: Text(
                          'Nivel de confianza de la IA',
                          key: const Key('etiqueta-confianza'),
                          style: Tipos.subtitulo.copyWith(fontSize: 18, color: Colores.violeta),
                        ),
                      ),
                      for (final h in identificacion.hipotesis)
                        TarjetaHipotesis(hipotesis: h, alPulsar: () => _elegir(h.etiqueta)),
                    ],
                  ],
                ),
              ),
              // Fuera de la lista: los campos están siempre a la vista.
              _PanelCampo(controlador: _libre, alEnviar: () => _elegir(_libre.text)),
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

/// Mientras la IA mira el dibujo: estrellas sobre un círculo violeta, para que se vean.
class _Pensando extends StatelessWidget {
  const _Pensando();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 280,
      height: 280,
      decoration: BoxDecoration(
        color: Colores.violeta,
        shape: BoxShape.circle,
        boxShadow: sombraSuave(Colores.violeta),
      ),
      child: const Center(child: Estrellas(tamano: 220)),
    );
  }
}

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
        borderRadius: BorderRadius.circular(Radios.medio),
        side: BorderSide(color: color, width: 3),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(Radios.medio),
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
                      child: Text(hipotesis.etiqueta, style: Tipos.titulo.copyWith(fontSize: 26)),
                    ),
                    Text(
                      '${hipotesis.porcentaje} %',
                      style: Tipos.subtitulo.copyWith(fontSize: 24, color: color),
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

/// Panel inferior con el campo libre (naranja): siempre a la vista; lo que el niño escriba manda.
class _PanelCampo extends StatelessWidget {
  const _PanelCampo({required this.controlador, required this.alEnviar});

  final TextEditingController controlador;
  final VoidCallback alEnviar;

  @override
  Widget build(BuildContext context) {
    OutlineInputBorder borde(double ancho) => OutlineInputBorder(
      borderRadius: BorderRadius.circular(Radios.medio),
      borderSide: BorderSide(color: Colores.naranja, width: ancho),
    );
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(Radios.grande)),
        boxShadow: [
          BoxShadow(
            color: Colores.texto.withValues(alpha: 0.1),
            blurRadius: 12,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              key: const Key('campo-libre'),
              controller: controlador,
              maxLength: 60,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => alEnviar(),
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
              decoration: InputDecoration(
                hintText: 'Es otra cosa: escríbela',
                hintStyle: const TextStyle(fontSize: 17),
                counterText: '',
                prefixIcon: const Icon(Icons.edit, color: Colores.naranja, size: 28),
                fillColor: Colores.naranja.withValues(alpha: 0.08),
                border: borde(3),
                enabledBorder: borde(3),
                focusedBorder: borde(4),
              ),
            ),
          ),
          const SizedBox(width: 6),
          BotonIcono(
            key: const Key('boton-enviar-libre'),
            icono: Icons.check,
            etiqueta: 'Usar lo que escribí',
            tamano: kToqueMinimo,
            alPulsar: alEnviar,
          ),
        ],
      ),
    );
  }
}
