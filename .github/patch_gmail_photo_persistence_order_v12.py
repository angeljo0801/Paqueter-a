from pathlib import Path

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)

p = Path('app/lib/packages.dart')
s = p.read_text()

# v12 fixes the actual persistence ordering bug. v2 intentionally runs image OCR
# before the smart photo filter, but v9 later inserted persistence/ack immediately
# after that OCR call. That meant a background result was considered consumed and
# saved BEFORE accepted/rejected photos and offline paths were finalized.
old = r'''      await _mergeItemsFromEmailImageOcr();
      await _persistRecoveredGmailSnapshot();
      await GmailBackgroundSearch.acknowledgeFinished(
        orderNumber: gmailOrder.text.trim(),
        tracking: tracking.text.trim(),
      );
      await _smartFilterAndCacheGmailPhotos();
'''
new = r'''      await _mergeItemsFromEmailImageOcr();
      await _smartFilterAndCacheGmailPhotos();

      // Only mark the background result as consumed after the final accepted
      // photos, rejected photos and offline cache paths are in memory and saved.
      await _persistRecoveredGmailSnapshot();
      await GmailBackgroundSearch.acknowledgeFinished(
        orderNumber: gmailOrder.text.trim(),
        tracking: tracking.text.trim(),
      );
      if (mounted) setState(() {});
'''
s = replace_once(s, old, new, 'persist/ack after final Gmail photo filter')

p.write_text(s)
print('Gmail v12 applied: reconstructed photos are filtered/cached first, then persisted and acknowledged.')
