import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/flujo_cuento.dart';
import '../../application/lienzo.dart';
import '../../application/proveedores.dart';
import '../../core/tema.dart';
import '../../domain/entidades.dart';
import '../../domain/repositorios.dart';
import '../identificacion/pantalla_identificacion.dart';
import '../widgets/comunes.dart';

/// Visor del cuento: una página a la vez, con botones grandes (sin gestos de
/// deslizar) y narración por página.
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
  bool _sonando = false;
  bool _reintentando = false;
  StreamSubscription<bool>? _sub;
  late final Reproductor _reproductor;

  Cuento? get _cuento => widget.desdeFlujo ? ref.read(flujoProvider).cuento : widget.cuento;

  @override
  void initState() {
    super.initState();
    _reproductor = ref.read(reproductorProvider);
    _sub = _reproductor.reproduciendo.listen((v) {
      if (mounted) setState(() => _sonando = v);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _narrar());
  }

  @override
  void dispose() {
    _sub?.cancel();
    unawaited(_reproductor.detener());
    super.dispose();
  }

  Future<void> _narrar() async {
    final audio = _cuento?.paginas.elementAtOrNull(_pagina)?.audio;
    if (audio != null) await _reproductor.reproducir(audio);
  }

  Future<void> _irA(int pagina) async {
    await _reproductor.detener();
    setState(() => _pagina = pagina);
    await _narrar();
  }

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

  Future<void> _reintentarVoz() async {
    setState(() => _reintentando = true);
    await ref.read(flujoProvider.notifier).reintentarNarracion();
    if (!mounted) return;
    setState(() => _reintentando = false);
    await _narrar();
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
              padding: const EdgeInsets.all(8),
              child: Row(
                children: [
                  BotonIcono(
                    key: const Key('boton-inicio'),
                    icono: Icons.home,
                    etiqueta: 'Volver a dibujar',
                    color: Colores.verde,
                    tamano: 56,
                    alPulsar: _alInicio,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      cuento.titulo ?? '',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
                    ),
                  ),
                  if (pagina.audio != null)
                    BotonIcono(
                      key: const Key('boton-narrar'),
                      icono: _sonando ? Icons.stop : Icons.volume_up,
                      etiqueta: _sonando ? 'Parar' : 'Escuchar',
                      color: Colores.violeta,
                      tamano: 64,
                      alPulsar: _sonando ? () => _reproductor.detener() : _narrar,
                    ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                children: [
                  Center(
                    child: ConstrainedBox(
                      // La imagen no empuja el texto fuera de la pantalla.
                      constraints: BoxConstraints(
                        maxHeight: MediaQuery.sizeOf(context).height * 0.45,
                      ),
                      child: AspectRatio(
                        aspectRatio: 1,
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(24),
                          child: pagina.imagen != null
                              ? Image.memory(pagina.imagen!, fit: BoxFit.cover)
                              : const ColoredBox(
                                  color: Colores.amarillo,
                                  child: Icon(Icons.image, size: 96, color: Colors.white),
                                ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    pagina.texto,
                    key: const Key('texto-pagina'),
                    style: const TextStyle(fontSize: 22, height: 1.5, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 12),
                  if (cuento.sinNarracion)
                    AvisoInfo(
                      key: const Key('aviso-sin-voz'),
                      texto: 'Este cuento llegó sin voz. Puedes pedirla otra vez.',
                      accion: widget.desdeFlujo
                          ? (_reintentando
                                ? const SizedBox.square(
                                    dimension: kToqueMinimo,
                                    child: Center(child: CircularProgressIndicator()),
                                  )
                                : BotonIcono(
                                    key: const Key('boton-reintentar-voz'),
                                    icono: Icons.record_voice_over,
                                    etiqueta: 'Pedir la voz otra vez',
                                    color: Colores.azulInfo,
                                    tamano: 64,
                                    alPulsar: _reintentarVoz,
                                  ))
                          : null,
                    ),
                  if (cuento.avisos.contains(Avisos.sinEscenarios))
                    const Padding(
                      padding: EdgeInsets.only(top: 8),
                      child: AvisoInfo(
                        key: Key('aviso-sin-escenarios'),
                        texto: 'Algunos fondos son de nuestro banco de paisajes.',
                      ),
                    ),
                  if (widget.desdeFlujo) ...[
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      key: const Key('boton-no-era-asi'),
                      onPressed: _noEraAsi,
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colores.naranja,
                        side: const BorderSide(color: Colores.naranja, width: 3),
                        minimumSize: const Size.fromHeight(kToqueMinimo),
                      ),
                      icon: const Icon(Icons.replay, size: 32),
                      label: const Text(
                        'No era así: cambiar lo que dibujé',
                        style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  BotonIcono(
                    key: const Key('boton-anterior'),
                    icono: Icons.arrow_back,
                    etiqueta: 'Página anterior',
                    alPulsar: _pagina == 0 ? null : () => _irA(_pagina - 1),
                  ),
                  Row(
                    children: [
                      for (var i = 0; i < cuento.paginas.length; i++)
                        Container(
                          margin: const EdgeInsets.all(4),
                          width: 16,
                          height: 16,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: i == _pagina ? Colores.naranja : Colors.grey.shade300,
                          ),
                        ),
                    ],
                  ),
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
