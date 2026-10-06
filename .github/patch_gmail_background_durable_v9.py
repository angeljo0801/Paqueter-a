from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


# v9 fixes the remaining minimized-app race:
# - a foreground request can finish while Android is suspending the UI. Older
#   code deleted the durable WorkManager result before the editor had actually
#   applied/cached the photos;
# - a result can finish a few seconds AFTER the app is resumed, so a single
#   lifecycle check is not enough.
# Keep the result durable until the package editor explicitly acknowledges it,
# poll briefly after resume, and persist the recovered Gmail snapshot into the
# package immediately after photos/items are applied.

# ---------------------------------------------------------------------------
# Durable background result with explicit acknowledgement for package editor.
# ---------------------------------------------------------------------------
bg_path = Path('app/lib/background_sync.dart')
bs = bg_path.read_text()

old_read_sig = r'''  static Future<Map<String, dynamic>?> _readFinished(
    SharedPreferences prefs,
    String slot,
    String token,
  ) async {
'''
new_read_sig = r'''  static Future<Map<String, dynamic>?> _readFinished(
    SharedPreferences prefs,
    String slot,
    String token, {
    bool consume = true,
  }) async {
'''
bs = replace_once(bs, old_read_sig, new_read_sig, 'readFinished consume flag')

old_success_consume = r'''          if (data is Map) {
            await prefs.remove(_pendingKey(slot));
            await prefs.remove(_resultKey(slot));
            await prefs.remove(_errorKey(slot));
            return Map<String, dynamic>.from(data);
          }
'''
new_success_consume = r'''          if (data is Map) {
            if (consume) {
              await prefs.remove(_pendingKey(slot));
              await prefs.remove(_resultKey(slot));
              await prefs.remove(_errorKey(slot));
            }
            return Map<String, dynamic>.from(data);
          }
'''
bs = replace_once(bs, old_success_consume, new_success_consume, 'defer successful result cleanup')

has_finished_anchor = r'''  static Future<bool> hasFinished({
'''
ack_method = r'''  static Future<void> acknowledgeFinished({
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

'''
if 'static Future<void> acknowledgeFinished({' not in bs:
    bs = replace_once(bs, has_finished_anchor, ack_method + has_finished_anchor, 'background result acknowledgement')

old_reconstruct_sig = r'''  static Future<Map<String, dynamic>> reconstruct({
    String baseUrl = '',
    String apiKey = '',
    String orderNumber = '',
    String tracking = '',
  }) async {
'''
new_reconstruct_sig = r'''  static Future<Map<String, dynamic>> reconstruct({
    String baseUrl = '',
    String apiKey = '',
    String orderNumber = '',
    String tracking = '',
    bool autoAcknowledge = true,
  }) async {
'''
bs = replace_once(bs, old_reconstruct_sig, new_reconstruct_sig, 'auto acknowledge option')

bs = replace_once(
    bs,
    '      final recovered = await _readFinished(prefs, slot, token);\n',
    '      final recovered = await _readFinished(prefs, slot, token, consume: autoAcknowledge);\n',
    'recover without consuming package result',
)

# The second occurrence is inside the direct-error polling loop.
old_poll = '        final recovered = await _readFinished(prefs, slot, token);\n'
new_poll = '        final recovered = await _readFinished(prefs, slot, token, consume: autoAcknowledge);\n'
bs = replace_once(bs, old_poll, new_poll, 'poll without consuming package result')

# v7 changed _request -> _requestWithRetry. Persist the direct response BEFORE
# returning so suspension between network completion and UI application cannot
# lose the photos. Package lookups leave it pending until UI acknowledgement;
# other callers keep the old consume-on-return behavior.
old_direct_success = r'''      await prefs.reload();
      final latest = prefs.getString(pendingKey) ?? '';
      if (latest.contains('"token":"$token"')) {
        await prefs.remove(pendingKey);
        await prefs.remove(_resultKey(slot));
        await prefs.remove(_errorKey(slot));
      }
      return data;
'''
new_direct_success = r'''      await prefs.reload();
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
'''
bs = replace_once(bs, old_direct_success, new_direct_success, 'persist foreground result before UI resumes')
bg_path.write_text(bs)


# ---------------------------------------------------------------------------
# Package editor: keep durable result until photos are actually processed,
# watch for a result that completes after resume, and persist Gmail state now.
# ---------------------------------------------------------------------------
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

# Package reconstruction owns acknowledgement; purchase/order lookups keep the
# default autoAcknowledge=true behavior.
old_package_call = r'''      final data = await GmailBackgroundSearch.reconstruct(
        baseUrl: gmailBackendUrl,
        apiKey: gmailApiKey,
        orderNumber: order,
        tracking: track,
      );
'''
new_package_call = r'''      final data = await GmailBackgroundSearch.reconstruct(
        baseUrl: gmailBackendUrl,
        apiKey: gmailApiKey,
        orderNumber: order,
        tracking: track,
        autoAcknowledge: false,
      );
'''
ps = replace_once(ps, old_package_call, new_package_call, 'package durable Gmail call')

# v8 already installed lifecycle observation. Add a short result watcher because
# WorkManager can finish after the exact resumed callback has already fired.
old_recovery_flag = '  bool _recoveringFinishedGmailSearch = false;\n\n'
new_recovery_flag = r'''  bool _recoveringFinishedGmailSearch = false;
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

'''
ps = replace_once(ps, old_recovery_flag, new_recovery_flag, 'Gmail recovery polling state')

old_init = r'''  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    init();
  }
'''
new_init = r'''  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    init();
    _startGmailRecoveryWatch();
  }
'''
ps = replace_once(ps, old_init, new_init, 'start Gmail recovery watcher')

old_dispose = r'''  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
'''
new_dispose = r'''  void dispose() {
    _gmailRecoveryPoll?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }
'''
ps = replace_once(ps, old_dispose, new_dispose, 'cancel Gmail recovery watcher')

old_resumed = r'''    if (state == AppLifecycleState.resumed) {
      Future<void>.delayed(
        const Duration(milliseconds: 250),
        _recoverFinishedGmailSearch,
      );
    }
'''
new_resumed = r'''    if (state == AppLifecycleState.resumed) {
      _startGmailRecoveryWatch();
      Future<void>.delayed(
        const Duration(milliseconds: 250),
        _recoverFinishedGmailSearch,
      );
    }
'''
ps = replace_once(ps, old_resumed, new_resumed, 'watch Gmail result after resume')

# Keep the one-shot recovery conservative; the periodic watcher retries as soon
# as gmailLoading becomes false instead of missing the finished result forever.

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
method_anchor = '  Future<void> removeMultipleEmailPhotos() async {\n'
if '_persistRecoveredGmailSnapshot()' not in ps:
    ps = replace_once(ps, method_anchor, persist_method + method_anchor, 'persist recovered Gmail package snapshot')

# Do not claim success until the filtered photos/items have been applied and the
# package snapshot is durable. Then acknowledge/erase the WorkManager result.
old_after_processing = r'''      await _smartFilterAndCacheGmailPhotos();
      await _mergeItemsFromEmailImageOcr();
'''
new_after_processing = r'''      await _smartFilterAndCacheGmailPhotos();
      await _mergeItemsFromEmailImageOcr();
      await _persistRecoveredGmailSnapshot();
      await GmailBackgroundSearch.acknowledgeFinished(
        orderNumber: gmailOrder.text.trim(),
        tracking: tracking.text.trim(),
      );
'''
ps = replace_once(ps, old_after_processing, new_after_processing, 'persist then acknowledge Gmail reconstruction')

# If a direct attempt returns "background pending", continue polling while the
# editor is visible instead of relying on another minimize/resume cycle.
pending_anchor = r'''      if (data['_backgroundPending'] == true) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('${data['_message'] ?? 'La búsqueda continúa en segundo plano.'}')),
          );
        }
        return;
      }
'''
pending_new = r'''      if (data['_backgroundPending'] == true) {
        _startGmailRecoveryWatch();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('${data['_message'] ?? 'La búsqueda continúa en segundo plano.'}')),
          );
        }
        return;
      }
'''
ps = replace_once(ps, pending_anchor, pending_new, 'poll pending Gmail result')

packages_path.write_text(ps)

print('Gmail v9 applied: background result is durable until UI applies it, recovery polls after resume, and recovered package data is persisted immediately.')
