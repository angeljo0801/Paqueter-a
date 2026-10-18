from pathlib import Path

# v64: Regression fixtures supplied by the user:
# - white lightning-bolt delivery truck on a SOLID GREEN square: reject
# - "Temu: Shop Like a Billionaire / Shop anywhere with our App / Get":
#   reject as an install ad, not an item
# - keep the real dark shirt row under Package info ("Black / Label size: S x1")
# - keep SHEIN watches and all other shopping photos.
# Do not make the Gmail search or product-page UI changes here.

p=Path('app/lib/gmail_purchase_link.dart')
s=p.read_text()
anchor='Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
assert s.count(anchor)==1

helpers=r'''
// Recognize only a flat monochrome glyph on a SINGLE solid-colored square,
// including Temu's GREEN charging/truck icon. This does not reject photos
// merely because they have a green background or depict a truck for sale.
Future<bool> gmailLooksLikeSolidColorDeliveryGlyph(
  List<int> bytes,
  int width,
  int height,
) async {
  if (width < 70 || height < 70 ||
      width / height < 0.72 || width / height > 1.43) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes), targetWidth: width > 192 ? 192 : null,
    );
    final frame = await codec.getNextFrame();
    try {
      final data = await frame.image.toByteData(
        format: ui.ImageByteFormat.rawRgba,
      );
      if (data == null) return false;
      final pixels = data.buffer.asUint8List();
      if (pixels.length < 400) return false;
      final histogram = <int, int>{};
      var visible = 0;
      var white = 0;
      for (var i = 0; i + 3 < pixels.length; i += 4) {
        if (pixels[i + 3] < 128) continue;
        visible++;
        final red = pixels[i], green = pixels[i + 1], blue = pixels[i + 2];
        if (red >= 208 && green >= 208 && blue >= 208) {
          white++;
        } else {
          final bucket = (red ~/ 24) * 144 + (green ~/ 24) * 12 +
              blue ~/ 24;
          histogram[bucket] = (histogram[bucket] ?? 0) + 1;
        }
      }
      if (visible < 500) return false;
      final whiteRatio = white / visible;
      final dominant = histogram.values.fold<int>(
        0, (max, n) => n > max ? n : max,
      ) / visible;
      // Solid green Temu background + sharp pure-white pictogram typically
      // occupies ~40-65% background and ~20-40% white glyph. The real
      // product photo has texture, so it lacks one dominating color bucket.
      return dominant >= 0.36 && whiteRatio >= 0.16 &&
          whiteRatio <= 0.68;
    } finally {
      frame.image.dispose();
      codec.dispose();
    }
  } catch (_) { return false; }
}

// Temu app-install strip shown in the supplied screenshot: white horizontal
// ad, orange TEMU branding / GET button, no merchandise. This is independent
// of ML Kit OCR availability, which may be exhausted after many email images.
Future<bool> gmailLooksLikeTemuInstallStrip(
  List<int> bytes,
  int width,
  int height,
) async {
  if (width < 230 || height < 35 || width / height < 2.65) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes), targetWidth: width > 256 ? 256 : null,
    );
    final frame = await codec.getNextFrame();
    try {
      final data = await frame.image.toByteData(
        format: ui.ImageByteFormat.rawRgba,
      );
      if (data == null) return false;
      final pixels = data.buffer.asUint8List();
      var total = 0, pale = 0, orange = 0;
      for (var i = 0; i + 3 < pixels.length; i += 4) {
        if (pixels[i + 3] < 128) continue;
        total++;
        final red = pixels[i], green = pixels[i + 1], blue = pixels[i + 2];
        if (red >= 210 && green >= 210 && blue >= 210) pale++;
        if (red >= 188 && green >= 57 && green <= 183 && blue < 82 &&
            red > green * 1.35) orange++;
      }
      if (total < 500) return false;
      return pale / total >= 0.60 &&
          orange / total >= 0.035 && orange / total <= 0.30;
    } finally {
      frame.image.dispose();
      codec.dispose();
    }
  } catch (_) { return false; }
}

bool gmailTemuInstallText(String text) {
  final lower = text.toLowerCase().replaceAll(RegExp(r'\s+'), ' ');
  return lower.contains('shop like a billionaire') ||
      lower.contains('shop anywhere with our app') ||
      (lower.contains('temu') && lower.contains('shop anywhere') &&
       lower.contains('get'));
}

'''
s=s.replace(anchor,helpers+anchor,1)
a=s.index(anchor)
b=s.index('\nWidget gmailSmartPhotoImage(',a)
fn=s[a:b]

# v63 lost the actual original URL / name due to an interpolation mishap:
# it literally matched a blank space, so URL-based transport rules never ran.
broken="""      final assetName = ' '
          .toLowerCase();"""
correct="""      final assetName =
          (image['originalUrl'] ?? '').toString().toLowerCase() + ' ' +
          (image['name'] ?? '').toString().toLowerCase();"""
assert fn.count(broken)==1, 'v64 transport asset name regression moved'
fn=fn.replace(broken,correct,1)

# Existing v63 logic classifies after decoding but before large-product boost.
needle="""      if (!sectionProduct && (shippingIconName ||
          await gmailLooksLikeFlatLogisticsIcon(bytes, width, height))) {"""
assert fn.count(needle)==1, 'v64 icon veto location moved'
fn=fn.replace(needle,"""      if (!sectionProduct && (shippingIconName ||
          await gmailLooksLikeFlatLogisticsIcon(bytes, width, height) ||
          await gmailLooksLikeSolidColorDeliveryGlyph(bytes, width, height))) {""",1)

# Install ads are a separate type; do not let source provenance or size
# override this hard no-merchandise test.
mark="""      var score = 0;"""
guard="""      final installBannerByPixels = !sectionProduct &&
          await gmailLooksLikeTemuInstallStrip(bytes, width, height);
      if (installBannerByPixels) {
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'rejectReason': 'anuncio para instalar Temu (no artículo)',
          'photoClass': 'app_install_banner',
        });
        continue;
      }
"""
assert fn.count(mark)==1, 'v64 score marker changed'
fn=fn.replace(mark,guard+mark,1)

# Product (shirt) provenance remains the highest priority except for
# unmistakable shipping/advertising graphics; never punish all wide images.
needle="""      if (_gmailPromoText(ocr) && !trustedProductShape) {"""
replacement="""      if (gmailTemuInstallText(ocr) && !sectionProduct) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': 'anuncio para instalar Temu (no artículo)',
          'photoClass': 'app_install_banner',
        });
        continue;
      }
      if (_gmailPromoText(ocr) && !trustedProductShape) {"""
assert fn.count(needle)==1, 'v64 OCR banner marker changed'
fn=fn.replace(needle,replacement,1)
s=s[:a]+fn+s[b:]
p.write_text(s)

# Reject the *current search's* confirmed logistics/promotional images even
# if a previous photo snapshot stored them as a purchase.
p=Path('app/lib/packages.dart')
s=p.read_text()
a=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedGmailPhotos() async {',a)
fn=s[a:b]
original="""        .where((e) => e['photoClass'] == 'store_wordmark' ||
              e['rejectReason'] == 'logotipo de tienda (no artículo)')"""
replacement="""        .where((e) => e['photoClass'] == 'store_wordmark' ||
              e['photoClass'] == 'logistics_icon' ||
              e['photoClass'] == 'app_install_banner' ||
              e['photoClass'] == 'delivery_proof' ||
              e['rejectReason'] == 'logotipo de tienda (no artículo)')"""
assert fn.count(original)==1, 'v64 review classified rejection anchor'
fn=fn.replace(original,replacement,1)
s=s[:a]+fn+s[b:]

a=s.index('  Future<void> _persistRecoveredGmailSnapshot() async {')
b=s.index('  Future<void> removeMultipleEmailPhotos() async {',a)
fn=s[a:b]
old="""        .where((e) => e['photoClass'] == 'store_wordmark' ||
            e['rejectReason'] == 'logotipo de tienda (no artículo)')"""
new="""        .where((e) => e['photoClass'] == 'store_wordmark' ||
            e['photoClass'] == 'logistics_icon' ||
            e['photoClass'] == 'app_install_banner' ||
            e['photoClass'] == 'delivery_proof' ||
            e['rejectReason'] == 'logotipo de tienda (no artículo)')"""
assert fn.count(old)==1, 'v64 saved-photo rejection anchor'
fn=fn.replace(old,new,1)
s=s[:a]+fn+s[b:]
p.write_text(s)

assert 'gmailLooksLikeSolidColorDeliveryGlyph(bytes, width, height)' in
Path('app/lib/gmail_purchase_link.dart').read_text()
assert 'gmailTemuInstallText(ocr)' in Path('app/lib/gmail_purchase_link.dart').read_text()
print('v64: green Temu transport icon and orange app-install banner rejected; product shirt preserved.')
