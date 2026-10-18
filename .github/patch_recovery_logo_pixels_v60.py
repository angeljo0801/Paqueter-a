from pathlib import Path

# v60 -- Regression: a narrow white SHEIN brand graphic passed v59 when
# ML Kit OCR returned blank. Classify wide, nearly monochrome brand wordmarks
# by their IMAGE pixels before any trusted-shop thumbnail bonus or fallback.
# Avoid relying on file names and avoid broad OCR rules that lose real watches.

p=Path('app/lib/gmail_purchase_link.dart')
s=p.read_text()
anchor='Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
assert s.count(anchor)==1
helper=r'''
// Narrow brand-wordmark signature, not a general black-and-white rejection:
// monochrome lettering in an unusually WIDE strip. Watches and ordinary
// merchandise thumbnails are approximately square and remain untouched.
Future<bool> gmailLooksLikeWideBrandWordmark(
  List<int> bytes,
  int width,
  int height,
) async {
  if (width < 95 || height < 12 || width / height < 2.65) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes),
      targetWidth: width > 256 ? 256 : null,
    );
    final frame = await codec.getNextFrame();
    try {
      final data = await frame.image.toByteData(
        format: ui.ImageByteFormat.rawRgba,
      );
      if (data == null) return false;
      final rgba = data.buffer.asUint8List();
      var sample = 0;
      var neutral = 0;
      var bright = 0;
      var dark = 0;
      var transparent = 0;
      for (var i = 0; i + 3 < rgba.length; i += 4) {
        final alpha = rgba[i + 3];
        if (alpha < 32) {
          transparent++;
          continue;
        }
        final red = rgba[i], green = rgba[i + 1], blue = rgba[i + 2];
        final highest = [red, green, blue].reduce((a, b) => a > b ? a : b);
        final lowest = [red, green, blue].reduce((a, b) => a < b ? a : b);
        final luminance = (red * 299 + green * 587 + blue * 114) ~/ 1000;
        sample++;
        if (highest - lowest <= 29) neutral++;
        if (luminance >= 200) bright++;
        if (luminance <= 100) dark++;
      }
      final total = sample + transparent;
      if (total == 0 || sample < 75) return false;
      final colorfulOrPhoto = neutral / sample < 0.93;
      if (colorfulOrPhoto) return false;
      // The SHEIN screenshot is black text on a white, thin horizontal band.
      // Require BOTH light and dark pixels, with very few midtones, so a
      // black belt on white or a pale product is not rejected solely by ratio.
      final bicolor = bright / sample >= 0.30 &&
          dark / sample >= 0.06 &&
          (bright + dark) / sample >= 0.81;
      final transparentBrand = transparent / total >= 0.50 &&
          bright / sample >= 0.06 &&
          dark / sample >= 0.06;
      return bicolor || transparentBrand;
    } finally {
      frame.image.dispose();
      codec.dispose();
    }
  } catch (e) {
    debugPrint('Gmail wordmark pixel inspection skipped: $e');
    return false; // Do not block products on a decoder failure.
  }
}

'''
s=s.replace(anchor,helper+anchor,1)

a=s.index(anchor)
b=s.index('\nWidget gmailSmartPhotoImage(',a)
fn=s[a:b]
size="""      if (width > 0 && height > 0 && (width < 90 || height < 90) &&
          !sourceThumbnail) {"""
assert fn.count(size)==1,'v60 image geometry gate changed'
fn=fn.replace(size,r'''      // Visual check runs BEFORE small-image rejection and the trusted-source
      // bonus. OCR may fail on thin brand lettering; the pixels still show a
      // white/black monochrome wordmark with a very wide aspect ratio.
      if (await gmailLooksLikeWideBrandWordmark(bytes, width, height)) {
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'rejectReason': 'logotipo de tienda (no artículo)',
          'photoClass': 'store_wordmark',
        });
        continue;
      }
'''+size,1)
s=s[:a]+fn+s[b:]
p.write_text(s)

# The fallback preview must never overrule a positively classified logo.
# Protect against CDN URL aliases by comparing the digest thumbnail identity.
p=Path('app/lib/packages.dart')
s=p.read_text()
a=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedGmailPhotos() async {',a)
fn=s[a:b]
anchor="""      for (final image in gmailCandidateInbox) {"""
assert fn.count(anchor)==1,'v60 inbox fallback loop missing'
fn=fn.replace(anchor,r'''      final rejectedWordmarkIds = rejected
          .where((e) => e['photoClass'] == 'store_wordmark')
          .map(_gmailCandidateIdentity)
          .toSet();
      for (final image in gmailCandidateInbox) {
        // A candidate may have different original/cached URLs but one
        // canonical thumbnail identity. Never automatically resurrect logos.
        if (rejectedWordmarkIds.contains(_gmailCandidateIdentity(image))) {
          continue;
        }
''',1)
s=s[:a]+fn+s[b:]
p.write_text(s)

# Validate code placement rather than relying on a debug-only screenshot.
h=Path('app/lib/gmail_purchase_link.dart').read_text()
a=h.index('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
b=h.index('\nWidget gmailSmartPhotoImage(',a)
fn=h[a:b]
assert fn.index('gmailLooksLikeWideBrandWordmark(bytes, width, height)') < fn.index('final sourceThumbnail')
assert 'final colorfulOrPhoto = neutral / sample < 0.93;' in h
assert "if (rejectedWordmarkIds.contains(_gmailCandidateIdentity(image)))" in s
print('v60: OCR-empty wide monochrome SHEIN/TEMU wordmarks rejected by pixels; originals retained for review.')
