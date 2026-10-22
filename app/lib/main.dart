import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'application/proveedores.dart';
import 'data/cache_cuentos.dart';
import 'data/sesion_local.dart';
import 'presentation/app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Hive.initFlutter();
  final cache = await CacheCuentos.abrir();
  final prefs = await SharedPreferences.getInstance();

  runApp(
    ProviderScope(
      // Los reintentos de red los hace Dio; Riverpod no reintenta por su cuenta.
      retry: (_, _) => null,
      overrides: [
        sesionLocalProvider.overrideWithValue(SesionLocal(prefs)),
        cacheProvider.overrideWithValue(cache),
      ],
      child: const StoryDrawApp(),
    ),
  );
}
