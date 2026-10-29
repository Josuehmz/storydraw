import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/flujo_cuento.dart';
import '../../application/lienzo.dart';
import '../../core/tema.dart';
import '../../domain/entidades.dart';
import '../identificacion/pantalla_identificacion.dart';
import '../widgets/comunes.dart';

/// Visor del cuento: una página a la vez, con botones grandes (sin gestos de
/// deslizar). El cuento sale sin narración: se lee en pantalla.
class PantallaCuento extends ConsumerStatefulWidget {
  const PantallaCuento({super.key, this.cuento, this.desdeFlujo = false})
    : assert(cuento != null || desdeFlujo);

  /// Cuento de la biblioteca. Si `desdeFlujo`, se lee del flujo activo.
  final Cuento? cuento;
  final bool desdeFlujo;

  @override
  ConsumerState<PantallaCuento> createState() => _PantallaCuentoState();
}

class _PantallaCuentoState extends ConsumerState<PantallaCuento> {
  int _pagina = 0;

  void _irA(int pagina) => setState(() => _pagina = pagina);

  void _alInicio() {
    ref.read(flujoProvider.notifier).reiniciar();
    ref.read(lienzoProvider.notifier).limpiar();
    Navigator.of(context).popUntil((r) => r.isFirst);
  }

  void _noEraAsi() {
    ref.read(flujoProvider.notifier).noEraAsi();
    Navigator.of(
      context,
    ).pushReplacement(MaterialPageRoute<void>(builder: (_) => const PantallaIdentificacion()));
  }

  @override
  Widget build(BuildContext context) {
    final cuento = widget.desdeFlujo ? ref.watch(flujoProvider).cuento : widget.cuento;
    if (cuento == null || cuento.paginas.isEmpty) {
      return const Scaffold(body: Center(child: Icon(Icons.menu_book, size: 96)));
    }
    final pagina = cuento.paginas[_pagina.clamp(0, cuento.paginas.length - 1)];
    final ultima = _pagina >= cuento.paginas.length - 1;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: Row(
                children: [
                  BotonIcono(
                    key: const Key('boton-inicio'),
                    icono: Icons.home,
                    etiqueta: 'Volver a dibujar',
                    color: Colores.verde,
                    tamano: kToqueMinimo,
                    alPulsar: _alInicio,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      cuento.titulo ?? '',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Tipos.titulo.copyWith(fontSize: 24, height: 1.1),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                children: [
                  // Al cambiar de página, la nueva entra con un fundido y un leve ascenso.
                  TweenAnimationBuilder<double>(
                    key: ValueKey(_pagina),
                    tween: Tween(begin: 0, end: 1),
                    duration: const Duration(milliseconds: 320),
                    curve: Curves.easeOutCubic,
                    builder: (_, t, hijo) => Opacity(
                      opacity: t,
                      child: Transform.translate(offset: Offset(0, 16 * (1 - t)), child: hijo),
                    ),
                    child: Column(
                      children: [
                        Center(
                          child: ConstrainedBox(
                            // La imagen no empuja el texto fuera de la pantalla.
                            constraints: BoxConstraints(
                              maxHeight: MediaQuery.sizeOf(context).height * 0.36,
                            ),
                            child: AspectRatio(
                              aspectRatio: 1,
                              child: _MarcoIlustracion(imagen: pagina.imagen),
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),
                        _HojaDeTexto(texto: pagina.texto),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  if (cuento.avisos.contains(Avisos.sinEscenarios))
                    const AvisoInfo(
                      key: Key('aviso-sin-escenarios'),
                      texto: 'Algunos fondos son de nuestro banco de paisajes.',
                    ),
                  if (widget.desdeFlujo) ...[
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      key: const Key('boton-no-era-asi'),
                      onPressed: _noEraAsi,
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size.fromHeight(kToqueMinimo),
                        textStyle: Tipos.boton.copyWith(fontSize: 18),
                      ),
                      icon: const Icon(Icons.replay, size: 28),
                      label: const Text('No era así: cambiar lo que dibujé'),
                    ),
                  ],
                  const SizedBox(height: 16),
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
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
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  BotonIcono(
                    key: const Key('boton-anterior'),
                    icono: Icons.arrow_back,
                    etiqueta: 'Página anterior',
                    alPulsar: _pagina == 0 ? null : () => _irA(_pagina - 1),
                  ),
                  _PuntosDePagina(total: cuento.paginas.length, actual: _pagina),
                  ultima
                      ? BotonIcono(
                          key: const Key('boton-fin'),
                          icono: Icons.celebration,
                          etiqueta: '¡Fin! Volver a dibujar',
                          color: Colores.verde,
                          alPulsar: _alInicio,
                        )
                      : BotonIcono(
                          key: const Key('boton-siguiente'),
                          icono: Icons.arrow_forward,
                          etiqueta: 'Página siguiente',
                          alPulsar: () => _irA(_pagina + 1),
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

/// La ilustración como una lámina de libro: borde blanco grueso, sombra y esquinas suaves.
class _MarcoIlustracion extends StatelessWidget {
  const _MarcoIlustracion({required this.imagen});

  final Uint8List? imagen;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(Radios.grande),
        boxShadow: sombraSuave(),
      ),
      padding: const EdgeInsets.all(6),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(Radios.grande - 6),
        child: imagen != null
            ? Image.memory(imagen!, fit: BoxFit.cover)
            : const ColoredBox(
                color: Colores.amarillo,
                child: Icon(Icons.image, size: 96, color: Colors.white),
              ),
      ),
    );
  }
}

/// El texto de la página sobre una hoja de papel cálida, con buena lectura.
class _HojaDeTexto extends StatelessWidget {
  const _HojaDeTexto({required this.texto});

  final String texto;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(Radios.grande),
        border: Border.all(color: Colores.amarillo.withValues(alpha: 0.6), width: 3),
      ),
      child: Text(
        texto,
        key: const Key('texto-pagina'),
        style: const TextStyle(fontSize: 22, height: 1.55, fontWeight: FontWeight.w600),
      ),
    );
  }
}

/// Un punto por página; la actual se alarga y toma el color de acción.
class _PuntosDePagina extends StatelessWidget {
  const _PuntosDePagina({required this.total, required this.actual});

  final int total;
  final int actual;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var i = 0; i < total; i++)
          AnimatedContainer(
            duration: const Duration(milliseconds: 220),
            margin: const EdgeInsets.symmetric(horizontal: 4),
            width: i == actual ? 30 : 14,
            height: 14,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(7),
              color: i == actual ? Colores.naranja : Colores.amarillo.withValues(alpha: 0.55),
            ),
          ),
      ],
    );
  }
}
