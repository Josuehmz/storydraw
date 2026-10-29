import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/proveedores.dart';
import '../../core/tema.dart';
import '../../domain/entidades.dart';
import '../cuento/pantalla_cuento.dart';
import '../widgets/comunes.dart';

/// Biblioteca del niño: lee de la caché (Hive) y se sincroniza si hay red.
class PantallaBiblioteca extends ConsumerWidget {
  const PantallaBiblioteca({super.key});

  Future<void> _confirmarBorrado(BuildContext context, WidgetRef ref, Cuento cuento) async {
    final borrar = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.delete_forever, size: 72, color: Colores.rojo),
        actionsAlignment: MainAxisAlignment.spaceEvenly,
        actionsPadding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
        actions: [
          BotonIcono(
            key: const Key('confirmar-no'),
            icono: Icons.close,
            etiqueta: 'No borrar',
            color: Colores.verde,
            alPulsar: () => Navigator.of(ctx).pop(false),
          ),
          BotonIcono(
            key: const Key('confirmar-si'),
            icono: Icons.check,
            etiqueta: 'Sí, borrar',
            color: Colores.rojo,
            alPulsar: () => Navigator.of(ctx).pop(true),
          ),
        ],
      ),
    );
    if (borrar ?? false) await ref.read(bibliotecaProvider.notifier).borrar(cuento.id);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final biblioteca = ref.watch(bibliotecaProvider);
    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 72,
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.collections_bookmark, size: 36, color: Colores.verde),
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                'Mis cuentos',
                overflow: TextOverflow.ellipsis,
                style: Tipos.titulo.copyWith(fontSize: 26),
              ),
            ),
          ],
        ),
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(bibliotecaProvider.future),
        child: biblioteca.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (_, _) => _Vacia(
            icono: Icons.cloud_off,
            color: Colores.violeta,
            boton: BotonIcono(
              key: const Key('biblioteca-reintentar'),
              icono: Icons.refresh,
              etiqueta: 'Intentar otra vez',
              color: Colores.violeta,
              alPulsar: () => ref.invalidate(bibliotecaProvider),
            ),
          ),
          data: (cuentos) => cuentos.isEmpty
              ? _Vacia(
                  vaciaKey: const Key('biblioteca-vacia'),
                  icono: Icons.brush,
                  color: Colores.naranja,
                  boton: BotonIcono(
                    key: const Key('biblioteca-dibujar'),
                    icono: Icons.brush,
                    etiqueta: 'Dibujar un cuento',
                    alPulsar: () => Navigator.of(context).pop(),
                  ),
                )
              : GridView.builder(
                  padding: const EdgeInsets.all(14),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: MediaQuery.sizeOf(context).shortestSide >= 600 ? 3 : 2,
                    mainAxisSpacing: 14,
                    crossAxisSpacing: 14,
                    childAspectRatio: 0.78,
                  ),
                  itemCount: cuentos.length,
                  itemBuilder: (_, i) => _Portada(
                    cuento: cuentos[i],
                    color: _lomos[i % _lomos.length],
                    alAbrir: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(builder: (_) => PantallaCuento(cuento: cuentos[i])),
                    ),
                    alBorrar: () => _confirmarBorrado(context, ref, cuentos[i]),
                  ),
                ),
        ),
      ),
    );
  }
}

/// Colores de la franja de cada libro, para que la estantería no se vea toda igual.
const _lomos = [Colores.naranja, Colores.violeta, Colores.verde, Colores.azulInfo];

/// Estado vacío o de error: un icono grande sobre un círculo suave y un botón de acción.
/// Va dentro de una lista para que «tirar para actualizar» siga funcionando.
class _Vacia extends StatelessWidget {
  const _Vacia({required this.icono, required this.color, required this.boton, this.vaciaKey});

  final IconData icono;
  final Color color;
  final Widget boton;
  final Key? vaciaKey;

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        const SizedBox(height: 90),
        Center(
          child: Container(
            width: 180,
            height: 180,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withValues(alpha: 0.14),
              border: Border.all(color: color.withValues(alpha: 0.4), width: 4),
            ),
            child: Icon(icono, key: vaciaKey, size: 96, color: color),
          ),
        ),
        const SizedBox(height: 32),
        Center(child: boton),
      ],
    );
  }
}

class _Portada extends StatelessWidget {
  const _Portada({
    required this.cuento,
    required this.color,
    required this.alAbrir,
    required this.alBorrar,
  });

  final Cuento cuento;
  final Color color;
  final VoidCallback alAbrir;
  final VoidCallback alBorrar;

  @override
  Widget build(BuildContext context) {
    final portada = cuento.paginas.isNotEmpty ? cuento.paginas.first.imagen : null;
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Radios.medio),
        side: BorderSide(color: color, width: 3),
      ),
      child: InkWell(
        key: Key('portada-${cuento.id}'),
        onTap: alAbrir,
        child: Stack(
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: portada != null
                      ? Image.memory(portada, fit: BoxFit.cover)
                      : const ColoredBox(
                          color: Colores.amarillo,
                          child: Icon(Icons.menu_book, size: 64, color: Colors.white),
                        ),
                ),
                Container(
                  color: color.withValues(alpha: 0.12),
                  padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
                  child: Text(
                    cuento.titulo ?? '',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Tipos.subtitulo.copyWith(fontSize: 16, height: 1.15),
                  ),
                ),
              ],
            ),
            Positioned(
              top: 2,
              right: 2,
              child: BotonIcono(
                key: Key('borrar-${cuento.id}'),
                icono: Icons.delete,
                etiqueta: 'Borrar cuento',
                color: Colores.rojo,
                tamano: 44,
                alPulsar: alBorrar,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
