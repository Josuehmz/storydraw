import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/config.dart';
import '../core/http.dart';
import '../data/cache_cuentos.dart';
import '../data/repositorios_api.dart';
import '../data/repositorios_invitado.dart';
import '../data/sesion_local.dart';
import '../domain/entidades.dart';
import '../domain/repositorios.dart';

/// Proveedores escritos a mano (sin build_runner). `main.dart` sobreescribe los
/// que dependen de la plataforma; las pruebas sobreescriben los repositorios.

final configProvider = Provider<AppConfig>((ref) => AppConfig.desdeEntorno());

final sesionLocalProvider = Provider<SesionLocal>(
  (ref) => throw UnimplementedError('Se inyecta en main.dart'),
);

final cacheProvider = Provider<CacheCuentos>(
  (ref) => throw UnimplementedError('Se inyecta en main.dart'),
);

final dioProvider = Provider<Dio>((ref) {
  final sesion = ref.watch(sesionLocalProvider);
  return crearDio(ref.watch(configProvider), token: () => sesion.token);
});

final cuentasRepositorioProvider = Provider<CuentasRepositorio>((ref) {
  if (ref.watch(sesionProvider.select((s) => s.invitado))) {
    return ref.watch(cuentasInvitadoProvider);
  }
  return CuentasRepositorioApi(
    ref.watch(dioProvider),
    ref.watch(sesionLocalProvider),
    ref.watch(cacheProvider),
  );
});

final cuentosRepositorioProvider = Provider<CuentosRepositorio>((ref) {
  if (ref.watch(sesionProvider.select((s) => s.invitado))) {
    return CuentosRepositorioInvitado(
      ref.watch(dioProvider),
      ref.watch(cacheProvider),
      ref.watch(configProvider),
      ref.watch(sesionLocalProvider),
      ref.watch(cuentasInvitadoProvider),
    );
  }
  return CuentosRepositorioApi(
    ref.watch(dioProvider),
    ref.watch(cacheProvider),
    ref.watch(configProvider),
  );
});

/// Modo invitado (solo pruebas locales): perfiles y cuentos solo en el dispositivo.
final cuentasInvitadoProvider = Provider<CuentasRepositorioInvitado>(
  (ref) => CuentasRepositorioInvitado(
    ref.watch(dioProvider),
    ref.watch(sesionLocalProvider),
    ref.watch(cacheProvider),
  ),
);

// ------------------------------------------------------------------- sesión

class EstadoSesion {
  const EstadoSesion({required this.autenticado, this.perfil, this.invitado = false});

  final bool autenticado;
  final Perfil? perfil;

  /// Entró como invitado: sin cuenta, todo se guarda solo en el dispositivo.
  final bool invitado;
}

class SesionNotifier extends Notifier<EstadoSesion> {
  SesionLocal get _local => ref.read(sesionLocalProvider);

  @override
  EstadoSesion build() {
    final local = ref.watch(sesionLocalProvider);
    final id = local.perfilId;
    return EstadoSesion(
      autenticado: local.token != null,
      invitado: local.token != null && local.invitado,
      perfil: id == null
          ? null
          : Perfil(id: id, apodo: local.perfilApodo ?? '', edad: local.perfilEdad ?? 8),
    );
  }

  Future<void> iniciar(String email, String contrasena) async {
    await ref.read(cuentasRepositorioProvider).iniciarSesion(email: email, contrasena: contrasena);
    state = const EstadoSesion(autenticado: true);
  }

  /// Solo existe si la app se compiló con `MODO_INVITADO=true`.
  Future<void> entrarComoInvitado() async {
    await ref.read(cuentasInvitadoProvider).entrar();
    state = const EstadoSesion(autenticado: true, invitado: true);
  }

  Future<void> elegirPerfil(Perfil perfil) async {
    await _local.elegirPerfil(id: perfil.id, apodo: perfil.apodo, edad: perfil.edad);
    state = EstadoSesion(autenticado: true, perfil: perfil, invitado: state.invitado);
  }

  Future<void> cambiarPerfil() async {
    await _local.olvidarPerfil();
    state = EstadoSesion(autenticado: true, invitado: state.invitado);
  }

  Future<void> cerrar() async {
    await ref.read(cuentasRepositorioProvider).cerrarSesion();
    state = const EstadoSesion(autenticado: false);
  }
}

final sesionProvider = NotifierProvider<SesionNotifier, EstadoSesion>(SesionNotifier.new);

// --------------------------------------------------------------- biblioteca

class BibliotecaNotifier extends AsyncNotifier<List<Cuento>> {
  @override
  Future<List<Cuento>> build() async {
    final perfil = ref.watch(sesionProvider).perfil;
    if (perfil == null) return const [];
    return ref.read(cuentosRepositorioProvider).biblioteca(perfil.id);
  }

  Future<void> borrar(String cuentoId) async {
    await ref.read(cuentosRepositorioProvider).borrar(cuentoId);
    final actual = state.value ?? const <Cuento>[];
    state = AsyncData([
      for (final c in actual)
        if (c.id != cuentoId) c,
    ]);
  }
}

final bibliotecaProvider = AsyncNotifierProvider<BibliotecaNotifier, List<Cuento>>(
  BibliotecaNotifier.new,
);
