import 'package:flutter/material.dart';

/// Paleta vibrante y botones grandes: la app la usan niños de 6 a 12 años.
/// El naranja y el azul salen del logo (`assets/marca/logo.png`).
abstract final class Colores {
  static const naranja = Color(0xFFFF6B35); // marca («Draw» y el lápiz); acción principal
  static const azul = Color(0xFF2E86AA); // marca (el trazo del logo)
  static const violeta = Color(0xFF7C5CBF); // voz de la IA
  static const amarillo = Color(0xFFFFD23F);
  static const crema = Color(0xFFFFF8F0);
  static const texto = Color(0xFF2D2D2D);
  static const verde = Color(0xFF2E9E4F); // confianza alta
  static const ambar = Color(0xFFF2A100); // confianza media
  static const rojo = Color(0xFFD64545); // confianza baja
  static const azulInfo = Color(0xFF2F7DE1); // información importante (no error)

  static const lienzo = <Color>[
    Color(0xFF212121),
    Color(0xFFE53935),
    Color(0xFFFF6B35),
    Color(0xFFFFD23F),
    Color(0xFF43A047),
    Color(0xFF29B6F6),
    Color(0xFF1565C0),
    Color(0xFF7C5CBF),
    Color(0xFFEC407A),
    Color(0xFF6D4C41),
  ];
}

/// Tamaño mínimo de cualquier cosa que se toca (más que los 48 dp de Material).
const double kToqueMinimo = 64;

ThemeData construirTema() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: Colores.naranja,
      secondary: Colores.azul,
      onSecondary: Colors.white,
      surface: Colores.crema,
    ),
  );
  return base.copyWith(
    scaffoldBackgroundColor: Colores.crema,
    textTheme: base.textTheme.apply(bodyColor: Colores.texto, displayColor: Colores.texto),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: Colores.naranja,
        foregroundColor: Colors.white,
        minimumSize: const Size(kToqueMinimo, kToqueMinimo),
        textStyle: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(minimumSize: const Size(kToqueMinimo, kToqueMinimo)),
    ),
  );
}
