from pathlib import Path

# v63: Fix a concrete user regression: Temu's valid shirt "Built Different /
# Black / Label size: S x1" went to discarded; a white delivery-truck icon
# and house/door photos were wrongly accepted. Backend now flags per-IMAGE
# deliveryProofHint and productRowHint using "Package info" as the separator.
# This patch keeps general Gmail search, SHEIN's pre-delivery rule and stored
# manual photos intact.

p=Path('app/lib/packages.dart')
s=p.read_text()
a=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedGmailPhotos() async {',a)
fn=s[a:b]
old=r'''    final preparedByUrl = <String, Map<String, dynamic>>{};
    for (final candidate in gmailCandidateInbox) {
      final url = (candidate['url'] ?? '').toString().trim();
      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url)) continue;
      final previous = preparedByUrl[url];
      if (previous == null ||
          (previous['thumbnailUrl'] ?? '').toString().isEmpty) {
        preparedByUrl[url] = candidate;
      }
    }'''
new=r'''    final preparedByUrl = <String, Map<String, dynamic>>{};
    for (final candidate in gmailCandidateInbox) {
      final cached = (candidate['url'] ?? '').toString().trim();
      final original = (candidate['originalUrl'] ?? '').toString().trim();
      if (cached.isEmpty || hiddenEmailPhotoUrls.contains(cached) ||
          (original.isNotEmpty && hiddenEmailPhotoUrls.contains(original))) {
        continue;
      }
      // Backend candidate URL is /api/gmail/media/cache_... while the
      // original emailPhotoUrls contains a remote CDN URL. Index BOTH.
      for (final key in <String>[cached, original]) {
        if (key.isEmpty) continue;
        final previous = preparedByUrl[key];
        if (previous == null ||
            (previous['thumbnailUrl'] ?? '').toString().isEmpty) {
          preparedByUrl[key] = candidate;
        }
      }
    }'''
assert fn.count(old)==1, 'v63 expected v62 prepared mapping'
fn=fn.replace(old,new,1)
# The existing v62 source loop now maps originals -> cached originals, and
# de-duplicates both by the canonical thumbnail's digest.
s=s[:a]+fn+s[b:]
p.write_text(s)

p=Path('app/lib/gmail_purchase_link.dart')
s=p.read_text()
anchor='Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
assert s.count(anchor)==1

helper=r'''
// A logistics icon is a flat vector design, not a product. In contrast,
// photographic watches/shoes or a shirt card have varied colors/textures.
// Guard narrowly: dark, almost uniformly gray background, bright white flat
// glyph, square icon geometry, no purchase-row provenance.
Future<bool> gmailLooksLikeFlatLogisticsIcon(
  List<int> bytes,
  int width,
  int height,
) async {
  if (width < 70 || height < 70 ||
      width / height < 0.74 || width / height > 1.40) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes),
      targetWidth: width > 192 ? 192 : null,
    );
    final frame = await codec.getNextFrame();
    try {
      final byteData = await frame.image.toByteData(
        format: ui.ImageByteFormat.rawRgba,
      );
      if (byteData == null) return false;
      final pixels = byteData.buffer.asUint8List();
      if (pixels.length < 400) return false;
      final r0 = pixels[0], g0 = pixels[1], b0 = pixels[2];
      final bgLum = (r0 * 299 + g0 * 587 + b0 * 114) ~/ 1000;
      if (bgLum > 115 || (r0 - g0).abs() > 24 ||
          (r0 - b0).abs() > 24) return false;
      var count = 0, neutral = 0, background = 0, brightGlyph = 0;
      for (var i = 0; i + 3 < pixels.length; i += 4) {
        if (pixels[i + 3] < 100) continue;
        count++;
        final r = pixels[i], g = pixels[i + 1], b = pixels[i + 2];
        final hi = [r, g, b].reduce((a, b) => a > b ? a : b);
        final lo = [r, g, b].reduce((a, b) => a < b ? a : b);
        if (hi - lo < 30) neutral++;
        if ((r - r0).abs() < 20 && (g - g0).abs() < 20 &&
            (b - b0).abs() < 20) background++;
        if (r > 176 && g > 176 && b > 176) brightGlyph++;
      }
      if (count < 100) return false;
      return neutral / count >= 0.94 &&
          background / count >= 0.52 &&
          brightGlyph / count >= 0.07;
    } finally {
      frame.image.dispose();
      codec.dispose();
    }
  } catch (_) {
    return false;
  }
}

'''
s=s.replace(anchor,helper+anchor,1)
a=s.index(anchor)
b=s.index('\nWidget gmailSmartPhotoImage(',a)
fn=s[a:b]

old="""      if (await gmailLooksLikeWideBrandWordmark(bytes, width, height)) {"""
new="""      if (image['productRowHint'] != true &&
          await gmailLooksLikeWideBrandWordmark(bytes, width, height)) {"""
assert fn.count(old)==1,'v63 old wide brand detector'
fn=fn.replace(old,new,1)

needle="""      if (width > 0 && height > 0 && (width < 90 || height < 90) &&
          !sourceThumbnail) {"""
replacement="""      if (width > 0 && height > 0 && (width < 90 || height < 90) &&
          !sourceThumbnail && image['productRowHint'] != true) {"""
assert fn.count(needle)==1,'v63 small product row threshold'
fn=fn.replace(needle,replacement,1)

# Place a hard delivery-photo veto after the downloaded image can be decoded,
# before white/gray vector icons or source bonuses can gain scoring points.
needle="""      var score = 0;"""
insert=r'''      final sectionProduct = image['productRowHint'] == true &&
          !deliveryProofHint;
      // This metadata is for the image BEFORE "Package info", not the whole
      // email. It can include the house, doormat, address, Temu logo and
      // tracking/delivery pictograms. None is merchandise.
      if (image['deliveryProofHint'] == true && !sectionProduct) {
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'rejectReason': 'foto o icono de entrega (no artículo)',
          'photoClass': 'delivery_proof',
        });
        continue;
      }
      final assetName = ' '
          .toLowerCase();
      final shippingIconName = RegExp(
        r'(?:truck|delivery|shipping|shipment|logistics|courier|gofo)'
        r'[-_/.]?(?:icon|logo|symbol|badge)|'
        r'(?:icon|logo)[-_/.]?(?:truck|delivery|shipping|courier)',
      ).hasMatch(assetName);
      if (!sectionProduct && (shippingIconName ||
          await gmailLooksLikeFlatLogisticsIcon(bytes, width, height))) {
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'rejectReason': 'icono de transporte (no artículo)',
          'photoClass': 'logistics_icon',
        });
        continue;
      }
'''
assert fn.count(needle)==1,'v63 score initialization'
fn=fn.replace(needle,insert+needle,1)

# Protect the real elongated product row, even when OCR returns no readable
# text from gray writing on black background. The backend has positively
# identified the "Package info" section boundary for this exact image.
needle="""      if (score < 2 && !trustedProductShape) {"""
replacement="""      if (sectionProduct) score += 8;
      if (score < 2 && !trustedProductShape && !sectionProduct) {"""
assert fn.count(needle)==1,'v63 score cutoff'
fn=fn.replace(needle,replacement,1)
# Existing v59 wordmark check must not reject actual product row by OCR noise.
needle="""      if (gmailIsIsolatedStoreWordmark(ocr)) {"""
repl="""      if (gmailIsIsolatedStoreWordmark(ocr) && !sectionProduct) {"""
assert fn.count(needle)==1,'v63 OCR wordmark anchor'
fn=fn.replace(needle,repl,1)
s=s[:a]+fn+s[b:]
p.write_text(s)

assert 'final sectionProduct = image[\\'productRowHint\\'] == true' in s
assert 'gmailLooksLikeFlatLogisticsIcon(bytes, width, height)' in s
assert "if (sectionProduct) score += 8;" in s
print('v63: shirt from Package info accepted, delivery proof/truck icon rejected, CDN thumbnail mapping repaired.')
