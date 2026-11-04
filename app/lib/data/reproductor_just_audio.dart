// StreamAudioSource es experimental en just_audio, pero permite reproducir desde
// bytes en memoria (la caché de Hive) sin escribir archivos temporales.
// ignore_for_file: experimental_member_use

import 'dart:async';
import 'dart:typed_data';

import 'package:just_audio/just_audio.dart';

import '../domain/repositorios.dart';

/// Narración con just_audio desde bytes en memoria (sirve también sin conexión).
class ReproductorJustAudio implements Reproductor {
  final AudioPlayer _player = AudioPlayer();

  @override
  Stream<bool> get reproduciendo => _player.playerStateStream
      .map((s) => s.playing && s.processingState != ProcessingState.completed)
      .distinct();

  @override
  Future<void> reproducir(Uint8List mp3) async {
    await _player.stop();
    await _player.setAudioSource(_FuenteBytes(mp3));
    unawaited(_player.play());
  }

  @override
  Future<void> detener() => _player.stop();

  @override
  Future<void> liberar() => _player.dispose();
}

class _FuenteBytes extends StreamAudioSource {
  _FuenteBytes(this._bytes);

  final Uint8List _bytes;

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    start ??= 0;
    end ??= _bytes.length;
    return StreamAudioResponse(
      sourceLength: _bytes.length,
      contentLength: end - start,
      offset: start,
      stream: Stream.value(_bytes.sublist(start, end)),
      contentType: 'audio/mpeg',
    );
  }
}
