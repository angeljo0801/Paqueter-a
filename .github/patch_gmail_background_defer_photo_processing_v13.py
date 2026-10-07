from pathlib import Path

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)

p = Path('app/lib/packages.dart')
s = p.read_text()

# v13: the Gmail HTTP result can finish while the Activity is paused. The raw
# reconstruction is safely persisted by GmailBackgroundSearch, but image OCR /
# downloads / ML Kit must not run while Paqueteria is minimized. Previously the
# UI isolate could finish that post-processing in background, save an empty
# accepted-photo list, acknowledge the durable result, and leave nothing to
# recover when the user returned.

watch_old = r'''      if (!loaded ||
          gmailBackendUrl.trim().isEmpty ||
          gmailApiKey.trim().isEmpty ||
          gmailLoading ||
          _recoveringFinishedGmailSearch) {
        return;
      }
'''
watch_new = r'''      if (WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed ||
          !loaded ||
          gmailBackendUrl.trim().isEmpty ||
          gmailApiKey.trim().isEmpty ||
          gmailLoading ||
          _recoveringFinishedGmailSearch) {
        return;
      }
'''
s = replace_once(s, watch_old, watch_new, 'background polling only while resumed')

recover_old = r'''    if (!mounted ||
        !loaded ||
        gmailBackendUrl.trim().isEmpty ||
        gmailApiKey.trim().isEmpty ||
        gmailLoading ||
        _recoveringFinishedGmailSearch) {
      return;
    }
'''
recover_new = r'''    if (!mounted ||
        WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed ||
        !loaded ||
        gmailBackendUrl.trim().isEmpty ||
        gmailApiKey.trim().isEmpty ||
        gmailLoading ||
        _recoveringFinishedGmailSearch) {
      return;
    }
'''
s = replace_once(s, recover_old, recover_new, 'finished-result recovery only while resumed')

request_anchor = r'''      final data = await GmailBackgroundSearch.reconstruct(
        baseUrl: gmailBackendUrl,
        apiKey: gmailApiKey,
        orderNumber: order,
        tracking: track,
        autoAcknowledge: false,
      );
'''
request_new = request_anchor + r'''      // If Android paused the app while Gmail was searching, leave the durable
      // raw result untouched. didChangeAppLifecycleState / the recovery watcher
      // will apply, filter, cache and persist its photos after we are visible.
      if (WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
        _startGmailRecoveryWatch();
        return;
      }
'''
s = replace_once(s, request_anchor, request_new, 'defer background-finished result until resume')

post_filter_old = r'''      await _mergeItemsFromEmailImageOcr();
      await _smartFilterAndCacheGmailPhotos();

      // Only mark the background result as consumed after the final accepted
'''
post_filter_new = r'''      await _mergeItemsFromEmailImageOcr();
      if (WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
        _startGmailRecoveryWatch();
        return;
      }
      await _smartFilterAndCacheGmailPhotos();
      if (WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
        _startGmailRecoveryWatch();
        return;
      }

      // Only mark the background result as consumed after the final accepted
'''
s = replace_once(s, post_filter_old, post_filter_new, 'never acknowledge photos processed while paused')

# If photo preparation itself returns after the app was minimized, don't replace
# the visible photo collections with an empty/partial result.
filter_apply_old = r'''    final offline = result['offlinePaths'];
    if (!mounted) return;
    setState(() {
'''
filter_apply_new = r'''    final offline = result['offlinePaths'];
    if (!mounted ||
        WidgetsBinding.instance.lifecycleState != AppLifecycleState.resumed) {
      return;
    }
    setState(() {
'''
s = replace_once(s, filter_apply_old, filter_apply_new, 'do not apply photo filter result while paused')

p.write_text(s)
print('Gmail v13 applied: background lookup keeps raw result durable; photo OCR/cache/persistence waits until app resumes.')
