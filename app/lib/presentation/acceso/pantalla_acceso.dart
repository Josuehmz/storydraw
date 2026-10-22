import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/proveedores.dart';
import '../../core/errores.dart';
import '../../core/tema.dart';

/// Zona del adulto: crear la cuenta con consentimiento previo o iniciar sesión.
class PantallaAcceso extends ConsumerStatefulWidget {
  const PantallaAcceso({super.key});

  @override
  ConsumerState<PantallaAcceso> createState() => _PantallaAccesoState();
}

class _PantallaAccesoState extends ConsumerState<PantallaAcceso> {
  final _email = TextEditingController();
  final _contrasena = TextEditingController();
  bool _registro = false;
  bool _consiente = false;
  bool _cargando = false;
  String? _mensaje;

  @override
  void dispose() {
    _email.dispose();
    _contrasena.dispose();
    super.dispose();
  }

  String _textoError(ErrorApi e) => switch (e.tipo) {
    TipoError.correoSinVerificar => 'Primero confirma tu correo con el enlace que te enviamos.',
    TipoError.sesionVencida => 'Correo o contraseña incorrectos.',
    TipoError.conflicto => 'Ese correo ya tiene una cuenta. Inicia sesión.',
    TipoError.datosInvalidos => 'Revisa el correo y usa una contraseña de 10 caracteres o más.',
    TipoError.limite => 'Demasiados intentos. Espera un minuto.',
    TipoError.sinConexion => 'No hay conexión con StoryDraw.',
    _ => 'Algo falló. Inténtalo de nuevo.',
  };

  Future<void> _enviar() async {
    setState(() {
      _cargando = true;
      _mensaje = null;
    });
    try {
      if (_registro) {
        await ref
            .read(cuentasRepositorioProvider)
            .registrar(
              email: _email.text.trim(),
              contrasena: _contrasena.text,
              aceptaConsentimiento: _consiente,
            );
        setState(() {
          _registro = false;
          _mensaje = 'Te enviamos un correo. Confirma la cuenta y luego inicia sesión.';
        });
      } else {
        await ref.read(sesionProvider.notifier).iniciar(_email.text.trim(), _contrasena.text);
      }
    } on ErrorApi catch (e) {
      setState(() => _mensaje = _textoError(e));
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final puedeEnviar = !_cargando && (!_registro || _consiente);
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const Icon(Icons.auto_stories, size: 96, color: Colores.naranja),
            const Text(
              'StoryDraw',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 34, fontWeight: FontWeight.w900),
            ),
            const Text(
              'Para padres, madres o tutores',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16),
            ),
            const SizedBox(height: 24),
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(value: false, label: Text('Entrar')),
                ButtonSegment(value: true, label: Text('Crear cuenta')),
              ],
              selected: {_registro},
              onSelectionChanged: (s) => setState(() => _registro = s.first),
            ),
            const SizedBox(height: 16),
            TextField(
              key: const Key('campo-email'),
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              decoration: const InputDecoration(labelText: 'Correo', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              key: const Key('campo-contrasena'),
              controller: _contrasena,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Contraseña (10 caracteres o más)',
                border: OutlineInputBorder(),
              ),
            ),
            if (_registro) ...[
              const SizedBox(height: 12),
              CheckboxListTile(
                key: const Key('consentimiento'),
                value: _consiente,
                onChanged: (v) => setState(() => _consiente = v ?? false),
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text(
                  'Soy el padre, la madre o el tutor del niño y acepto que StoryDraw guarde su '
                  'apodo, su edad y los cuentos que cree. El dibujo no se guarda nunca. '
                  'Puedo borrar cualquier cuento, perfil o la cuenta entera cuando quiera.',
                ),
              ),
            ],
            const SizedBox(height: 16),
            ElevatedButton(
              key: const Key('boton-acceso'),
              onPressed: puedeEnviar ? _enviar : null,
              child: _cargando
                  ? const CircularProgressIndicator(color: Colors.white)
                  : Text(_registro ? 'Crear cuenta' : 'Entrar'),
            ),
            if (_mensaje != null) ...[
              const SizedBox(height: 16),
              Text(_mensaje!, key: const Key('mensaje-acceso'), textAlign: TextAlign.center),
            ],
          ],
        ),
      ),
    );
  }
}
