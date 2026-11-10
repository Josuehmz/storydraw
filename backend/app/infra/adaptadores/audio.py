"""Utilidades de audio para la narración: texto limpio, WAV a MP3 y duración de un MP3.

MeloTTS (Cloudflare) devuelve un WAV mono de 44,1 kHz: unos 88 KB por segundo, demasiado
para mandarlo al teléfono. El habla se entiende igual de bien en MP3 mono de 22 kHz y 48 kbps
(unos 6 KB por segundo), así que se convierte antes de guardarlo. Aura-2 ya entrega MP3 mono
de 24 kHz y 48 kbps: ese no se toca.
"""

from __future__ import annotations

import io
import re
import unicodedata
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


# ---------------------------------------------------------------- texto para la voz

_MARCAS = re.compile(r"[*_#`~|<>\[\]{}]+")
_FINAL = (".", "!", "?", "…", "»", '"', ")")


def texto_para_narrar(texto: str) -> str:
    """Texto limpio para un narrador: sin emojis ni marcas, con espacios y puntuación sanos.

    Aura-2 pone las pausas y la entonación según la puntuación: frases completas, comas donde
    respira el narrador y un punto al final. El cuento ya viene así; esto quita lo que un
    modelo de texto a veces cuela (asteriscos, emojis, saltos de línea sueltos).
    """
    limpio = "".join(
        " " if unicodedata.category(c) in ("So", "Sk", "Cs", "Co", "Cn") else c for c in texto
    )
    limpio = limpio.replace("\u200d", "").replace("\ufe0f", "")
    limpio = _MARCAS.sub(" ", limpio)
    # Un salto de línea es una pausa: si la línea no cerraba frase, se cierra con punto.
    lineas = [ln.strip() for ln in limpio.splitlines() if ln.strip()]
    limpio = " ".join(ln if ln.endswith((*_FINAL, ",", ";", ":")) else ln + "." for ln in lineas)
    limpio = re.sub(r"\s+", " ", limpio).strip()
    limpio = re.sub(r"\s+([,.;:!?…])", r"\1", limpio)  # «hola ,» -> «hola,»
    limpio = re.sub(r"([,;:])(?=\S)", r"\1 ", limpio)  # «hola,amigo» -> «hola, amigo»
    limpio = re.sub(r"\.{2,}", "…", limpio)
    if limpio and not limpio.endswith(_FINAL):
        limpio += "."
    return limpio


# ---------------------------------------------------------------- duración de un MP3

_KBPS = {
    1: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),  # MPEG-1 capa III
    2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),  # MPEG-2 y 2.5
}
_HZ = {3: (44_100, 48_000, 32_000), 2: (22_050, 24_000, 16_000), 0: (11_025, 12_000, 8_000)}


def segundos_mp3(mp3: bytes) -> float:
    """Duración de un MP3 (capa III) sumando sus cuadros. 0 si no es un MP3 válido."""
    i = 0
    if mp3[:3] == b"ID3" and len(mp3) >= 10:
        i = 10 + ((mp3[6] << 21) | (mp3[7] << 14) | (mp3[8] << 7) | mp3[9])
    muestras_totales = 0
    hz_final = 0
    while i + 4 <= len(mp3):
        if mp3[i] != 0xFF or (mp3[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        version = (mp3[i + 1] >> 3) & 0x03  # 3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5
        capa = (mp3[i + 1] >> 1) & 0x03  # 1 = capa III
        indice_kbps = mp3[i + 2] >> 4
        indice_hz = (mp3[i + 2] >> 2) & 0x03
        relleno = (mp3[i + 2] >> 1) & 0x01
        if version == 1 or capa != 1 or indice_kbps in (0, 15) or indice_hz == 3:
            i += 1
            continue
        kbps = _KBPS[1 if version == 3 else 2][indice_kbps]
        hz = _HZ[version][indice_hz]
        muestras = 1152 if version == 3 else 576
        largo = muestras // 8 * kbps * 1000 // hz + relleno
        if largo <= 4:
            i += 1
            continue
        muestras_totales += muestras
        hz_final = hz
        i += largo
    return muestras_totales / hz_final if hz_final else 0.0
