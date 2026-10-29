import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/proveedores.dart';
import '../../core/tema.dart';
import '../../domain/entidades.dart';
import '../widgets/comunes.dart';

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
          icon: const Icon(Icons.face, size: 56, color: Colores.violeta),
          title: const Text('Nuevo perfil'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                key: const Key('campo-apodo'),
                controller: apodo,
                maxLength: 40,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(
                  labelText: 'Apodo (no hace falta el nombre real)',
                ),
              ),
              const SizedBox(height: 8),
              Text('Edad', style: Tipos.subtitulo.copyWith(fontSize: 18)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (var e = 6; e <= 12; e++)
                    ChoiceChip(
                      label: Text('$e'),
                      showCheckmark: false,
                      selected: edad == e,
                      labelStyle: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: edad == e ? Colors.white : Colores.texto,
                      ),
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
        icon: const Icon(Icons.delete_forever, size: 56, color: Colores.rojo),
        title: Text('¿Borrar a ${perfil.apodo}?'),
        content: const Text('Se borran su perfil y todos sus cuentos. No se puede deshacer.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colores.rojo),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Borrar'),
          ),
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
      floatingActionButton: FloatingActionButton.extended(
        key: const Key('boton-nuevo-perfil'),
        onPressed: () => _crear(context, ref),
        icon: const Icon(Icons.person_add, size: 28),
        label: const Text('Nuevo perfil', style: Tipos.boton),
      ),
      body: perfiles.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => Center(
          child: BotonIcono(
            icono: Icons.refresh,
            etiqueta: 'Intentar otra vez',
            color: Colores.violeta,
            alPulsar: () => ref.invalidate(perfilesProvider),
          ),
        ),
        data: (lista) => lista.isEmpty
            ? const _SinPerfiles()
            : Column(
                children: [
                  Expanded(
                    child: GridView.count(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                      crossAxisCount: 2,
                      mainAxisSpacing: 16,
                      crossAxisSpacing: 16,
                      childAspectRatio: 0.8,
                      children: [
                        for (final (i, p) in lista.indexed)
                          _TarjetaPerfil(
                            perfil: p,
                            color: _avatares[i % _avatares.length],
                            alElegir: () => ref.read(sesionProvider.notifier).elegirPerfil(p),
                            alBorrar: () => _borrar(context, ref, p),
                          ),
                      ],
                    ),
                  ),
                  // Pista solo para el adulto: borrar es un gesto a propósito difícil.
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 84),
                    child: Text(
                      'Mantén pulsado un perfil para borrarlo',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: Colores.texto.withValues(alpha: 0.6),
                      ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

/// Un niño: avatar grande con su inicial, apodo y edad.
class _TarjetaPerfil extends StatelessWidget {
  const _TarjetaPerfil({
    required this.perfil,
    required this.color,
    required this.alElegir,
    required this.alBorrar,
  });

  final Perfil perfil;
  final Color color;
  final VoidCallback alElegir;
  final VoidCallback alBorrar;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Radios.grande),
        side: BorderSide(color: color, width: 3),
      ),
      child: InkWell(
        key: Key('perfil-${perfil.id}'),
        borderRadius: BorderRadius.circular(Radios.grande),
        onTap: alElegir,
        onLongPress: alBorrar,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 88,
                height: 88,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: color,
                  border: Border.all(color: Colors.white, width: 4),
                  boxShadow: sombraSuave(color),
                ),
                child: Text(
                  perfil.apodo.characters.first.toUpperCase(),
                  style: Tipos.titulo.copyWith(fontSize: 46, color: Colors.white),
                ),
              ),
              const SizedBox(height: 10),
              Text(
                perfil.apodo,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Tipos.subtitulo.copyWith(fontSize: 22),
              ),
              const SizedBox(height: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  '${perfil.edad} años',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: color),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Aún no hay niños: invita a crear el primer perfil.
class _SinPerfiles extends StatelessWidget {
  const _SinPerfiles();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 160,
              height: 160,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colores.violeta.withValues(alpha: 0.14),
                border: Border.all(color: Colores.violeta.withValues(alpha: 0.4), width: 4),
              ),
              child: const Icon(Icons.face, size: 88, color: Colores.violeta),
            ),
            const SizedBox(height: 20),
            Text(
              'Crea el perfil de quien va a dibujar',
              textAlign: TextAlign.center,
              style: Tipos.subtitulo.copyWith(fontSize: 22),
            ),
          ],
        ),
      ),
    );
  }
}
