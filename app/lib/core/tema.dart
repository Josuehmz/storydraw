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

/// Esquinas redondeadas: una escala corta para que todo se sienta de la misma familia.
abstract final class Radios {
  static const double chico = 16;
  static const double medio = 20;
  static const double grande = 28;
}

/// Tipografía: Fredoka (redondeada y juguetona) para títulos y botones; Nunito para leer.
abstract final class Tipos {
  static const _titulo = 'Fredoka';

  /// Título grande de una pantalla o del cuento.
  static const titulo = TextStyle(fontFamily: _titulo, fontSize: 28, fontWeight: FontWeight.w600);

  /// Subtítulo o etiqueta destacada.
  static const subtitulo = TextStyle(
    fontFamily: _titulo,
    fontSize: 22,
    fontWeight: FontWeight.w500,
  );

  /// Texto de botón.
  static const boton = TextStyle(fontFamily: _titulo, fontSize: 20, fontWeight: FontWeight.w600);
}

/// Sombra suave y cálida, para que las cosas se vean «de bulto» sin ser pesadas.
List<BoxShadow> sombraSuave([Color color = Colores.texto]) => [
  BoxShadow(color: color.withValues(alpha: 0.16), blurRadius: 12, offset: const Offset(0, 5)),
];

ThemeData construirTema() {
  final esquema = ColorScheme.fromSeed(
    seedColor: Colores.naranja,
    surface: Colores.crema,
  ).copyWith(primary: Colores.naranja, secondary: Colores.violeta, error: Colores.rojo);
  final base = ThemeData(useMaterial3: true, colorScheme: esquema, fontFamily: 'Nunito');
  final texto = base.textTheme.apply(bodyColor: Colores.texto, displayColor: Colores.texto);

  RoundedRectangleBorder forma(double radio) =>
      RoundedRectangleBorder(borderRadius: BorderRadius.circular(radio));
  OutlineInputBorder borde(Color color, double ancho) => OutlineInputBorder(
    borderRadius: BorderRadius.circular(Radios.medio),
    borderSide: BorderSide(color: color, width: ancho),
  );

  return base.copyWith(
    scaffoldBackgroundColor: Colores.crema,
    textTheme: texto.copyWith(
      headlineLarge: texto.headlineLarge?.merge(Tipos.titulo),
      headlineMedium: texto.headlineMedium?.merge(Tipos.titulo),
      headlineSmall: texto.headlineSmall?.merge(Tipos.titulo),
      titleLarge: texto.titleLarge?.merge(Tipos.subtitulo),
      titleMedium: texto.titleMedium?.merge(Tipos.subtitulo),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colores.crema,
      foregroundColor: Colores.texto,
      surfaceTintColor: Colors.transparent,
      centerTitle: true,
      titleTextStyle: TextStyle(
        fontFamily: 'Fredoka',
        fontSize: 24,
        fontWeight: FontWeight.w600,
        color: Colores.texto,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: Colores.naranja,
        foregroundColor: Colors.white,
        elevation: 4,
        shadowColor: Colores.naranja.withValues(alpha: 0.5),
        minimumSize: const Size(kToqueMinimo, kToqueMinimo),
        padding: const EdgeInsets.symmetric(horizontal: 28),
        textStyle: Tipos.boton,
        shape: forma(Radios.medio),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: Colores.naranja,
        foregroundColor: Colors.white,
        minimumSize: const Size(kToqueMinimo, 52),
        padding: const EdgeInsets.symmetric(horizontal: 24),
        textStyle: Tipos.boton,
        shape: forma(Radios.medio),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: Colores.naranja,
        minimumSize: const Size(kToqueMinimo, kToqueMinimo),
        side: const BorderSide(color: Colores.naranja, width: 3),
        textStyle: Tipos.boton,
        shape: forma(Radios.medio),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: Colores.violeta,
        minimumSize: const Size(kToqueMinimo, 52),
        textStyle: Tipos.boton,
        shape: forma(Radios.medio),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(minimumSize: const Size(kToqueMinimo, kToqueMinimo)),
    ),
    floatingActionButtonTheme: FloatingActionButtonThemeData(
      backgroundColor: Colores.naranja,
      foregroundColor: Colors.white,
      elevation: 6,
      shape: forma(Radios.grande),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 18),
      border: borde(Colores.violeta.withValues(alpha: 0.35), 2),
      enabledBorder: borde(Colores.violeta.withValues(alpha: 0.35), 2),
      focusedBorder: borde(Colores.naranja, 3),
      errorBorder: borde(Colores.rojo, 2),
      focusedErrorBorder: borde(Colores.rojo, 3),
      labelStyle: const TextStyle(fontWeight: FontWeight.w600),
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      elevation: 3,
      shadowColor: Colores.texto.withValues(alpha: 0.25),
      surfaceTintColor: Colors.transparent,
      shape: forma(Radios.medio),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: Colores.crema,
      surfaceTintColor: Colors.transparent,
      shape: forma(Radios.grande),
      titleTextStyle: Tipos.subtitulo.copyWith(color: Colores.texto),
    ),
    chipTheme: ChipThemeData(
      selectedColor: Colores.naranja,
      backgroundColor: Colors.white,
      labelStyle: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
      secondaryLabelStyle: const TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.w700,
        color: Colors.white,
      ),
      checkmarkColor: Colors.white,
      side: const BorderSide(color: Colores.naranja, width: 2),
      shape: forma(Radios.chico),
      padding: const EdgeInsets.all(10),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        minimumSize: const Size(kToqueMinimo, 52),
        textStyle: Tipos.boton.copyWith(fontSize: 18),
        selectedBackgroundColor: Colores.naranja,
        selectedForegroundColor: Colors.white,
        side: const BorderSide(color: Colores.naranja, width: 2),
      ),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: Colores.naranja),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: Colores.texto,
      shape: forma(Radios.chico),
    ),
  );
}
