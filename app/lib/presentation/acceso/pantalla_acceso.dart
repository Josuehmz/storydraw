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
  bool _verContrasena = false;
  String? _mensaje;
  bool _mensajeBueno = false;

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
          _mensajeBueno = true;
          _mensaje = 'Te enviamos un correo. Confirma la cuenta y luego inicia sesión.';
        });
      } else {
        await ref.read(sesionProvider.notifier).iniciar(_email.text.trim(), _contrasena.text);
      }
    } on ErrorApi catch (e) {
      setState(() {
        _mensajeBueno = false;
        _mensaje = _textoError(e);
      });
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
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
          children: [
            const _Marca(),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(Radios.grande),
                boxShadow: sombraSuave(),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  SegmentedButton<bool>(
                    showSelectedIcon: false,
                    segments: const [
                      ButtonSegment(value: false, label: Text('Entrar')),
                      ButtonSegment(value: true, label: Text('Crear cuenta')),
                    ],
                    selected: {_registro},
                    onSelectionChanged: (s) => setState(() {
                      _registro = s.first;
                      _mensaje = null;
                    }),
                  ),
                  const SizedBox(height: 18),
                  TextField(
                    key: const Key('campo-email'),
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    autocorrect: false,
                    decoration: const InputDecoration(
                      labelText: 'Correo',
                      prefixIcon: Icon(Icons.mail_outline, color: Colores.violeta),
                    ),
                  ),
                  const SizedBox(height: 14),
                  TextField(
                    key: const Key('campo-contrasena'),
                    controller: _contrasena,
                    obscureText: !_verContrasena,
                    decoration: InputDecoration(
                      labelText: 'Contraseña',
                      helperText: '10 caracteres o más',
                      prefixIcon: const Icon(Icons.lock_outline, color: Colores.violeta),
                      suffixIcon: IconButton(
                        tooltip: _verContrasena ? 'Ocultar contraseña' : 'Ver contraseña',
                        icon: Icon(_verContrasena ? Icons.visibility_off : Icons.visibility),
                        onPressed: () => setState(() => _verContrasena = !_verContrasena),
                      ),
                    ),
                  ),
                  if (_registro) ...[
                    const SizedBox(height: 14),
                    Material(
                      color: Colores.violeta.withValues(alpha: 0.08),
                      clipBehavior: Clip.antiAlias,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(Radios.medio),
                        side: BorderSide(color: Colores.violeta.withValues(alpha: 0.35)),
                      ),
                      child: CheckboxListTile(
                        key: const Key('consentimiento'),
                        value: _consiente,
                        activeColor: Colores.naranja,
                        onChanged: (v) => setState(() => _consiente = v ?? false),
                        controlAffinity: ListTileControlAffinity.leading,
                        title: const Text(
                          'Soy el padre, la madre o el tutor del niño y acepto que StoryDraw '
                          'guarde su apodo, su edad y los cuentos que cree. El dibujo no se '
                          'guarda nunca. Puedo borrar cualquier cuento, perfil o la cuenta '
                          'entera cuando quiera.',
                          style: TextStyle(fontSize: 14.5, height: 1.4),
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 18),
                  ElevatedButton(
                    key: const Key('boton-acceso'),
                    onPressed: puedeEnviar ? _enviar : null,
                    child: _cargando
                        ? const SizedBox(
                            width: 28,
                            height: 28,
                            child: CircularProgressIndicator(color: Colors.white, strokeWidth: 3),
                          )
                        : Text(_registro ? 'Crear cuenta' : 'Entrar'),
                  ),
                  if (_mensaje != null) ...[
                    const SizedBox(height: 14),
                    _Mensaje(texto: _mensaje!, bueno: _mensajeBueno),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Logo y nombre: un libro sobre un sello naranja, rodeado de estrellas.
class _Marca extends StatelessWidget {
  const _Marca();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        SizedBox(
          width: 150,
          height: 130,
          child: Stack(
            alignment: Alignment.center,
            children: [
              const Positioned(
                left: 6,
                top: 14,
                child: Icon(Icons.star_rounded, size: 30, color: Colores.amarillo),
              ),
              Positioned(
                right: 8,
                top: 4,
                child: Icon(
                  Icons.star_rounded,
                  size: 22,
                  color: Colores.violeta.withValues(alpha: 0.7),
                ),
              ),
              const Positioned(
                right: 14,
                bottom: 14,
                child: Icon(Icons.star_rounded, size: 26, color: Colores.amarillo),
              ),
              Container(
                width: 104,
                height: 104,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colores.naranja,
                  border: Border.all(color: Colors.white, width: 5),
                  boxShadow: sombraSuave(Colores.naranja),
                ),
                child: const Icon(Icons.auto_stories, size: 54, color: Colors.white),
              ),
            ],
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'StoryDraw',
          textAlign: TextAlign.center,
          style: Tipos.titulo.copyWith(fontSize: 42, color: Colores.naranja),
        ),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
          decoration: BoxDecoration(
            color: Colores.violeta.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(20),
          ),
          child: const Text(
            'Para padres, madres o tutores',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: Colores.violeta),
          ),
        ),
      ],
    );
  }
}

/// Resultado del intento: verde si salió bien, rojo si no, con icono además del color.
class _Mensaje extends StatelessWidget {
  const _Mensaje({required this.texto, required this.bueno});

  final String texto;
  final bool bueno;

  @override
  Widget build(BuildContext context) {
    final color = bueno ? Colores.verde : Colores.rojo;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        border: Border.all(color: color, width: 2),
        borderRadius: BorderRadius.circular(Radios.chico),
      ),
      child: Row(
        children: [
          Icon(bueno ? Icons.mark_email_read : Icons.error_outline, color: color, size: 28),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              texto,
              key: const Key('mensaje-acceso'),
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
