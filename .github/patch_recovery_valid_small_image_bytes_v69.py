from pathlib import Path

# v69 -- The actual rejected "1pc" flashlight image has rejectReason
# "imagen demasiado pequeña/grande". This phrase is NOT a pixel-size veto.
# The v1 product-image analyzer rejects ANY file whose compressed byte length
# is under 3500, BEFORE decoding, OCR, or the v67/v68 compact-product rules.
# Efficiently compressed product thumbnails can be under 3500 bytes.
# Permit any nonempty, decodable image up to the existing 10 MiB guard. Keep
# every logistics, advertising, store-wordmark and learning safety veto intact.

p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
a = s.index('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
b = s.index('\nWidget gmailSmartPhotoImage(', a)
fn = s[a:b]

old = """      if (bytes.length < (matchedStoreSource ? 500 : 3500) || bytes.length > 10 * 1024 * 1024) {
        rejected.add({...image, 'rejectReason': 'imagen demasiado pequeña/grande'});
        continue;
      }"""
new = """      // Do not treat compressed file size as an indication that a photo
      // cannot be a product. Tiny WEBP/PNG/JPEG thumbnails can be valid
      // products, including the reported flashlight + 1pc retailer row.
      // Retain only the genuine resource/memory limit.
      if (bytes.isEmpty) {
        rejected.add({...image, 'rejectReason': 'archivo de imagen vacío'});
        continue;
      }
      if (bytes.length > 10 * 1024 * 1024) {
        rejected.add({...image, 'rejectReason': 'archivo de imagen demasiado grande'});
        continue;
      }"""
assert fn.count(old) == 1, 'v69 original compressed-byte gate not found'
fn = fn.replace(old, new, 1)

# A short nonimage HTTP body would otherwise reach URL keyword scoring with
# width/height == 0; reject it explicitly after attempting image decoding.
point = """      final photographicRowCandidate =
          await gmailLooksLikePhotoAndBriefLabelRow(bytes, width, height);"""
guard = """      // If the bytes do not decode into a valid image, never accept them
      // using only URL words, store identity or OCR provenance.
      if (width <= 0 || height <= 0) {
        rejected.add({
          ...image,
          'rejectReason': 'datos no corresponden a una imagen válida',
        });
        continue;
      }
"""
assert fn.count(point) == 1, 'v69 current v68 size/row prefilter missing'
fn = fn.replace(point, guard + point, 1)

assert "bytes.length < 3500" not in fn
assert "matchedStoreSource ? 500 : 3500" not in fn
assert fn.index("if (width <= 0 || height <= 0)") < fn.index("final photographicRowCandidate =")
assert fn.index("if (shippingIconName ||") < fn.index("if (shortItemPhotoRow) score += 6;")
assert fn.index("if (installBannerByPixels)") < fn.index("if (shortItemPhotoRow) score += 6;")
assert "'photoClass': 'logistics_icon'" in fn
assert "'photoClass': 'app_install_banner'" in fn
s = s[:a] + fn + s[b:]
p.write_text(s)
print('v69: <3500-byte compressed valid images reach decoding and classifier; malformed/oversize still rejected.')
