from pathlib import Path

# v50: A nonessential second OCR pass must never precede or block photo
# persistence. The accepted photos and their offline paths are the durable
# result. Only acknowledge the Gmail job AFTER verifying it on disk.
p=Path('app/lib/packages.dart')
s=p.read_text()
start=s.index('  Future<void> reconstructFromGmail() async {')
end=s.index('  Future<void> openEmailPhoto(',start)
method=s[start:end]

photo='      await _smartFilterAndCacheGmailPhotos();'
ocr='      await _mergeItemsFromEmailImageOcr();'
assert method.count(photo)==1 and method.count(ocr)==1, 'v50: expected one photo and one OCR pass'
assert method.index(photo)<method.index(ocr), 'v50: photo filter no longer first'

# There are TWO persistence/ack pairs: one in the already-processed worker
# branch (keep it intact), and another following the second OCR. Move only
# the second pair in front of the nonessential OCR.
saved='      await _persistRecoveredGmailSnapshot();'
ack="""      await GmailBackgroundSearch.acknowledgeFinished(
        orderNumber: gmailOrder.text.trim(),
        tracking: tracking.text.trim(),
      );"""
idx=method.index(ocr)
if method.count(saved,idx)!=1 or method.count(ack,idx)!=1:
    raise RuntimeError('v50: could not isolate the post-OCR save/ack pair')
method=method[:idx]+method[idx:].replace(saved,'',1).replace(ack,'',1)
idx=method.index(ocr)
write_first="""      // Product photos must be on disk before any optional item-name OCR.
      // A failure here keeps the Gmail result pending and retryable.
      if (!mounted) return;
      await _persistRecoveredGmailSnapshot();
      await GmailBackgroundSearch.acknowledgeFinished(
        orderNumber: gmailOrder.text.trim(),
        tracking: tracking.text.trim(),
      );
      // OCR of item descriptions is useful, but cannot undo a photo save.
      try {
        await _mergeItemsFromEmailImageOcr();
        await _persistRecoveredGmailSnapshot();
      } catch (e) {
        debugPrint('Gmail item OCR skipped after photos saved: $e');
      }"""
method=method[:idx]+method[idx:].replace(ocr,write_first,1)
assert method.count(saved)==3, f'v50: expected worker, photo, OCR save paths, found {method.count(saved)}'
assert method.count('GmailBackgroundSearch.acknowledgeFinished(')>=1, 'v50: photo acknowledgement missing'
print('v50 photo transaction validation: snapshot writes=',method.count(saved), 'acknowledgements=',method.count('GmailBackgroundSearch.acknowledgeFinished('))
assert method.index('      // Product photos must be on disk')<method.index('        await _mergeItemsFromEmailImageOcr();')
s=s[:start]+method+s[end:]
p.write_text(s)

# Existing users can explicitly save as before, but avoid visually clearing
# photos with old saved state by loading the current record after a successful
# automatic persistence, rather than reopening a stale widget.existing map.
# The snapshot itself only touches Gmail fields and never overwrites buyers.

print('Gmail v50: final photo snapshot verified and acknowledged before optional item OCR.')
