from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# v16: the tap itself starts the durable Railway job before WorkManager scheduling
# or any long foreground request. WorkManager remains an immediate safety net.
bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

helper_anchor = r'''  static Future<Map<String, dynamic>> _requestServerJob({
'''
start_helper = r'''  static Future<void> _startServerJobNow({
    required String baseUrl,
    required String apiKey,
    required String orderNumber,
    required String tracking,
    required String token,
  }) async {
    final base = baseUrl.trim().replaceAll(RegExp(r'/$'), '');
    if (base.isEmpty || apiKey.trim().isEmpty) return;
    final params = <String, String>{
      if (tracking.trim().isNotEmpty) 'tracking': tracking.trim(),
      if (tracking.trim().isEmpty && orderNumber.trim().isNotEmpty)
        'order_number': orderNumber.trim(),
      'client_token': token,
    };
    final uri = Uri.parse('$base/api/gmail/reconstruct/jobs')
        .replace(queryParameters: params);
    final response = await http.post(
      uri,
      headers: {'x-api-key': apiKey.trim()},
    ).timeout(const Duration(seconds: 12));
    if (response.statusCode == 404 || response.statusCode == 405) {
      // Compatibility with an older backend: the direct request below will
      // still start the reconstruction.
      return;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception(response.body);
    }
  }

'''
if 'static Future<void> _startServerJobNow({' not in bs:
    bs = replace_once(
        bs,
        helper_anchor,
        start_helper + helper_anchor,
        'immediate Railway job starter',
    )

# Remove the old 8-second WorkManager delay. The same client token makes the
# foreground call and WorkManager idempotently join one Railway job.
old_delay = "            initialDelay: const Duration(seconds: 8),\n"
if old_delay in bs:
    bs = bs.replace(old_delay, '', 1)

# Start Railway immediately after the durable local pending record is written,
# before asking Android to enqueue its background safety net.
registration_anchor = r'''      await prefs.remove(_resultKey(slot));
      await prefs.remove(_errorKey(slot));
      if (backgroundAvailable) {
'''
registration_new = r'''      await prefs.remove(_resultKey(slot));
      await prefs.remove(_errorKey(slot));

      // This is deliberately before WorkManager. Tapping Buscar starts the
      // server job now instead of waiting for Android's scheduler.
      try {
        await _startServerJobNow(
          baseUrl: base,
          apiKey: key,
          orderNumber: order,
          tracking: track,
          token: token,
        );
      } catch (_) {
        // WorkManager/direct retry below remains the safety net.
      }

      if (backgroundAvailable) {
'''
bs = replace_once(
    bs,
    registration_anchor,
    registration_new,
    'start Railway job before WorkManager scheduling',
)

# Foreground waits on the exact same durable Railway job rather than starting a
# second /reconstruct request. This also means minimizing immediately is safe.
reconstruct_start = bs.find('  static Future<Map<String, dynamic>> reconstruct({')
reconstruct_end = bs.find("\n  static String _upgradeKey(", reconstruct_start)
if reconstruct_end < 0:
    reconstruct_end = bs.find("\n  @pragma('vm:entry-point')\n  static Future<bool> execute(", reconstruct_start)
if reconstruct_start < 0 or reconstruct_end < 0:
    raise SystemExit('No se encontró bloque reconstruct de Gmail')
block = bs[reconstruct_start:reconstruct_end]
block = replace_once(
    block,
    r'''      final data = await _requestWithRetry(
        baseUrl: base,
        apiKey: key,
        orderNumber: order,
        tracking: track,
      );
''',
    r'''      final data = await _requestServerJob(
        baseUrl: base,
        apiKey: key,
        orderNumber: order,
        tracking: track,
        token: token,
      );
''',
    'foreground joins durable Railway job',
)
bs = bs[:reconstruct_start] + block + bs[reconstruct_end:]
bg_path.write_text(bs)


# Immediate visual confirmation: spinner/snackbar happen before reading config.
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

old_start = r'''    gmailBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();
    gmailApiKey = await WhatsBotPurchaseSyncService.apiKey();
    if (gmailApiKey.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Falta la API key del servidor de WhatsBot en Configuración.')),
      );
      return;
    }
    setState(() => gmailLoading = true);
'''
new_start = r'''    if (mounted) {
      setState(() => gmailLoading = true);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Búsqueda de Gmail iniciada…'),
          duration: Duration(seconds: 1),
        ),
      );
    }
    gmailBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();
    gmailApiKey = await WhatsBotPurchaseSyncService.apiKey();
    if (gmailApiKey.isEmpty) {
      if (!mounted) return;
      setState(() => gmailLoading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Falta la API key del servidor de WhatsBot en Configuración.')),
      );
      return;
    }
'''
ps = replace_once(
    ps,
    old_start,
    new_start,
    'immediate Gmail tap feedback',
)

packages_path.write_text(ps)

print('Gmail v16 applied: tap starts Railway immediately; WorkManager has no artificial delay.')
