import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/proveedores.dart';
import '../../core/tema.dart';
import '../../domain/entidades.dart';

final perfilesProvider = FutureProvider<List<Perfil>>(
  (ref) => ref.read(cuentasRepositorioProvider).perfiles(),
);

/// Elegir o crear el perfil del niño (6 a 12 años). Lo maneja el adulto.
class PantallaPerfiles extends ConsumerWidget {
  const PantallaPerfiles({super.key});

  static const _avatares = [Colores.naranja, Colores.violeta, Colores.verde, Colores.azulInfo];

  Future<void> _crear(BuildContext context, WidgetRef ref) async {
    final apodo = TextEditingController();
    var edad = 8;
    final crear = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Text('Nuevo perfil'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                key: const Key('campo-apodo'),
                controller: apodo,
                maxLength: 40,
                decoration: const InputDecoration(
                  labelText: 'Apodo (no hace falta el nombre real)',
                ),
              ),
              const SizedBox(height: 8),
              const Text('Edad'),
              Wrap(
                spacing: 6,
                children: [
                  for (var e = 6; e <= 12; e++)
                    ChoiceChip(
                      label: Text('$e'),
                      selected: edad == e,
                      onSelected: (_) => setState(() => edad = e),
                    ),
                ],
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Crear')),
          ],
        ),
      ),
    );
    if (crear ?? false) {
      if (apodo.text.trim().isNotEmpty) {
        await ref
            .read(cuentasRepositorioProvider)
            .crearPerfil(apodo: apodo.text.trim(), edad: edad);
        ref.invalidate(perfilesProvider);
      }
    }
    apodo.dispose();
  }

  Future<void> _borrar(BuildContext context, WidgetRef ref, Perfil perfil) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('¿Borrar a ${perfil.apodo}?'),
        content: const Text('Se borran su perfil y todos sus cuentos. No se puede deshacer.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Borrar')),
        ],
      ),
    );
    if (ok ?? false) {
      await ref.read(cuentasRepositorioProvider).borrarPerfil(perfil.id);
      ref.invalidate(perfilesProvider);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final perfiles = ref.watch(perfilesProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('¿Quién va a dibujar?'),
        actions: [
          IconButton(
            tooltip: 'Cerrar sesión',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(sesionProvider.notifier).cerrar(),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.large(
        key: const Key('boton-nuevo-perfil'),
        onPressed: () => _crear(context, ref),
        child: const Icon(Icons.person_add, size: 40),
      ),
      body: perfiles.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => Center(
          child: IconButton(
            iconSize: 72,
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(perfilesProvider),
          ),
        ),
        data: (lista) => GridView.count(
          padding: const EdgeInsets.all(16),
          crossAxisCount: 2,
          mainAxisSpacing: 16,
          crossAxisSpacing: 16,
          children: [
            for (final (i, p) in lista.indexed)
              InkWell(
                key: Key('perfil-${p.id}'),
                borderRadius: BorderRadius.circular(24),
                onTap: () => ref.read(sesionProvider.notifier).elegirPerfil(p),
                onLongPress: () => _borrar(context, ref, p),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    CircleAvatar(
                      radius: 52,
                      backgroundColor: _avatares[i % _avatares.length],
                      child: Text(
                        p.apodo.characters.first.toUpperCase(),
                        style: const TextStyle(fontSize: 44, color: Colors.white),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      p.apodo,
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
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
