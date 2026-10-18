from pathlib import Path

# v65 regression: the v64 visual detectors correctly recognize the user
# screenshots, but both are bypassed when backend productRowHint == true.
# Temu's "Package info" boundary is not a blanket product guarantee: the
# same email can include marketing links/truck icons after product details.
# A VERY SPECIFIC logistics/ad classification must outrank positional boosts.
# Keep general Temu Gmail search, SHEIN original rules, image persistence.

p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
a = s.index('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
b = s.index('\nWidget gmailSmartPhotoImage(', a)
fn = s[a:b]

old = '''      if (!sectionProduct && (shippingIconName ||
          await gmailLooksLikeFlatLogisticsIcon(bytes, width, height) ||
          await gmailLooksLikeSolidColorDeliveryGlyph(bytes, width, height))) {'''
new = '''      // High-certainty logistics graphics are NOT products, even if Temu
      // mistakenly tags their email section as "Package info".
      if (shippingIconName ||
          await gmailLooksLikeFlatLogisticsIcon(bytes, width, height) ||
          await gmailLooksLikeSolidColorDeliveryGlyph(bytes, width, height)) {'''
assert fn.count(old) == 1, 'v65 green-truck decision must override productRowHint'
fn = fn.replace(old, new, 1)

old = '''      final installBannerByPixels = !sectionProduct &&
          await gmailLooksLikeTemuInstallStrip(bytes, width, height);'''
new = '''      final installBannerByPixels =
          await gmailLooksLikeTemuInstallStrip(bytes, width, height);'''
assert fn.count(old) == 1, 'v65 banner pixel decision must override productRowHint'
fn = fn.replace(old, new, 1)

old = '''      if (gmailTemuInstallText(ocr) && !sectionProduct) {'''
new = '''      if (gmailTemuInstallText(ocr)) {'''
assert fn.count(old) == 1, 'v65 banner OCR decision must override productRowHint'
fn = fn.replace(old, new, 1)

# Report the exact rejected graphic count instead of appearing to accept
# zero images mysteriously. The existing editor report shows these stats.
needle = '''      'ocrAttempts': ocrAttempts,'''
assert fn.count(needle) == 1, 'v65 OCR report structure moved'
fn = fn.replace(needle, '''      'nonProductGraphics': rejected.where((e) =>
          e['photoClass'] == 'logistics_icon' ||
          e['photoClass'] == 'app_install_banner' ||
          e['photoClass'] == 'store_wordmark').length,
''' + needle, 1)

# Safety: the product row still receives the +8 score for the real shirt,
# but only after the narrow graphical exclusions above.
assert fn.index('if (shippingIconName ||') < fn.index('if (sectionProduct) score += 8;')
assert fn.index('if (installBannerByPixels)') < fn.index('if (sectionProduct) score += 8;')
assert "if (gmailTemuInstallText(ocr))" in fn
assert 'if (sectionProduct) score += 8;' in fn
s = s[:a] + fn + s[b:]
p.write_text(s)

p = Path('app/lib/packages.dart')
s = p.read_text()
needle = """        '\${n('smallStoreThumbnails')} miniaturas recuperadas · '"""
# The older report layout may vary; do not break builds if that line changed.
# The diagnostic is still exposed in analysisDiagnostics.
if needle in s:
    s = s.replace(needle,
        needle + """\n        '\${n('nonProductGraphics')} gráficos descartados · '""", 1)
    p.write_text(s)

print('v65: pixel/URL/OCR veto for green truck and Temu app-install ad precedes false productRowHint; shirt boost retained.')
