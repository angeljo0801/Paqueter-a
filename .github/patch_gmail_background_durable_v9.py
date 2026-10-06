from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# v9 fixes the remaining minimized-app race:
# keep a successful Gmail result durable until the package editor has actually
# applied/cached/persisted it, and keep checking briefly after app resume because
# WorkManager may finish a few seconds after the exact resume callback.

# ---------------------------------------------------------------------------
# Durable background result with explicit acknowledgement for package editor.
# ---------------------------------------------------------------------------
bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

bs = replace_once(
    bs,
    r'''  static Future<Map<String, dynamic>?> _readFinished(
    SharedPreferences prefs,
    String slot,
    String token,
  ) async {
''',
    r'''  static Future<Map<String, dynamic>?> _readFinished(
    SharedPreferences prefs,
    String slot,
    String token, {
    bool consume = true,
  }) async {
''',
    'readFinished consume flag',
)

bs = replace_once(
    bs,
    r'''          if (data is Map) {
            await prefs.remove(_pendingKey(slot));
            await prefs.remove(_resultKey(slot));
            await prefs.remove(_errorKey(slot));
            return Map<String, dynamic>.from(data);
          }
''',
    r'''          if (data is Map) {
            if (consume) {
              await prefs.remove(_pendingKey(slot));
              await prefs.remove(_resultKey(slot));
              await prefs.remove(_errorKey(slot));
            }
            return Map<String, dynamic>.from(data);
          }
''',
    'defer successful result cleanup',
)

if 'static Future<void> acknowledgeFinished({' not in bs:
    bs = replace_once(
        bs,
        r'''  static Future<bool> hasFinished({
''',
        r'''  static Future<void> acknowledgeFinished({
    String orderNumber = '',
    String tracking = '',
  }) async {
    final order = orderNumber.trim();
    final track = tracking.trim();
    if (order.isEmpty && track.isEmpty) return;
    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    final slot = _slot(order, track);
    await prefs.remove(_pendingKey(slot));
    await prefs.remove(_resultKey(slot));
    await prefs.remove(_errorKey(slot));
  }

  static Future<bool> hasFinished({
''',
        'background result acknowledgement',
    )

bs = replace_once(
    bs,
    r'''  static Future<Map<String, dynamic>> reconstruct({
    String baseUrl = '',
    String apiKey = '',
    String orderNumber = '',
    String tracking = '',
  }) async {
''',
    r'''  static Future<Map<String, dynamic>> reconstruct({
    String baseUrl = '',
    String apiKey = '',
    String orderNumber = '',
    String tracking = '',
    bool autoAcknowledge = true,
  }) async {
''',
    'auto acknowledge option',
)

bs = replace_once(
    bs,
    '      final recovered = await _readFinished(prefs, slot, token);\n',
    '      final recovered = await _readFinished(prefs, slot, token, consume: autoAcknowledge);\n',
    'recover without consuming package result',
)
bs = replace_once(
    bs,
    '        final recovered = await _readFinished(prefs, slot, token);\n',
    '        final recovered = await _readFinished(prefs, slot, token, consume: autoAcknowledge);\n',
    'poll without consuming package result',
)

# Persist a foreground success too. Otherwise Android can suspend the UI after
# the request returns but before the editor has added/cached the photos.
bs = replace_once(
    bs,
    r'''      await prefs.reload();
      final latest = prefs.getString(pendingKey) ?? '';
      if (latest.contains('"token":"$token"')) {
        await prefs.remove(pendingKey);
        await prefs.remove(_resultKey(slot));
        await prefs.remove(_errorKey(slot));
      }
      return data;
''',
    r'''      await prefs.reload();
      final latest = prefs.getString(pendingKey) ?? '';
      if (latest.contains('"token":"$token"')) {
        await prefs.setString(
          _resultKey(slot),
          jsonEncode({
            'token': token,
            'completedAt': DateTime.now().toIso8601String(),
            'data': data,
          }),
        );
        await prefs.remove(_errorKey(slot));
        if (autoAcknowledge) {
          await prefs.remove(pendingKey);
          await prefs.remove(_resultKey(slot));
        }
      }
      return data;
''',
    'persist foreground result before UI resumes',
)

bg_path.write_text(bs)


# ---------------------------------------------------------------------------
# Package editor recovery and immediate persistence.
# ---------------------------------------------------------------------------
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

ps = replace_once(
    ps,
    r'''      final data = await GmailBackgroundSearch.reconstruct(
        baseUrl: gmailBackendUrl,
        apiKey: gmailApiKey,
        orderNumber: order,
        tracking: track,
      );
''',
    r'''      final data = await GmailBackgroundSearch.reconstruct(
        baseUrl: gmailBackendUrl,
        apiKey: gmailApiKey,
        orderNumber: order,
        tracking: track,
        autoAcknowledge: false,
      );
''',
    'package durable Gmail call',
)

ps = replace_once(
    ps,
    '  bool _recoveringFinishedGmailSearch = false;\n\n',
    r'''  bool _recoveringFinishedGmailSearch = false;
  Timer? _gmailRecoveryPoll;

  void _startGmailRecoveryWatch() {
    _gmailRecoveryPoll?.cancel();
    var attempts = 0;
    _gmailRecoveryPoll = Timer.periodic(const Duration(seconds: 2), (timer) async {
      attempts++;
      if (!mounted || attempts > 45) {
        timer.cancel();
        return;
      }
      if (gmailLoading || _recoveringFinishedGmailSearch) return;
      final track = tracking.text.trim();
      final order = gmailOrder.text.trim();
      if (track.isEmpty && order.isEmpty) return;
      final ready = await GmailBackgroundSearch.hasFinished(
        orderNumber: order,
        tracking: track,
      );
      if (!ready || !mounted) return;
      timer.cancel();
      await _recoverFinishedGmailSearch();
    });
  }

''',
    'Gmail recovery polling state',
)

ps = replace_once(
    ps,
    r'''  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    init();
  }
''',
    r'''  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    init();
    _startGmailRecoveryWatch();
  }
''',
    'start Gmail recovery watcher',
)

ps = replace_once(
    ps,
    r'''  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
''',
    r'''  void dispose() {
    _gmailRecoveryPoll?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
''',
    'cancel Gmail recovery watcher',
)

ps = replace_once(
    ps,
    r'''    if (state == AppLifecycleState.resumed) {
      Future<void>.delayed(
        const Duration(milliseconds: 250),
        _recoverFinishedGmailSearch,
      );
    }
''',
    r'''    if (state == AppLifecycleState.resumed) {
      _startGmailRecoveryWatch();
      Future<void>.delayed(
        const Duration(milliseconds: 250),
        _recoverFinishedGmailSearch,
      );
    }
''',
    'watch Gmail result after resume',
)

persist_method = r'''
  Future<void> _persistRecoveredGmailSnapshot() async {
    final rows = await Store.list('packages');
    final existingId = '${widget.existing?['id'] ?? ''}'.trim();
    final track = tracking.text.trim();
    var index = -1;
    if (existingId.isNotEmpty) {
      index = rows.indexWhere((e) => '${e['id'] ?? ''}' == existingId);
    }
    if (index < 0 && track.isNotEmpty) {
      index = rows.indexWhere(
        (e) => '${e['tracking'] ?? ''}'.trim().toLowerCase() == track.toLowerCase(),
      );
    }
    if (index < 0) return;
    final current = Map<String, dynamic>.from(rows[index]);
    rows[index] = {
      ...current,
      'gmailStore': gmailStore.text.trim(),
      'gmailOrderNumber': gmailOrder.text.trim(),
      'gmailStatus': gmailStatus.text.trim(),
      'gmailEstimatedDelivery': gmailEta.text.trim(),
      'emailPhotoUrls': List<String>.from(emailPhotoUrls),
      'emailAttachmentImages': emailAttachmentImages.map((e) => Map<String, dynamic>.from(e)).toList(),
      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),
      'gmailOfflinePhotoPaths': Map<String, String>.from(gmailOfflinePhotoPaths),
      'gmailRejectedImages': gmailRejectedImages.map((e) => Map<String, dynamic>.from(e)).toList(),
      'gmailSourceEmails': List<String>.from(gmailSourceEmails),
      'gmailItems': gmailItems.map((e) => Map<String, dynamic>.from(e)).toList(),
      'hiddenGmailItemKeys': hiddenGmailItemKeys.toList(),
      'gmailOcrScannedUrls': gmailOcrScannedUrls.toList(),
      'gmailLinkedAt': DateTime.now().toIso8601String(),
    };
    await Store.saveList('packages', rows);
  }

'''
if '_persistRecoveredGmailSnapshot()' not in ps:
    ps = replace_once(
        ps,
        '  Future<void> removeMultipleEmailPhotos() async {\n',
        persist_method + '  Future<void> removeMultipleEmailPhotos() async {\n',
        'persist recovered Gmail package snapshot',
    )

# Anchor only on the OCR merge call. Requiring the smart-filter line immediately
# before it was too brittle because later photo patches can insert code between.
ps = replace_once(
    ps,
    '      await _mergeItemsFromEmailImageOcr();\n',
    r'''      await _mergeItemsFromEmailImageOcr();
      await _persistRecoveredGmailSnapshot();
      await GmailBackgroundSearch.acknowledgeFinished(
        orderNumber: gmailOrder.text.trim(),
        tracking: tracking.text.trim(),
      );
''',
    'persist then acknowledge Gmail reconstruction',
)

ps = replace_once(
    ps,
    r'''      if (data['_backgroundPending'] == true) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('${data['_message'] ?? 'La búsqueda continúa en segundo plano.'}')),
          );
        }
        return;
      }
''',
    r'''      if (data['_backgroundPending'] == true) {
        _startGmailRecoveryWatch();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('${data['_message'] ?? 'La búsqueda continúa en segundo plano.'}')),
          );
        }
        return;
      }
''',
    'poll pending Gmail result',
)

packages_path.write_text(ps)

print('Gmail v9 applied: background result remains durable until photos are applied and persisted; recovery keeps polling after resume.')
