from pathlib import Path

# v68: correct a second source of false rejection: narrow <90px-tall
# real photo+1pc rows are classified as "icono pequeño" BEFORE v67 score.
# Show reject reason in fullscreen discarded viewer (some are unscored inbox
# candidates). Preserve hard logo/banner/truck vetoes and manual restore.
p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
old = '''  if (width < 150 || height < 65 ||
      width / height < 1.55 || width / height > 9.0) return false;'''
new = '''  if (width < 85 || height < 43 ||
      width / height < 1.28 || width / height > 10.0) return false;'''
assert s.count(old) == 1, 'v68 narrow row detection location changed'
s = s.replace(old, new, 1)

a = s.index('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
b = s.index('\nWidget gmailSmartPhotoImage(', a)
fn = s[a:b]
old = '''      if (width > 0 && height > 0 && (width < 90 || height < 90) &&
          !sourceThumbnail && image['productRowHint'] != true) {'''
new = '''      // A 240x58 product photo plus "1pc" must not be treated as an icon.
      final photographicRowCandidate =
          await gmailLooksLikePhotoAndBriefLabelRow(bytes, width, height);
      if (width > 0 && height > 0 && (width < 90 || height < 90) &&
          !sourceThumbnail && image['productRowHint'] != true &&
          !photographicRowCandidate) {'''
assert fn.count(old) == 1, 'v68 small-photo early veto moved'
fn = fn.replace(old, new, 1)
old = '''      final compactPhotoRow =
          await gmailLooksLikePhotoAndBriefLabelRow(bytes, width, height);'''
assert fn.count(old) == 1
fn = fn.replace(old, '''      final compactPhotoRow = photographicRowCandidate;''', 1)
old = '''      final shortItemPhotoRow =
          width >= 150 && height >= 65 &&
          ratio >= 1.55 && ratio <= 9.0 &&
          !deliveryProofHint && !catalogCard &&
          (compactPhotoRow ||
           (shortItemLabel &&
            (matchedItem.isNotEmpty || orderItemSignals ||
             compactPhotoRow)));'''
new = '''      final shortItemPhotoRow =
          width >= 85 && height >= 43 &&
          ratio >= 1.28 && ratio <= 10.0 &&
          !deliveryProofHint && !catalogCard &&
          (compactPhotoRow ||
           (shortItemLabel &&
            (matchedItem.isNotEmpty || orderItemSignals)));'''
assert fn.count(old) == 1, 'v68 short order row scoring moved'
fn = fn.replace(old, new, 1)
assert fn.index('if (shippingIconName ||') < fn.index('if (shortItemPhotoRow) score += 6;')
assert fn.index('if (installBannerByPixels)') < fn.index('if (shortItemPhotoRow) score += 6;')
s = s[:a] + fn + s[b:]

# Show exactly why a candidate is in rejected review. A "candidate" reason
# means it was never classified, so no extra OCR rule would have rescued it.
old = """                      child: Text(
                        '${currentIndex + 1} / ${working.length} · Desliza horizontalmente',
                        style: const TextStyle(color: Colors.white),
                      ),"""
new = """                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            '${currentIndex + 1} / ${working.length} · Desliza horizontalmente',
                            style: const TextStyle(color: Colors.white),
                            textAlign: TextAlign.center,
                          ),
                          if ((working[currentIndex]['rejectReason'] ?? '')
                              .toString().trim().isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.only(top: 5),
                              child: Text(
                                'Motivo: ${(working[currentIndex]['rejectReason'] ?? '').toString()}',
                                style: const TextStyle(
                                  color: Colors.white70, fontSize: 12,
                                ),
                                textAlign: TextAlign.center,
                                maxLines: 3,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                        ],
                      ),"""
assert s.count(old) == 1, 'v68 gallery diagnostic footer moved'
s = s.replace(old, new, 1)
p.write_text(s)
print('v68: compact 1pc photos protected before small-size veto; precise reason displayed in discarded viewer.')
