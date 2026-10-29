"""Utilidades de audio para la narración: de WAV a MP3.

MeloTTS (Cloudflare) devuelve un WAV mono de 44,1 kHz: unos 88 KB por segundo, demasiado
para mandarlo al teléfono. El habla se entiende igual de bien en MP3 mono de 22 kHz y 48 kbps
(unos 6 KB por segundo), así que se convierte antes de guardarlo.
"""

from __future__ import annotations

import io
import wave

import lameenc

from app.infra.adaptadores.comun import ErrorProveedor

KBPS = 48
HZ_SALIDA = 22_050


def es_wav(datos: bytes) -> bool:
    return datos[:4] == b"RIFF" and datos[8:12] == b"WAVE"


def wav_a_mp3(wav: bytes) -> tuple[bytes, float]:
    """Devuelve el MP3 y la duración en segundos. Lanza ErrorProveedor si el WAV no sirve."""
    try:
        with wave.open(io.BytesIO(wav)) as w:
            canales = w.getnchannels()
            hz = w.getframerate()
            ancho = w.getsampwidth()
            cuadros = w.getnframes()
            pcm = w.readframes(cuadros)
    except (wave.Error, EOFError) as exc:
        raise ErrorProveedor("el audio de la voz no es un WAV válido") from exc
    if ancho != 2 or canales not in (1, 2) or not pcm:
        raise ErrorProveedor("el audio de la voz tiene un formato inesperado")
    codificador = lameenc.Encoder()
    codificador.set_bit_rate(KBPS)
    codificador.set_in_sample_rate(hz)
    codificador.set_out_sample_rate(HZ_SALIDA)
    codificador.set_channels(canales)
    codificador.set_quality(2)
    mp3 = bytes(codificador.encode(pcm)) + bytes(codificador.flush())
    return mp3, cuadros / hz
