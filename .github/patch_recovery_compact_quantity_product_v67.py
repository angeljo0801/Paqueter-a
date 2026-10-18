from pathlib import Path

# v67: A real flashlight product tile + "1pc" on dark background was discarded.
# v6 required two alphabetic words before treating a wide picture as an item,
# so a one-token quantity label never scored; v54 square-only provenance also
# did not help. Recover real photo + short quantity/variant rows without
# weakening hard exclusions for store logos, logistics icons or install ads.
p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
anchor = 'Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
assert s.count(anchor) == 1, 'v67 Gmail analyzer entry changed'
helpers = r'''
// Detect a genuine photographic thumbnail at the LEFT side of a short/wide
// order row with mostly flat space for a quantity/variant label at the RIGHT.
// This is NOT a generic "wide image" exemption: store banners and white
// delivery pictograms lack textured/colorful photographic content on the left.
Future<bool> gmailLooksLikePhotoAndBriefLabelRow(
  List<int> bytes, int width, int height,
) async {
  if (width < 150 || height < 65 ||
      width / height < 1.55 || width / height > 9.0) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes),
      targetWidth: width > 256 ? 256 : null,
    );
    final frame = await codec.getNextFrame();
    try {
      final img = frame.image;
      final raw = await img.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (raw == null) return false;
      final pixels = raw.buffer.asUint8List();
      final decodedWidth = img.width;
      var leftCount = 0, rightCount = 0, leftColor = 0;
      var sum = 0.0, sumSquares = 0.0;
      final leftBuckets = <int>{};
      final rightBuckets = <int, int>{};
      for (var offset = 0; offset + 3 < pixels.length; offset += 4) {
        if (pixels[offset + 3] < 128) continue;
        final x = ((offset ~/ 4) % decodedWidth) / decodedWidth;
        final r = pixels[offset], g = pixels[offset + 1];
        final b = pixels[offset + 2];
        final bucket = (r ~/ 24) * 144 + (g ~/ 24) * 12 + b ~/ 24;
        if (x >= 0.02 && x <= 0.33) {
          leftCount++;
          final hi = [r, g, b].reduce((a, c) => a > c ? a : c);
          final lo = [r, g, b].reduce((a, c) => a < c ? a : c);
          if (hi - lo >= 28) leftColor++;
          final luma = (299 * r + 587 * g + 114 * b) / 1000.0;
          sum += luma;
          sumSquares += luma * luma;
          leftBuckets.add(bucket);
        } else if (x >= 0.60 && x <= 0.97) {
          rightCount++;
          rightBuckets[bucket] = (rightBuckets[bucket] ?? 0) + 1;
        }
      }
      if (leftCount < 80 || rightCount < 80) return false;
      final luminanceVariance = sumSquares / leftCount -
          (sum / leftCount) * (sum / leftCount);
      final rightDominant = rightBuckets.values.fold<int>(
        0, (maximum, n) => n > maximum ? n : maximum,
      ) / rightCount;
      return leftColor / leftCount >= 0.075 &&
          luminanceVariance >= 900 &&
          leftBuckets.length >= 14 &&
          rightDominant >= 0.67;
    } finally {
      frame.image.dispose();
      codec.dispose();
    }
  } catch (error) {
    debugPrint('Gmail compact item-row photo check skipped: $error');
    return false;
  }
}

bool gmailHasShortItemQuantityOrVariant(String ocr) {
  final text = ocr.toLowerCase().replaceAll(RegExp(r'\s+'), ' ');
  return RegExp(
    r'\b\d{1,3}\s*(?:pcs?|pieces?|units?|ct)\b'
    r'|\b(?:qty|quantity|cantidad)\s*[:#=-]?\s*\d{1,3}\b'
    r'|(?:^|[\s,(])(?:x|×)\s*\d{1,3}\b'
    r'|\b(?:size|talla|color|colour|variant|label size)\s*[:#=-]?\s*[a-z0-9]+\b',
    caseSensitive: false,
  ).hasMatch(text);
}

'''
s = s.replace(anchor, helpers + anchor, 1)
start = s.index(anchor)
end = s.index('\nWidget gmailSmartPhotoImage(', start)
fn = s[start:end]
# The v65 hard icon/banner classifiers run immediately BEFORE this location.
point = '''      var score = 0;'''
assert fn.count(point) == 1, 'v67 product score location missing'
fn = fn.replace(point, '''      final compactPhotoRow =
          await gmailLooksLikePhotoAndBriefLabelRow(bytes, width, height);
''' + point, 1)

# v6 quantityCues did not recognize 1pc, 2pcs, 1 piece, etc. Replace the
# compact item-row boost, not the strict logo/banner/truck exclusions.
anchor = '''      if (compactOrderRow) score += 4;'''
assert fn.count(anchor) == 1, 'v67 existing compact row boost missing'
fn = fn.replace(anchor, '''      if (compactOrderRow) score += 4;
      final shortItemLabel = gmailHasShortItemQuantityOrVariant(ocr);
      final shortItemPhotoRow =
          width >= 150 && height >= 65 &&
          ratio >= 1.55 && ratio <= 9.0 &&
          !deliveryProofHint && !catalogCard &&
          (compactPhotoRow ||
           (shortItemLabel &&
            (matchedItem.isNotEmpty || orderItemSignals ||
             compactPhotoRow)));
      // The supplied flashlight row contains an actual image on the left
      // and only "1pc" on the right. OCR may miss it entirely; a verified
      // photographic-left / empty-label-right layout still counts.
      if (shortItemPhotoRow) score += 6;
''', 1)

# A short genuine row should not be rejected by the legacy >=2-word requirement
# nor by a wide-image text penalty. All hard non-product guards still run first.
old = '''      if (ratio > 2.20 &&
          ocr.split(RegExp(r'\\s+')).length >= 4 &&
          matchedItem.isEmpty &&
          !orderItemSignals &&
          !compactOrderRow) {'''
new = '''      if (ratio > 2.20 &&
          ocr.split(RegExp(r'\\s+')).length >= 4 &&
          matchedItem.isEmpty &&
          !orderItemSignals &&
          !compactOrderRow &&
          !shortItemPhotoRow) {'''
assert fn.count(old) == 1, 'v67 wide-image penalty moved'
fn = fn.replace(old, new, 1)

# The learning engine is optional; its old negative samples must not
# suppress a row positively identified with the new photographic evidence.
old = '''      if (learnedDecision.reject && !sourceThumbnail &&'''
new = '''      if (learnedDecision.reject && !sourceThumbnail &&
          !compactPhotoRow &&'''
assert fn.count(old) == 1, 'v67 optional learning veto changed'
fn = fn.replace(old, new, 1)

s = s[:start] + fn + s[end:]
p.write_text(s)

# Ensure the new row boost cannot bypass the important vetoes.
fn = Path('app/lib/gmail_purchase_link.dart').read_text()
start = fn.index(anchor if False else 'Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
end = fn.index('\nWidget gmailSmartPhotoImage(', start)
fn = fn[start:end]
assert fn.index('if (shippingIconName ||') < fn.index('if (shortItemPhotoRow) score += 6;')
assert fn.index('if (installBannerByPixels)') < fn.index('if (shortItemPhotoRow) score += 6;')
assert 'gmailHasShortItemQuantityOrVariant(ocr)' in fn
assert 'if (sectionProduct) score += 8;' in fn
print('v67: visual photo+1pc/x1/item-variant rows rescued without weakening logistics/ads veto.')
