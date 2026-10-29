import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/proveedores.dart';
import '../../core/tema.dart';
import '../../domain/entidades.dart';
import '../widgets/comunes.dart';

final perfilesProvider = FutureProvider<List<Perfil>>(
  (ref) => ref.watch(cuentasRepositorioProvider).perfiles(),
);

/// Elegir o crear el perfil del niño (6 a 12 años). Lo maneja el adulto.
class PantallaPerfiles extends ConsumerWidget {
  const PantallaPerfiles({super.key});

  static const _avatares = [Colores.naranja, Colores.violeta, Colores.verde, Colores.azulInfo];

  Future<void> _crear(BuildContext context, WidgetRef ref) async {
    final datos = await showDialog<({String apodo, int edad})>(
      context: context,
      builder: (_) => const _FormularioPerfil(),
    );
    if (datos == null) return;
    await ref.read(cuentasRepositorioProvider).crearPerfil(apodo: datos.apodo, edad: datos.edad);
    ref.invalidate(perfilesProvider);
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
    // Con cero perfiles el botón grande del estado vacío es la única acción: sin botón flotante.
    final hayPerfiles = perfiles.value?.isNotEmpty ?? false;
    return Scaffold(
      appBar: AppBar(
        title: const Text('¿Quién va a dibujar?'),
        actions: [
          IconButton(
            tooltip: ref.watch(sesionProvider).invitado
                ? 'Salir del modo invitado'
                : 'Cerrar sesión',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(sesionProvider.notifier).cerrar(),
          ),
        ],
      ),
      floatingActionButton: hayPerfiles
          ? SizedBox(
              height: kToqueMinimo + 8,
              child: FloatingActionButton.extended(
                key: const Key('boton-nuevo-perfil'),
                onPressed: () => _crear(context, ref),
                icon: const Icon(Icons.person_add, size: 28),
                label: const Text('Nuevo dibujante', style: Tipos.boton),
              ),
            )
          : null,
      body: Column(
        children: [
          const Padding(padding: EdgeInsets.fromLTRB(16, 8, 16, 0), child: AvisoInvitado()),
          Expanded(child: _lista(context, ref, perfiles)),
        ],
      ),
    );
  }

  Widget _lista(BuildContext context, WidgetRef ref, AsyncValue<List<Perfil>> perfiles) {
    return perfiles.when(
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
          ? _SinPerfiles(alCrear: () => _crear(context, ref))
          : Column(
              children: [
                Expanded(
                  child: GridView.count(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
                    crossAxisCount: 2,
                    mainAxisSpacing: 16,
                    crossAxisSpacing: 16,
                    childAspectRatio: 0.78,
                    children: [
                      for (final (i, p) in lista.indexed)
                        _TarjetaPerfil(
                          perfil: p,
                          color: _avatares[i % _avatares.length],
                          alPulsar: () => ref.read(sesionProvider.notifier).elegirPerfil(p),
                          alMantener: () => _borrar(context, ref, p),
                        ),
                    ],
                  ),
                ),
                // Pista solo para el adulto (borrar es un gesto a propósito difícil); abajo
                // deja sitio para el botón flotante.
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 92),
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
    );
  }
}

/// Formulario del adulto. Es dueño de su controlador: se libera cuando el diálogo
/// termina de cerrarse, no antes (antes fallaba al animar el cierre).
class _FormularioPerfil extends StatefulWidget {
  const _FormularioPerfil();

  @override
  State<_FormularioPerfil> createState() => _FormularioPerfilState();
}

class _FormularioPerfilState extends State<_FormularioPerfil> {
  final _apodo = TextEditingController();
  var _edad = 8;

  @override
  void dispose() {
    _apodo.dispose();
    super.dispose();
  }

  void _aceptar() {
    final apodo = _apodo.text.trim();
    Navigator.pop(context, apodo.isEmpty ? null : (apodo: apodo, edad: _edad));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      icon: const Icon(Icons.face, size: 56, color: Colores.violeta),
      title: const Text('Nuevo perfil'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextField(
              key: const Key('campo-apodo'),
              controller: _apodo,
              maxLength: 40,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Apodo',
                helperText: 'No hace falta el nombre real',
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
                    selected: _edad == e,
                    labelStyle: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: _edad == e ? Colors.white : Colores.texto,
                    ),
                    onSelected: (_) => setState(() => _edad = e),
                  ),
              ],
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancelar')),
        FilledButton(onPressed: _aceptar, child: const Text('Crear')),
      ],
    );
  }
}

/// Estado vacío: se entiende sin leer (dibujo grande + botón con icono). El texto es para el adulto.
class _SinPerfiles extends StatelessWidget {
  const _SinPerfiles({required this.alCrear});

  final VoidCallback alCrear;

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const Key('perfiles-vacio'),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _IlustracionDibujante(),
            const SizedBox(height: 32),
            SizedBox(
              width: double.infinity,
              height: 80,
              child: ElevatedButton.icon(
                key: const Key('boton-primer-perfil'),
                onPressed: alCrear,
                icon: const Icon(Icons.person_add, size: 36),
                label: const Text('Crear el primer dibujante', style: Tipos.boton),
                style: ElevatedButton.styleFrom(
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radios.grande)),
                ),
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Adulto: crea un perfil con el apodo y la edad del niño. '
              'Después, al tocar su tarjeta se abre el lienzo para dibujar.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 15, color: Colores.texto),
            ),
          ],
        ),
      ),
    );
  }
}

/// Carita grande en azul de la marca con un lápiz naranja y un «+»: «aquí falta alguien que dibuje».
class _IlustracionDibujante extends StatelessWidget {
  const _IlustracionDibujante();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 220,
      height: 220,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            width: 220,
            height: 220,
            decoration: BoxDecoration(
              color: Colores.azul.withValues(alpha: 0.14),
              shape: BoxShape.circle,
            ),
          ),
          Container(
            width: 156,
            height: 156,
            decoration: const BoxDecoration(color: Colores.azul, shape: BoxShape.circle),
            child: const Icon(Icons.face, color: Colores.crema, size: 112),
          ),
          Positioned(
            right: 8,
            bottom: 16,
            child: Container(
              width: 76,
              height: 76,
              decoration: BoxDecoration(
                color: Colores.naranja,
                shape: BoxShape.circle,
                border: Border.all(color: Colores.crema, width: 5),
              ),
              child: const Icon(Icons.brush, color: Colors.white, size: 40),
            ),
          ),
          Positioned(
            left: 10,
            top: 14,
            child: Container(
              width: 60,
              height: 60,
              decoration: BoxDecoration(
                color: Colores.naranja,
                shape: BoxShape.circle,
                border: Border.all(color: Colores.crema, width: 5),
              ),
              child: const Icon(Icons.add, color: Colors.white, size: 38),
            ),
          ),
        ],
      ),
    );
  }
}

/// Tarjeta grande de un perfil: el lápiz naranja dice «toca aquí para dibujar».
class _TarjetaPerfil extends StatelessWidget {
  const _TarjetaPerfil({
    required this.perfil,
    required this.color,
    required this.alPulsar,
    required this.alMantener,
  });

  final Perfil perfil;
  final Color color;
  final VoidCallback alPulsar;
  final VoidCallback alMantener;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: 'Dibujar como ${perfil.apodo}',
      child: Card(
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Radios.grande),
          side: BorderSide(color: color, width: 3),
        ),
        child: InkWell(
          key: Key('perfil-${perfil.id}'),
          borderRadius: BorderRadius.circular(Radios.grande),
          onTap: alPulsar,
          onLongPress: alMantener,
          child: Padding(
            padding: const EdgeInsets.all(12),
            // Con letra grande o pantalla estrecha se encoge en vez de desbordarse.
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Column(
                mainAxisSize: MainAxisSize.min,
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
                  const SizedBox(height: 8),
                  // Un apodo largo se corta en vez de encoger toda la tarjeta.
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 150),
                    child: Text(
                      perfil.apodo,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Tipos.subtitulo.copyWith(fontSize: 22),
                    ),
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
                  const SizedBox(height: 10),
                  Container(
                    key: Key('perfil-${perfil.id}-dibujar'),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: Colores.naranja,
                      borderRadius: BorderRadius.circular(Radios.medio),
                      boxShadow: sombraSuave(Colores.naranja),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.brush, color: Colors.white, size: 28),
                        SizedBox(width: 6),
                        Text(
                          'Dibujar',
                          style: TextStyle(
                            fontFamily: 'Fredoka',
                            color: Colors.white,
                            fontSize: 19,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
