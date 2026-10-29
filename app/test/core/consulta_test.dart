import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:storydraw/core/config.dart';
import 'package:storydraw/core/consulta.dart';

void main() {
  test('por defecto se consulta cada 3 s, se espera hasta 4 min y se avisa a los 60 s', () {
    const config = AppConfig(apiUrl: 'http://backend.prueba');
    expect(config.intervaloConsulta, const Duration(seconds: 3));
    expect(config.esperaMaxima, const Duration(minutes: 4));
    expect(config.avisoDemora, const Duration(seconds: 60));
    // 4 min / 3 s: como mucho 80 esperas (el cuento de 180 s hizo 78 consultas a 1 por 2 s)
    expect(config.esperaMaxima.inSeconds ~/ config.intervaloConsulta.inSeconds, 80);
  });

  test('entre consulta y consulta se espera el intervalo', () async {
    final momentos = <Duration>[];
    final reloj = Stopwatch()..start();
    var consultas = 0;
    final r = await consultarCadaIntervalo<String>(
      consultar: () async {
        momentos.add(reloj.elapsed);
        return ++consultas < 3 ? 'en_proceso' : 'listo';
      },
      enProceso: (e) => e == 'en_proceso',
      intervalo: const Duration(milliseconds: 60),
      esperaMaxima: const Duration(seconds: 10),
    );
    expect(r, 'listo');
    expect(consultas, 3);
    for (var i = 1; i < momentos.length; i++) {
      expect(momentos[i] - momentos[i - 1], greaterThanOrEqualTo(const Duration(milliseconds: 55)));
    }
  });

  test('pasada la espera máxima lanza TimeoutException y deja de consultar', () async {
    var consultas = 0;
    await expectLater(
      consultarCadaIntervalo<String>(
        consultar: () async {
          consultas++;
          return 'en_proceso';
        },
        enProceso: (e) => e == 'en_proceso',
        intervalo: const Duration(milliseconds: 10),
        esperaMaxima: const Duration(milliseconds: 50),
      ),
      throwsA(isA<TimeoutException>()),
    );
    // 50 ms / 10 ms = 5 esperas: la primera consulta más 5
    expect(consultas, lessThanOrEqualTo(6));
    final antes = consultas;
    await Future<void>.delayed(const Duration(milliseconds: 40));
    expect(consultas, antes);
  });
}
