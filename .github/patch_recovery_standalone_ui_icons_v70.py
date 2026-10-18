from pathlib import Path

# v70: Reject isolated X/social and protection-shield symbols from Gmail
# without undoing v69's small compressed product image recovery.
# Reuse the confirmed non-product 'store_wordmark' class so the v59/v60
# persisted-photo and inbox fallback guards cannot resurrect these icons.
p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
anchor = 'Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
assert s.count(anchor) == 1, 'v70: photo classifier missing'

helper = r'''// Standalone UI symbols (X, protective shield, etc.) have very few flat
// colors and a near-square canvas. Do not infer from "icon" or "logo" in a
// CDN URL: actual Temu/SHEIN merchandise can have those URL words.
// This is intentionally narrow; uncertain imagery stays reviewable.
Future<bool> gmailLooksLikeStandaloneUiSymbol(
  List<int> bytes, int width, int height,
) async {
  if (width < 90 || height < 90 || width > 640 || height > 640) {
    return false;
  }
  final ratio = width / height;
  if (ratio < 0.78 || ratio > 1.30) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes),
      targetWidth: 96,
      targetHeight: 96,
    );
    try {
      final frame = await codec.getNextFrame();
      try {
        final data = await frame.image.toByteData(
          format: ui.ImageByteFormat.rawRgba,
        );
        if (data == null) return false;
        final rgba = data.buffer.asUint8List();
        final w = frame.image.width, h = frame.image.height;
        final histogram = <int, int>{};
        var pixels = 0;
        for (var y = 0; y < h; y += 2) {
          for (var x = 0; x < w; x += 2) {
            final i = (y * w + x) * 4;
            if (i + 3 >= rgba.length || rgba[i + 3] < 128) continue;
            final bucket = ((rgba[i] >> 5) << 6) |
                ((rgba[i + 1] >> 5) << 3) |
                (rgba[i + 2] >> 5);
            histogram[bucket] = (histogram[bucket] ?? 0) + 1;
            pixels++;
          }
        }
        if (pixels < 400 || histogram.length > 24) return false;
        final counts = histogram.values.toList()
          ..sort((a, b) => b.compareTo(a));
        final top3 = counts.take(3).fold<int>(0, (a, b) => a + b);
        final top6 = counts.take(6).fold<int>(0, (a, b) => a + b);
        return top3 / pixels >= 0.83 && top6 / pixels >= 0.94;
      } finally {
        frame.image.dispose();
      }
    } finally {
      codec.dispose();
    }
  } catch (_) {
    return false; // Decoder errors must never discard a genuine product.
  }
}

'''
s = s.replace(anchor, helper + anchor, 1)
start = s.index(anchor)
end = s.index('\nWidget gmailSmartPhotoImage(', start)
fn = s[start:end]
decision = '''      final matchedItem = _gmailMatchedItem(ocr, items);
      final orderItemSignals = gmailOrderItemPhotoSignals(ocr);
      final catalogCard = gmailCatalogRecommendationCard(ocr);
'''
assert fn.count(decision) == 1, 'v70: OCR/product classification anchor moved'
updated = '''      final matchedItem = _gmailMatchedItem(ocr, items);
      final orderItemSignals = gmailOrderItemPhotoSignals(ocr);

      // Only a standalone, flat graphic with NO actual order-item evidence.
      // Do not trust square geometry alone, and keep all manual overrides.
      if (matchedItem.isEmpty &&
          !orderItemSignals &&
          image['manuallyAccepted'] != true &&
          await gmailLooksLikeStandaloneUiSymbol(bytes, width, height)) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': 'icono de interfaz (no artículo)',
          // The v59/v60 logo hard veto already guards every fallback path
          // and offline-photo merge for this confirmed non-product class.
          'photoClass': 'store_wordmark',
        });
        continue;
      }
      final catalogCard = gmailCatalogRecommendationCard(ocr);
'''
fn = fn.replace(decision, updated, 1)
assert fn.index('gmailLooksLikeStandaloneUiSymbol(bytes, width, height)') < fn.index('if (sectionProduct) score += 8;')
assert "await gmailLooksLikePhotoAndBriefLabelRow(bytes, width, height)" in fn
assert "'photoClass': 'store_wordmark'" in fn
s = s[:start] + fn + s[end:]
p.write_text(s)
print('v70: isolated flat UI symbols rejected; v69 compact products and photo fallbacks preserved.')
