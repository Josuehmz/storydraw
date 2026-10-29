import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/proveedores.dart';
import '../core/tema.dart';
import 'acceso/pantalla_acceso.dart';
import 'lienzo/pantalla_lienzo.dart';
import 'perfiles/pantalla_perfiles.dart';

class StoryDrawApp extends StatelessWidget {
  const StoryDrawApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'StoryDraw',
      debugShowCheckedModeBanner: false,
      theme: construirTema(),
      builder: (context, child) => _ColumnaCentrada(child: child!),
      home: const _Inicio(),
    );
  }
}

/// Ancho máximo de la app. En una pantalla ancha (la versión web en un computador) la app
/// se ve como en el celular: una columna centrada, sin estirar el lienzo ni las tarjetas.
const double kAnchoMaximo = 560;

class _ColumnaCentrada extends StatelessWidget {
  const _ColumnaCentrada({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    if (media.size.width <= kAnchoMaximo) return child;
    return ColoredBox(
      color: Colores.azul.withValues(alpha: 0.08),
      child: Center(
        child: Container(
          width: kAnchoMaximo,
          decoration: BoxDecoration(color: Colores.crema, boxShadow: sombraSuave()),
          // Las pantallas miden el ancho con MediaQuery: que vean el de la columna.
          child: MediaQuery(
            data: media.copyWith(size: Size(kAnchoMaximo, media.size.height)),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// Sin sesión → acceso del adulto; sin perfil → elegir niño; si no, el lienzo.
class _Inicio extends ConsumerWidget {
  const _Inicio();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sesion = ref.watch(sesionProvider);
    if (!sesion.autenticado) return const PantallaAcceso();
    if (sesion.perfil == null) return const PantallaPerfiles();
    return const PantallaLienzo();
  }
}
