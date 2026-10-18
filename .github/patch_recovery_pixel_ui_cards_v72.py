from pathlib import Path

# v72: Pixel-only visual veto for the two remaining screenshots:
# - muted-green standalone shield/check graphic, even when OCR is empty;
# - actual marketplace listing with repeated BLACK star glyphs + CART in a
#   WHITE footer, even when OCR does not see the cart/stars/prices.
# Veto before section/retailer boost, with explicit manual recovery preserved.
# Recheck package gallery after all legacy fallback merges to prevent an old
# cached snapshot or original/thumbnail alias from resurrecting these graphics.
p = Path('app/lib/gmail_purchase_link.dart')
s = p.read_text()
entry = 'Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
assert s.count(entry) == 1, 'v72: shared Gmail classifier missing'

helpers = r'''
// Strong pixel signature of the *shield shape*, not merely green merchandise.
// We require: two sloping side strokes, top cap, pointed bottom, central check,
// and a nearly empty upper-center interior, all in saturated green on a
// low-detail, similarly colored square tile. A green item/photo is not enough.
Future<bool> gmailLooksLikeShieldCheckArtwork(
  List<int> bytes, int width, int height,
) async {
  if (width < 90 || height < 90 || width > 512 || height > 512 ||
      width / height < 0.78 || width / height > 1.30) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes), targetWidth: 96, targetHeight: 96,
    );
    try {
      final frame = await codec.getNextFrame();
      try {
        final data = await frame.image.toByteData(
          format: ui.ImageByteFormat.rawRgba,
        );
        if (data == null) return false;
        final pixels = data.buffer.asUint8List();
        final w = frame.image.width, h = frame.image.height;
        final histogram = <int>{};
        var visible = 0, greenStrong = 0;
        final mask = List<bool>.filled(w * h, false);
        for (var y = 0; y < h; y++) {
          for (var x = 0; x < w; x++) {
            final i = (y * w + x) * 4;
            if (i + 3 >= pixels.length || pixels[i + 3] < 128) continue;
            final red = pixels[i], green = pixels[i + 1],
                blue = pixels[i + 2];
            visible++;
            histogram.add(((red >> 5) << 6) |
                ((green >> 5) << 3) | (blue >> 5));
            final on = green >= 95 && green - red >= 80 &&
                green - blue >= 75;
            mask[y * w + x] = on;
            if (on) greenStrong++;
          }
        }
        if (visible < 1000 || histogram.length > 26 ||
            greenStrong / visible < .12 ||
            greenStrong / visible > .58) return false;

        double coverage(double x1, double x2, double y1, double y2) {
          final xStart = (x1 * w).floor().clamp(0, w - 1);
          final xEnd = (x2 * w).ceil().clamp(xStart + 1, w);
          final yStart = (y1 * h).floor().clamp(0, h - 1);
          final yEnd = (y2 * h).ceil().clamp(yStart + 1, h);
          var matching = 0, area = 0;
          for (var y = yStart; y < yEnd; y++) {
            for (var x = xStart; x < xEnd; x++) {
              area++;
              if (mask[y * w + x]) matching++;
            }
          }
          return area == 0 ? 0 : matching / area;
        }

        return coverage(.02, .23, .26, .67) >= .18 &&
            coverage(.77, .98, .26, .67) >= .18 &&
            coverage(.22, .76, .03, .21) >= .18 &&
            coverage(.30, .72, .70, .92) >= .15 &&
            coverage(.25, .72, .40, .67) >= .14 &&
            coverage(.35, .65, .24, .38) <= .09;
      } finally {
        frame.image.dispose();
      }
    } finally {
      codec.dispose();
    }
  } catch (_) {
    return false;
  }
}

// A cart/stars retailer listing is a *screen UI* rather than a product-only
// photo: a colorful photographic top, broad white lower footer, a run of
// four/five evenly spaced dark star-shaped glyphs at the footer's left,
// and the dark outline of a cart button at the footer's lower-right.
// No OCR needed. One black product or a normal price is never enough.
Future<bool> gmailLooksLikeStarCartMarketplaceListing(
  List<int> bytes, int width, int height,
) async {
  if (width < 180 || height < 230 ||
      width / height < .48 || width / height > 1.85) return false;
  try {
    final codec = await ui.instantiateImageCodec(
      Uint8List.fromList(bytes), targetWidth: 128, targetHeight: 128,
    );
    try {
      final frame = await codec.getNextFrame();
      try {
        final data = await frame.image.toByteData(
          format: ui.ImageByteFormat.rawRgba,
        );
        if (data == null) return false;
        final px = data.buffer.asUint8List();
        final w = frame.image.width, h = frame.image.height;
        bool dark(int x, int y) {
          final i = (y * w + x) * 4;
          return px[i + 3] >= 128 &&
              px[i] < 110 && px[i + 1] < 110 && px[i + 2] < 110;
        }
        bool pale(int x, int y) {
          final i = (y * w + x) * 4;
          return px[i + 3] >= 128 &&
              px[i] >= 205 && px[i + 1] >= 205 && px[i + 2] >= 205;
        }
        double regionRatio(double x1, double x2, double y1, double y2,
            bool Function(int, int) test) {
          final xStart = (w * x1).floor().clamp(0, w - 1);
          final xEnd = (w * x2).ceil().clamp(xStart + 1, w);
          final yStart = (h * y1).floor().clamp(0, h - 1);
          final yEnd = (h * y2).ceil().clamp(yStart + 1, h);
          var match = 0, total = 0;
          for (var y = yStart; y < yEnd; y++) {
            for (var x = xStart; x < xEnd; x++) {
              total++;
              if (test(x, y)) match++;
            }
          }
          return total == 0 ? 0 : match / total;
        }
        if (regionRatio(0, 1, .73, 1, pale) < .67 ||
            regionRatio(0, 1, 0, .62, pale) > .53 ||
            regionRatio(.73, .99, .88, 1, pale) < .50 ||
            regionRatio(.73, .99, .88, 1, dark) < .020) {
          return false;
        }

        // Project each black star's vertical strokes onto the x-axis.
        // Four nearly equally spaced groups in ONE thin row excludes ordinary
        // words, isolated text, products with a price, and logistics banners.
        bool starRun(double y1, double y2) {
          final firstY = (y1 * h).floor();
          final lastY = (y2 * h).ceil();
          final minPixels = ((lastY - firstY) * .19).ceil();
          final groups = <double>[];
          int? start;
          final endX = (w * .50).floor();
          for (var x = 0; x <= endX; x++) {
            var active = false;
            if (x < endX) {
              var count = 0;
              for (var y = firstY; y < lastY; y++) {
                if (dark(x, y)) count++;
              }
              active = count >= minPixels;
            }
            if (active && start == null) start = x;
            if (!active && start != null) {
              final span = x - start;
              if (span >= w * .014 && span <= w * .075) {
                groups.add((start + x) / 2.0);
              }
              start = null;
            }
          }
          if (groups.length < 4) return false;
          for (var i = 0; i + 3 < groups.length; i++) {
            final gaps = <double>[
              groups[i + 1] - groups[i],
              groups[i + 2] - groups[i + 1],
              groups[i + 3] - groups[i + 2],
            ];
            if (gaps.every((d) => d >= w * .055 && d <= w * .125)) {
              var minimum = gaps.first, maximum = gaps.first;
              for (final d in gaps) {
                if (d < minimum) minimum = d;
                if (d > maximum) maximum = d;
              }
              if (maximum - minimum <= w * .047) return true;
            }
          }
          return false;
        }

        return starRun(.81, .89) || starRun(.77, .86);
      } finally {
        frame.image.dispose();
      }
    } finally {
      codec.dispose();
    }
  } catch (_) {
    return false;
  }
}

'''
s = s.replace(entry, helpers + entry, 1)
start = s.index(entry)
end = s.index('\nWidget gmailSmartPhotoImage(', start)
fn = s[start:end]

# EARLY visual veto, before generic size scoring, provenance, item matching,
# OCR budget exhaustion, sectionProduct or inherited score heuristics.
point = '''      final photographicRowCandidate =
          await gmailLooksLikePhotoAndBriefLabelRow(bytes, width, height);'''
assert fn.count(point) == 1, 'v72: early decode-to-photo decision moved'
block = r'''      if (image['manuallyAccepted'] != true) {
        final securityShield =
            await gmailLooksLikeShieldCheckArtwork(bytes, width, height);
        final starCartListing = !securityShield &&
            await gmailLooksLikeStarCartMarketplaceListing(
              bytes, width, height);
        if (securityShield || starCartListing) {
          rejected.add({
            ...image,
            'width': width,
            'height': height,
            'rejectReason': securityShield
                ? 'escudo gráfico de seguridad (no artículo)'
                : 'tarjeta de catálogo: estrellas y carrito (no artículo)',
            // Existing v59-v71 fallback restrictions already protect these
            // classes; the photo remains in manual discarded review.
            'photoClass': securityShield ? 'store_wordmark' : 'catalog_card',
          });
          continue;
        }
      }
'''
fn = fn.replace(point, block + point, 1)
assert fn.index('gmailLooksLikeShieldCheckArtwork(bytes, width, height)') < fn.index('final photographicRowCandidate =')
assert fn.index('gmailLooksLikeStarCartMarketplaceListing(') < fn.index('if (sectionProduct) score += 8;')
assert 'if (shortItemPhotoRow) score += 6;' in fn
s = s[:start] + fn + s[end:]
p.write_text(s)

# The old "show something if no product found" gallery fallback could
# resurrect *exactly* a hard-rejected icon or listing from an earlier
# accepted photo (or a different cached/original CDN URL). After ALL fallback
# logic finishes, remove those automatic inserts by both URL and image ID.
# Explicit manual recovery always overrides automated rejection.
p = Path('app/lib/packages.dart')
s = p.read_text()
a = s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b = s.index('  Future<void> _showRejectedGmailPhotos() async {', a)
fn = s[a:b]
anchor = "    final offline = result['offlinePaths'];"
assert fn.count(anchor) == 1, 'v72: package fallback finalization moved'
final_guard = r'''    final confirmedGraphics = rejected.where((image) =>
        image['photoClass'] == 'store_wordmark' ||
        image['photoClass'] == 'catalog_card' ||
        image['photoClass'] == 'delivery_status_banner' ||
        image['photoClass'] == 'logistics_icon' ||
        image['photoClass'] == 'app_install_banner' ||
        image['photoClass'] == 'delivery_proof').toList();

    final blockedImageAliases = <String>{};
    final blockedIdentities = <String>{};
    for (final image in confirmedGraphics) {
      for (final field in <String>['url', 'originalUrl', 'thumbnailUrl']) {
        final alias = (image[field] ?? '').toString().trim();
        if (alias.isNotEmpty) blockedImageAliases.add(alias);
      }
      final identity = _gmailCandidateIdentity(image);
      if (identity.isNotEmpty) blockedIdentities.add(identity);
    }
    accepted.removeWhere((image) {
      final url = (image['url'] ?? '').toString().trim();
      if (image['manuallyAccepted'] == true ||
          gmailManuallyAcceptedPhotoUrls.contains(url)) return false;
      for (final field in <String>['url', 'originalUrl', 'thumbnailUrl']) {
        final alias = (image[field] ?? '').toString().trim();
        if (alias.isNotEmpty && blockedImageAliases.contains(alias)) {
          return true;
        }
      }
      final identity = _gmailCandidateIdentity(image);
      return identity.isNotEmpty && blockedIdentities.contains(identity);
    });
'''
fn = fn.replace(anchor, final_guard + anchor, 1)
assert fn.index('final confirmedGraphics =') < fn.index("final offline = result['offlinePaths'];")
s = s[:a] + fn + s[b:]
p.write_text(s)
print('v72: pixel-based security shield and star+cart listing veto BEFORE OCR, plus final package fallback protection.')
