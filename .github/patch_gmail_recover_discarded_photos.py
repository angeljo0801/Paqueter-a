from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'No se encontró bloque esperado: {label}')
    return text.replace(old, new, 1)


helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

# Let the existing zoom/swipe gallery expose a restore action when it is opened
# from the discarded-images grid. Normal product galleries keep their current UI.
if 'bool allowRecover = false' not in hs:
    hs = replace_once(
        hs,
        "  int initialIndex = 0,\n}) async {\n",
        "  int initialIndex = 0,\n  bool allowRecover = false,\n  Set<String>? recoveredSink,\n}) async {\n",
        'Gmail gallery recover parameters',
    )

if "tooltip: 'Recuperar como producto'" not in hs:
    close_anchor = r'''              Positioned(
                right: 10,
                top: 10,
                child: IconButton.filled(
                  tooltip: 'Cerrar',
'''
    recover_button = r'''              if (allowRecover)
                Positioned(
                  left: 72,
                  top: 10,
                  child: IconButton.filledTonal(
                    tooltip: 'Recuperar como producto',
                    icon: const Icon(Icons.restore_from_trash_outlined),
                    onPressed: working.isEmpty
                        ? null
                        : () {
                            final image = working[currentIndex];
                            final raw = '${image['url'] ?? ''}'.trim();
                            if (raw.isEmpty) return;
                            recoveredSink?.add(raw);
                            if (working.length == 1) {
                              Navigator.pop(dialogContext);
                              return;
                            }
                            setDialog(() {
                              working.removeAt(currentIndex);
                              if (currentIndex >= working.length) {
                                currentIndex = working.length - 1;
                              }
                            });
                            WidgetsBinding.instance.addPostFrameCallback((_) {
                              if (controller.hasClients) {
                                controller.jumpToPage(currentIndex);
                              }
                            });
                          },
                  ),
                ),
'''
    hs = replace_once(
        hs,
        close_anchor,
        recover_button + close_anchor,
        'recover button in zoom gallery',
    )

# Recovered photos are accepted manually, so cache them without running the OCR
# rejection rules again. This preserves the existing offline-photo behavior.
if 'Future<Map<String, dynamic>> gmailCacheRecoveredPhoto(' not in hs:
    cache_helper = r'''
Future<Map<String, dynamic>> gmailCacheRecoveredPhoto(
  String baseUrl,
  String apiKey,
  Map<String, dynamic> image,
) async {
  final current = '${image['localPath'] ?? ''}'.trim();
  if (current.isNotEmpty && File(current).existsSync()) {
    return {...image, 'manuallyAccepted': true, 'photoClass': 'manual_product'};
  }
  final rawUrl = '${image['url'] ?? ''}'.trim();
  if (rawUrl.isEmpty) return {...image, 'manuallyAccepted': true};
  try {
    final response = await http.get(
      Uri.parse(gmailPhotoUrl(baseUrl, image)),
      headers: gmailPhotoHeaders(baseUrl, apiKey, image) ?? const <String, String>{},
    ).timeout(const Duration(seconds: 18));
    if (response.statusCode < 200 || response.statusCode >= 300 || response.bodyBytes.isEmpty) {
      return {...image, 'manuallyAccepted': true, 'photoClass': 'manual_product'};
    }
    final documents = await getApplicationDocumentsDirectory();
    final dir = Directory('${documents.path}/gmail_product_photos');
    if (!await dir.exists()) await dir.create(recursive: true);
    final digest = _gmailPhotoDigest(response.bodyBytes);
    final ext = _gmailPhotoExt(rawUrl, response.headers['content-type'] ?? '');
    final file = File('${dir.path}/$digest.$ext');
    if (!await file.exists()) await file.writeAsBytes(response.bodyBytes, flush: true);
    return {
      ...image,
      'localPath': file.path,
      'manuallyAccepted': true,
      'photoClass': 'manual_product',
      'rejectReason': '',
    };
  } catch (_) {
    return {...image, 'manuallyAccepted': true, 'photoClass': 'manual_product'};
  }
}

'''
    hs = replace_once(
        hs,
        'Future<Set<String>> showGmailRejectedPhotoGrid(\n',
        cache_helper + 'Future<Set<String>> showGmailRejectedPhotoGrid(\n',
        'offline cache helper for recovered Gmail photos',
    )

# Pass a recovery sink through the discarded thumbnail grid and remove recovered
# images from that grid immediately after the zoom viewer closes.
if 'Set<String>? recoveredOut,' not in hs:
    hs = replace_once(
        hs,
        "  required List<Map<String, dynamic>> images,\n}) async {\n  if (images.isEmpty) return <String>{};\n  final working = images.map((e) => Map<String, dynamic>.from(e)).toList();\n  final removed = <String>{};\n",
        "  required List<Map<String, dynamic>> images,\n  Set<String>? recoveredOut,\n}) async {\n  if (images.isEmpty) return <String>{};\n  final working = images.map((e) => Map<String, dynamic>.from(e)).toList();\n  final removed = <String>{};\n",
        'discarded grid recovery sink',
    )

old_grid_tap = r'''                        final removedNow = await openGmailPhotoGallery(
                          gridContext,
                          baseUrl: baseUrl,
                          apiKey: apiKey,
                          images: working,
                          initialIndex: index,
                        );
                        if (removedNow.isEmpty) return;
                        removed.addAll(removedNow);
                        setGrid(() {
                          working.removeWhere((e) =>
                              removedNow.contains('${e['url'] ?? ''}'.trim()));
                        });
'''
new_grid_tap = r'''                        final recoveredBefore = Set<String>.from(
                          recoveredOut ?? const <String>{},
                        );
                        final removedNow = await openGmailPhotoGallery(
                          gridContext,
                          baseUrl: baseUrl,
                          apiKey: apiKey,
                          images: working,
                          initialIndex: index,
                          allowRecover: true,
                          recoveredSink: recoveredOut,
                        );
                        final recoveredNow = (recoveredOut ?? <String>{})
                            .difference(recoveredBefore);
                        if (removedNow.isEmpty && recoveredNow.isEmpty) return;
                        removed.addAll(removedNow);
                        setGrid(() {
                          working.removeWhere((e) {
                            final url = '${e['url'] ?? ''}'.trim();
                            return removedNow.contains(url) || recoveredNow.contains(url);
                          });
                        });
'''
if old_grid_tap in hs:
    hs = hs.replace(old_grid_tap, new_grid_tap, 1)
else:
    raise SystemExit('No se encontró bloque esperado: discarded grid gallery tap')

helper_path.write_text(hs)


# ---------------- Packages ----------------
packages_path = Path('app/lib/packages.dart')
ps = packages_path.read_text()

if 'gmailManuallyAcceptedPhotoUrls' not in ps:
    ps = replace_once(
        ps,
        "  List<Map<String, dynamic>> gmailRejectedImages = [];\n",
        "  List<Map<String, dynamic>> gmailRejectedImages = [];\n  final Set<String> gmailManuallyAcceptedPhotoUrls = <String>{};\n",
        'package manually accepted Gmail photo state',
    )
    ps = replace_once(
        ps,
        "    gmailRejectedImages = dynList(widget.existing?['gmailRejectedImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n",
        "    gmailRejectedImages = dynList(widget.existing?['gmailRejectedImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n    gmailManuallyAcceptedPhotoUrls.addAll(dynList(widget.existing?['manuallyAcceptedGmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n",
        'package load manually accepted Gmail photos',
    )
    ps = replace_once(
        ps,
        "      'gmailRejectedImages': gmailRejectedImages,\n",
        "      'gmailRejectedImages': gmailRejectedImages,\n      'manuallyAcceptedGmailPhotoUrls': gmailManuallyAcceptedPhotoUrls.toList(),\n",
        'package save manually accepted Gmail photos',
    )

package_offline_anchor = "    final offline = result['offlinePaths'];\n    if (!mounted) return;\n"
if 'photoClass': 'manual_product' not in ps.split("Future<void> _smartFilterAndCacheGmailPhotos()", 1)[-1].split('Future<void>', 1)[0] if "Future<void> _smartFilterAndCacheGmailPhotos()" in ps else True:
    pass
# Preserve manual overrides when Gmail is reconstructed again.
manual_merge = r'''    if (gmailManuallyAcceptedPhotoUrls.isNotEmpty) {
      final forced = rejected
          .where((e) => gmailManuallyAcceptedPhotoUrls.contains('${e['url'] ?? ''}'.trim()))
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      for (final image in forced) {
        final url = '${image['url'] ?? ''}'.trim();
        accepted.add({
          ...image,
          'localPath': gmailOfflinePhotoPaths[url] ?? '${image['localPath'] ?? ''}',
          'manuallyAccepted': true,
          'photoClass': 'manual_product',
          'rejectReason': '',
        });
      }
      rejected.removeWhere(
        (e) => gmailManuallyAcceptedPhotoUrls.contains('${e['url'] ?? ''}'.trim()),
      );
    }
'''
if manual_merge.strip() not in ps:
    ps = replace_once(
        ps,
        package_offline_anchor,
        "    final offline = result['offlinePaths'];\n" + manual_merge + "    if (!mounted) return;\n",
        'package preserve recovered Gmail photos',
    )

old_package_show = r'''  Future<void> _showRejectedGmailPhotos() async {
    if (gmailRejectedImages.isEmpty) return;
    final removed = await showGmailRejectedPhotoGrid(
      context,
      baseUrl: gmailBackendUrl,
      apiKey: gmailApiKey,
      images: gmailRejectedImages,
    );
    if (!mounted || removed.isEmpty) return;
    setState(() {
      hiddenEmailPhotoUrls.addAll(removed);
      gmailRejectedImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
      emailPhotoUrls.removeWhere((e) => removed.contains(e.trim()));
      emailAttachmentImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
    });
  }
'''
new_package_show = r'''  Future<void> _showRejectedGmailPhotos() async {
    if (gmailRejectedImages.isEmpty) return;
    final recovered = <String>{};
    final removed = await showGmailRejectedPhotoGrid(
      context,
      baseUrl: gmailBackendUrl,
      apiKey: gmailApiKey,
      images: gmailRejectedImages,
      recoveredOut: recovered,
    );
    if (!mounted || (removed.isEmpty && recovered.isEmpty)) return;
    final recoveredRows = gmailRejectedImages
        .where((e) => recovered.contains('${e['url'] ?? ''}'.trim()))
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final cachedRecovered = <Map<String, dynamic>>[];
    for (final image in recoveredRows) {
      cachedRecovered.add(await gmailCacheRecoveredPhoto(
        gmailBackendUrl,
        gmailApiKey,
        image,
      ));
    }
    if (!mounted) return;
    setState(() {
      hiddenEmailPhotoUrls.addAll(removed);
      hiddenEmailPhotoUrls.removeAll(recovered);
      gmailManuallyAcceptedPhotoUrls.addAll(recovered);
      gmailRejectedImages.removeWhere((e) {
        final url = '${e['url'] ?? ''}'.trim();
        return removed.contains(url) || recovered.contains(url);
      });
      emailPhotoUrls.removeWhere((e) => removed.contains(e.trim()));
      emailAttachmentImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
      for (final image in cachedRecovered) {
        final url = '${image['url'] ?? ''}'.trim();
        final local = '${image['localPath'] ?? ''}'.trim();
        if (url.isEmpty) continue;
        if (local.isNotEmpty) gmailOfflinePhotoPaths[url] = local;
        if ('${image['kind']}' == 'attachment') {
          if (!emailAttachmentImages.any((e) => '${e['url'] ?? ''}'.trim() == url)) {
            final clean = Map<String, dynamic>.from(image)..remove('rejectReason');
            emailAttachmentImages.add(clean);
          }
        } else if (!emailPhotoUrls.contains(url)) {
          emailPhotoUrls.add(url);
        }
      }
    });
  }
'''
ps = replace_once(ps, old_package_show, new_package_show, 'package recover discarded Gmail photo')
packages_path.write_text(ps)


# ---------------- Purchases / orders ----------------
purchases_path = Path('app/lib/purchases.dart')
us = purchases_path.read_text()

if 'gmailPurchaseManuallyAcceptedPhotoUrls' not in us:
    us = replace_once(
        us,
        "  List<Map<String, dynamic>> gmailPurchaseRejectedImages = [];\n",
        "  List<Map<String, dynamic>> gmailPurchaseRejectedImages = [];\n  final Set<String> gmailPurchaseManuallyAcceptedPhotoUrls = <String>{};\n",
        'purchase manually accepted Gmail photo state',
    )
    us = replace_once(
        us,
        "      gmailPurchaseRejectedImages = dynList(widget.existing!['gmailRejectedImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n",
        "      gmailPurchaseRejectedImages = dynList(widget.existing!['gmailRejectedImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n      gmailPurchaseManuallyAcceptedPhotoUrls.addAll(dynList(widget.existing!['manuallyAcceptedGmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n",
        'purchase load manually accepted Gmail photos',
    )
    us = replace_once(
        us,
        "      'gmailRejectedImages': gmailPurchaseRejectedImages,\n",
        "      'gmailRejectedImages': gmailPurchaseRejectedImages,\n      'manuallyAcceptedGmailPhotoUrls': gmailPurchaseManuallyAcceptedPhotoUrls.toList(),\n",
        'purchase save manually accepted Gmail photos',
    )

purchase_manual_merge = r'''    if (gmailPurchaseManuallyAcceptedPhotoUrls.isNotEmpty) {
      final forced = rejected
          .where((e) => gmailPurchaseManuallyAcceptedPhotoUrls.contains('${e['url'] ?? ''}'.trim()))
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      for (final image in forced) {
        final url = '${image['url'] ?? ''}'.trim();
        accepted.add({
          ...image,
          'localPath': gmailPurchaseOfflinePhotoPaths[url] ?? '${image['localPath'] ?? ''}',
          'manuallyAccepted': true,
          'photoClass': 'manual_product',
          'rejectReason': '',
        });
      }
      rejected.removeWhere(
        (e) => gmailPurchaseManuallyAcceptedPhotoUrls.contains('${e['url'] ?? ''}'.trim()),
      );
    }
'''
if purchase_manual_merge.strip() not in us:
    us = replace_once(
        us,
        "    final offline = result['offlinePaths'];\n    if (!mounted) return;\n",
        "    final offline = result['offlinePaths'];\n" + purchase_manual_merge + "    if (!mounted) return;\n",
        'purchase preserve recovered Gmail photos',
    )

old_purchase_show = r'''  Future<void> _showRejectedPurchaseGmailPhotos() async {
    if (gmailPurchaseRejectedImages.isEmpty) return;
    final removed = await showGmailRejectedPhotoGrid(
      context,
      baseUrl: gmailPurchaseBackendUrl,
      apiKey: gmailPurchaseApiKey,
      images: gmailPurchaseRejectedImages,
    );
    if (!mounted || removed.isEmpty) return;
    setState(() {
      hiddenGmailPurchasePhotoUrls.addAll(removed);
      gmailPurchaseRejectedImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
      gmailPurchasePhotoUrls.removeWhere((e) => removed.contains(e.trim()));
      gmailPurchaseAttachmentImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
    });
  }
'''
new_purchase_show = r'''  Future<void> _showRejectedPurchaseGmailPhotos() async {
    if (gmailPurchaseRejectedImages.isEmpty) return;
    final recovered = <String>{};
    final removed = await showGmailRejectedPhotoGrid(
      context,
      baseUrl: gmailPurchaseBackendUrl,
      apiKey: gmailPurchaseApiKey,
      images: gmailPurchaseRejectedImages,
      recoveredOut: recovered,
    );
    if (!mounted || (removed.isEmpty && recovered.isEmpty)) return;
    final recoveredRows = gmailPurchaseRejectedImages
        .where((e) => recovered.contains('${e['url'] ?? ''}'.trim()))
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final cachedRecovered = <Map<String, dynamic>>[];
    for (final image in recoveredRows) {
      cachedRecovered.add(await gmailCacheRecoveredPhoto(
        gmailPurchaseBackendUrl,
        gmailPurchaseApiKey,
        image,
      ));
    }
    if (!mounted) return;
    setState(() {
      hiddenGmailPurchasePhotoUrls.addAll(removed);
      hiddenGmailPurchasePhotoUrls.removeAll(recovered);
      gmailPurchaseManuallyAcceptedPhotoUrls.addAll(recovered);
      gmailPurchaseRejectedImages.removeWhere((e) {
        final url = '${e['url'] ?? ''}'.trim();
        return removed.contains(url) || recovered.contains(url);
      });
      gmailPurchasePhotoUrls.removeWhere((e) => removed.contains(e.trim()));
      gmailPurchaseAttachmentImages.removeWhere(
        (e) => removed.contains('${e['url'] ?? ''}'.trim()),
      );
      for (final image in cachedRecovered) {
        final url = '${image['url'] ?? ''}'.trim();
        final local = '${image['localPath'] ?? ''}'.trim();
        if (url.isEmpty) continue;
        if (local.isNotEmpty) gmailPurchaseOfflinePhotoPaths[url] = local;
        if ('${image['kind']}' == 'attachment') {
          if (!gmailPurchaseAttachmentImages.any((e) => '${e['url'] ?? ''}'.trim() == url)) {
            final clean = Map<String, dynamic>.from(image)..remove('rejectReason');
            gmailPurchaseAttachmentImages.add(clean);
          }
        } else if (!gmailPurchasePhotoUrls.contains(url)) {
          gmailPurchasePhotoUrls.add(url);
        }
      }
    });
  }
'''
us = replace_once(us, old_purchase_show, new_purchase_show, 'purchase recover discarded Gmail photo')
purchases_path.write_text(us)

print('Discarded Gmail photos can now be restored from the zoom viewer.')
