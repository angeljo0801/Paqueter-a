from pathlib import Path

# Gmail v42: reject isolated vector-style UI glyphs (e.g. X social icon and
# payment-protection shield) while keeping compact genuine product rows.
# Do NOT blacklist generic URL words such as "logo", "banner" or "icon":
# Temu product CDN paths may contain those words.
p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()

helper_anchor = 'Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
if s.count(helper_anchor) != 1:
    raise SystemExit('Gmail v42: product photo preparation function changed')

helper = r'''// Unlike normal product photographs, standalone email UI icons are small,
// nearly square, and have a tiny flat-color palette. Analyze actual pixels,
// not CDN filenames: genuine Temu product URLs can contain "logo"/"icon".
//
// This is deliberately conservative. Ambiguous pictures remain accepted or
// accessible in the "discarded photos" review gallery.
Future<bool> gmailLooksLikeStandaloneUiIcon(
  Uint8List bytes,
  int width,
  int height,
) async {
  if (width < 90 || height < 90 || width > 640 || height > 640) {
    return false;
  }
  final ratio = width / height;
  if (ratio < 0.78 || ratio > 1.30) return false;

  try {
    final codec = await ui.instantiateImageCodec(
      bytes,
      targetWidth: 96,
      targetHeight: 96,
    );
    try {
      final frame = await codec.getNextFrame();
      try {
        final pixelData =
            await frame.image.toByteData(format: ui.ImageByteFormat.rawRgba);
        if (pixelData == null) return false;
        final rgba = pixelData.buffer.asUint8List();
        final sampleWidth = frame.image.width;
        final sampleHeight = frame.image.height;
        final palette = <int, int>{};
        var sampled = 0;

        // 8x8x8 RGB bins tolerate JPEG artifacts while separating detailed
        // photos from simple flat-colored raster/vector graphics.
        for (var y = 0; y < sampleHeight; y += 2) {
          for (var x = 0; x < sampleWidth; x += 2) {
            final i = (y * sampleWidth + x) * 4;
            if (i + 3 >= rgba.length || rgba[i + 3] < 128) continue;
            final key = ((rgba[i] >> 5) << 6) |
                ((rgba[i + 1] >> 5) << 3) |
                (rgba[i + 2] >> 5);
            palette[key] = (palette[key] ?? 0) + 1;
            sampled++;
          }
        }
        if (sampled < 400 || palette.length > 24) return false;
        final frequencies = palette.values.toList()
          ..sort((a, b) => b.compareTo(a));
        final topThree = frequencies.take(3).fold<int>(0, (a, b) => a + b);
        final topSix = frequencies.take(6).fold<int>(0, (a, b) => a + b);
        return topThree / sampled >= 0.83 && topSix / sampled >= 0.94;
      } finally {
        frame.image.dispose();
      }
    } finally {
      codec.dispose();
    }
  } catch (_) {
    // Decode/texture uncertainty must not cost the customer a product image.
    return false;
  }
}

'''
s = s.replace(helper_anchor, helper + helper_anchor, 1)

decision_anchor = '''      final matchedItem = _gmailMatchedItem(ocr, items);
      final orderItemSignals = gmailOrderItemPhotoSignals(ocr);
      final catalogCard = gmailCatalogRecommendationCard(ocr);
'''
if s.count(decision_anchor) != 1:
    raise SystemExit('Gmail v42: photo classification signal block changed')
replacement = '''      final matchedItem = _gmailMatchedItem(ocr, items);
      final orderItemSignals = gmailOrderItemPhotoSignals(ocr);

      // Flat single-symbol tiles (social X, green verification shield, etc.)
      // are not purchased articles. Require an isolated graphic AND no item
      // context; shape/size or filenames alone can never reject a product.
      if (matchedItem.isEmpty &&
          !orderItemSignals &&
          image['manuallyAccepted'] != true &&
          await gmailLooksLikeStandaloneUiIcon(bytes, width, height)) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': 'icono de interfaz sin artículo',
        });
        continue;
      }
      final catalogCard = gmailCatalogRecommendationCard(ocr);
'''
s = s.replace(decision_anchor, replacement, 1)

p.write_text(s)
print('Gmail v42 applied: isolated flat UI icons rejected; real product evidence and manual review preserved.')
