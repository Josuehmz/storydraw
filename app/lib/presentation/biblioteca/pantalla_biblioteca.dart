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
        icon: const Icon(Icons.delete_forever, size: 64, color: Colores.rojo),
        actionsAlignment: MainAxisAlignment.spaceEvenly,
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
        backgroundColor: Colores.crema,
        title: const Icon(Icons.collections_bookmark, size: 40, color: Colores.verde),
        centerTitle: true,
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(bibliotecaProvider.future),
        child: biblioteca.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (_, _) => ListView(
            children: const [
              SizedBox(height: 120),
              Icon(Icons.cloud_off, size: 96, color: Colores.violeta),
            ],
          ),
          data: (cuentos) => cuentos.isEmpty
              ? ListView(
                  children: const [
                    SizedBox(height: 120),
                    Icon(
                      Icons.brush,
                      key: Key('biblioteca-vacia'),
                      size: 96,
                      color: Colores.naranja,
                    ),
                  ],
                )
              : GridView.builder(
                  padding: const EdgeInsets.all(12),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: MediaQuery.sizeOf(context).shortestSide >= 600 ? 3 : 2,
                    mainAxisSpacing: 12,
                    crossAxisSpacing: 12,
                    childAspectRatio: 0.8,
                  ),
                  itemCount: cuentos.length,
                  itemBuilder: (_, i) => _Portada(
                    cuento: cuentos[i],
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

class _Portada extends StatelessWidget {
  const _Portada({required this.cuento, required this.alAbrir, required this.alBorrar});

  final Cuento cuento;
  final VoidCallback alAbrir;
  final VoidCallback alBorrar;

  @override
  Widget build(BuildContext context) {
    final portada = cuento.paginas.isNotEmpty ? cuento.paginas.first.imagen : null;
    return Card(
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
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
                Padding(
                  padding: const EdgeInsets.all(8),
                  child: Text(
                    cuento.titulo ?? '',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
            Positioned(
              top: 4,
              right: 4,
              child: BotonIcono(
                key: Key('borrar-${cuento.id}'),
                icono: Icons.delete,
                etiqueta: 'Borrar cuento',
                color: Colores.rojo,
                tamano: 48,
                alPulsar: alBorrar,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
