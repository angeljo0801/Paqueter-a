from pathlib import Path

p = Path('app/lib/background_sync.dart')
s = p.read_text()
start_marker = '  static String friendlyError(Object error) {'
end_marker = '\n  }\n\n'
if s.count(start_marker) != 1:
    raise SystemExit('Gmail actionable errors: unexpected background service structure')
start = s.index(start_marker)
end = s.index(end_marker, start) + len(end_marker)
func = r'''  static String friendlyError(Object error) {
    final raw = '$error';
    final lower = raw.toLowerCase();
    if (lower.contains('no hay cuentas gmail autorizadas') ||
        lower.contains('no enabled gmail') ||
        lower.contains('no gmail') ||
        lower.contains('gmail is not connected')) {
      return 'No hay cuentas Gmail disponibles para este cliente. Comprueba las cuentas conectadas o vuelve a autorizarlas.';
    }
    if (lower.contains('gmail no terminó') ||
        lower.contains('algunos mensajes de gmail no pudieron leerse') ||
        lower.contains('no pudo completarse en todas las cuentas')) {
      return 'Gmail no terminó de revisar los mensajes. Es un error de lectura o de tiempo de espera, no significa que el tracking no exista. Puedes reintentar.';
    }
    if (lower.contains('429') || lower.contains('rate limit') ||
        lower.contains('quota exceeded') || lower.contains('user-rate-limit')) {
      return 'Gmail está limitando temporalmente las consultas. Espera unos minutos y vuelve a intentar.';
    }
    if (lower.contains('401') || lower.contains('403') ||
        lower.contains('invalid_grant') || lower.contains('unauthorized') ||
        lower.contains('insufficientpermissions') ||
        lower.contains('forbidden')) {
      return 'Gmail ha rechazado el acceso. Abre Correos conectados y vuelve a autorizar la cuenta afectada.';
    }
    if (lower.contains('api key') || lower.contains('app_api_key')) {
      return 'La clave del servidor de WhatsBot no es válida o falta.';
    }
    if (_transientNetworkError(error)) {
      return 'Se interrumpió la conexión con Gmail o Railway. La búsqueda puede continuar en segundo plano; vuelve a abrir el paquete para ver su estado.';
    }
    if (lower.contains('job') || lower.contains('trabajo') ||
        lower.contains('railway') || lower.contains('503') ||
        lower.contains('502')) {
      return 'El servidor de Gmail no pudo terminar esta búsqueda. Reintenta más tarde; no se ha marcado el tracking como no encontrado.';
    }
    return 'No se pudo completar la búsqueda de Gmail. Comprueba Correos conectados y vuelve a intentar.';
  }

'''
s=s[:start]+func+s[end:]
p.write_text(s)
print('Gmail v32 actionable errors applied.')
