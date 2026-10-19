import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/errores.dart';
import '../domain/entidades.dart';
import 'proveedores.dart';

/// Fases del flujo del niño: dibujar → identificar → momento mágico → cuento.
enum Fase { inicial, identificando, eligiendo, generando, listo, rechazado, error }

class EstadoFlujo {
  const EstadoFlujo({
    this.fase = Fase.inicial,
    this.dibujo,
    this.identificacion,
    this.personaje,
    this.cuento,
    this.error,
  });

  final Fase fase;

  /// El dibujo vive solo en memoria mientras dura el flujo; nunca se guarda.
  final Uint8List? dibujo;
  final Identificacion? identificacion;
  final String? personaje;
  final Cuento? cuento;
  final TipoError? error;

  EstadoFlujo copiar({
    Fase? fase,
    Identificacion? identificacion,
    String? personaje,
    Cuento? cuento,
    TipoError? error,
  }) => EstadoFlujo(
    fase: fase ?? this.fase,
    dibujo: dibujo,
    identificacion: identificacion ?? this.identificacion,
    personaje: personaje ?? this.personaje,
    cuento: cuento ?? this.cuento,
    error: error,
  );
}

class FlujoCuentoNotifier extends Notifier<EstadoFlujo> {
  @override
  EstadoFlujo build() => const EstadoFlujo();

  Future<void> identificar(Uint8List dibujo) async {
    state = EstadoFlujo(fase: Fase.identificando, dibujo: dibujo);
    Identificacion identificacion;
    try {
      identificacion = await ref.read(cuentosRepositorioProvider).identificar(dibujo);
    } on ErrorApi catch (e) {
      if (e.tipo == TipoError.sesionVencida || e.tipo == TipoError.limite) {
        state = state.copiar(fase: Fase.error, error: e.tipo);
        return;
      }
      // Sin visión el flujo sigue: el niño escribe qué dibujó.
      identificacion = const Identificacion.noDisponible();
    }
    if (!ref.mounted) return;
    state = state.copiar(fase: Fase.eligiendo, identificacion: identificacion);
  }

  Future<void> crear(String personaje) async {
    final dibujo = state.dibujo;
    final perfil = ref.read(sesionProvider).perfil;
    if (dibujo == null || perfil == null) return;
    state = state.copiar(fase: Fase.generando, personaje: personaje);
    final repo = ref.read(cuentosRepositorioProvider);
    try {
      final id = await repo.crear(perfilId: perfil.id, dibujo: dibujo, personaje: personaje);
      final cuento = await repo.esperar(id);
      if (!ref.mounted) return;
      state = switch (cuento.estado) {
        EstadoCuento.listo => state.copiar(fase: Fase.listo, cuento: cuento),
        EstadoCuento.rechazado => state.copiar(fase: Fase.rechazado),
        _ => state.copiar(fase: Fase.error, error: TipoError.servidor),
      };
      if (cuento.estado == EstadoCuento.listo) ref.invalidate(bibliotecaProvider);
    } on ErrorApi catch (e) {
      if (!ref.mounted) return;
      state = state.copiar(fase: Fase.error, error: e.tipo);
    }
  }

  /// «No era así»: vuelve a la identificación con el mismo dibujo en memoria.
  void noEraAsi() {
    if (state.dibujo == null) return;
    state = state.copiar(fase: Fase.eligiendo);
  }

  Future<void> reintentarNarracion() async {
    final cuento = state.cuento;
    if (cuento == null) return;
    try {
      final nuevo = await ref.read(cuentosRepositorioProvider).reintentarNarracion(cuento.id);
      if (!ref.mounted) return;
      state = state.copiar(cuento: nuevo);
      ref.invalidate(bibliotecaProvider);
    } on ErrorApi catch (_) {
      // El aviso sigue visible y el niño puede volver a intentarlo.
    }
  }

  /// Termina el flujo y suelta el dibujo de la memoria.
  void reiniciar() => state = const EstadoFlujo();
}

final flujoProvider = NotifierProvider<FlujoCuentoNotifier, EstadoFlujo>(FlujoCuentoNotifier.new);
