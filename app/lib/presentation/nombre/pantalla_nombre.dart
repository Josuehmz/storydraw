import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/flujo_cuento.dart';
import '../../core/tema.dart';
import '../momento_magico/pantalla_momento_magico.dart';
import '../widgets/comunes.dart';

/// Lo que dibujó, sin el artículo: «un pez» → «pez», «una caja» → «caja». Así la pregunta
/// suena natural: «¿Cuál es el nombre de tu pez?».
String sustantivoDe(String personaje) {
  final limpio = personaje.trim();
  final sinArticulo = limpio.replaceFirst(
    RegExp(r'^(un|una|unos|unas|el|la|los|las)\s+', caseSensitive: false),
    '',
  );
  return sinArticulo.isEmpty ? limpio : sinArticulo;
}

/// Tercer paso del flujo: el niño ya dijo qué dibujó; ahora le pone nombre y pide el cuento.
/// El nombre es opcional: si lo deja vacío, el cuento llama al personaje por lo que es.
class PantallaNombre extends ConsumerStatefulWidget {
  const PantallaNombre({super.key, required this.personaje});

  /// Lo que el niño eligió o escribió en el paso anterior.
  final String personaje;

  @override
  ConsumerState<PantallaNombre> createState() => _PantallaNombreState();
}

class _PantallaNombreState extends ConsumerState<PantallaNombre> {
  // Si vuelve desde «No era así», el nombre anterior ya está escrito.
  late final _nombre = TextEditingController(text: ref.read(flujoProvider).nombre);

  @override
  void dispose() {
    _nombre.dispose();
    super.dispose();
  }

  void _verCuento() {
    ref.read(flujoProvider.notifier).crear(widget.personaje, nombre: _nombre.text.trim());
    // Se queda solo el lienzo debajo: atrás desde la espera no vuelve a las preguntas.
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(builder: (_) => const PantallaMomentoMagico()),
      (r) => r.isFirst,
    );
  }

  @override
  Widget build(BuildContext context) {
    final dibujo = ref.watch(flujoProvider).dibujo;
    final cosa = sustantivoDe(widget.personaje);

    return Scaffold(
      appBar: AppBar(toolbarHeight: 64),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                children: [
                  if (dibujo != null) LaminaDibujo(dibujo: dibujo),
                  const SizedBox(height: 18),
                  MensajeIA('¿Cuál es el nombre de tu $cosa?'),
                  const SizedBox(height: 18),
                  TextField(
                    key: const Key('campo-nombre'),
                    controller: _nombre,
                    autofocus: true,
                    maxLength: 30,
                    textCapitalization: TextCapitalization.words,
                    textInputAction: TextInputAction.done,
                    onSubmitted: (_) => _verCuento(),
                    style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700),
                    decoration: InputDecoration(
                      hintText: 'Escribe su nombre',
                      counterText: '',
                      prefixIcon: const Icon(Icons.favorite, color: Colores.verde, size: 30),
                      fillColor: Colores.verde.withValues(alpha: 0.08),
                      border: _borde(3),
                      enabledBorder: _borde(3),
                      focusedBorder: _borde(4),
                    ),
                  ),
                ],
              ),
            ),
            Container(
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
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  key: const Key('boton-ver-cuento'),
                  onPressed: _verCuento,
                  icon: const Icon(Icons.auto_stories, size: 30),
                  label: const Text('Ver cuento'),
                  style: ElevatedButton.styleFrom(
                    minimumSize: const Size.fromHeight(72),
                    textStyle: Tipos.boton.copyWith(fontSize: 24),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static OutlineInputBorder _borde(double ancho) => OutlineInputBorder(
    borderRadius: BorderRadius.circular(Radios.medio),
    borderSide: BorderSide(color: Colores.verde, width: ancho),
  );
}
