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
      home: const _Inicio(),
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
