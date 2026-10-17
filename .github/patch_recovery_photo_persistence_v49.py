from pathlib import Path

# v49 -- Gmail photo persistence must be a verified disk transaction, not a
# successful-looking preview. This applies to existing packages and purchases;
# new records still require their normal Save flow.

p = Path('app/lib/packages.dart')
s = p.read_text()
start = s.index('  Future<void> _persistRecoveredGmailSnapshot() async {')
end = s.index('  Future<void> removeMultipleEmailPhotos() async {', start)
replacement = r'''  Future<void> _persistRecoveredGmailSnapshot() async {
    // Bypass the list cache so that a stale screen cannot overwrite another
    // storage write without first seeing the latest package record.
    final rows = await Store.list('packages', forceRefresh: true);
    final existingId = '${widget.existing?['id'] ?? ''}'.trim();
    final track = tracking.text.trim();
    var index = -1;
    if (existingId.isNotEmpty) {
      index = rows.indexWhere((e) => '${e['id'] ?? ''}' == existingId);
    }
    if (index < 0 && existingId.isEmpty && track.isNotEmpty) {
      index = rows.indexWhere(
        (e) => '${e['tracking'] ?? ''}'.trim().toLowerCase() == track.toLowerCase(),
      );
    }
    if (index < 0) {
      throw StateError(
        'Las fotos aparecen, pero el paquete aún no existe en el almacenamiento. '
        'Guarda el paquete antes de vincularlo con Gmail.',
      );
    }
    final current = Map<String, dynamic>.from(rows[index]);
    final keptUrls = emailPhotoUrls
        .map((e) => e.trim()).where((e) => e.isNotEmpty && !hiddenEmailPhotoUrls.contains(e))
        .toList();
    final keptAttachments = emailAttachmentImages
        .where((e) {
          final url = (e['url'] ?? '').toString().trim();
          return url.isNotEmpty && !hiddenEmailPhotoUrls.contains(url);
        })
        .map((e) => Map<String, dynamic>.from(e)).toList();

    // An OCR/network regression must not erase confirmed, previously saved
    // photos if the new scan produced nothing. Explicit user removals remain.
    if (keptUrls.isEmpty && keptAttachments.isEmpty) {
      keptUrls.addAll(
        dynList(current['emailPhotoUrls']).map((e) => e.toString().trim())
          .where((e) => e.isNotEmpty && !hiddenEmailPhotoUrls.contains(e)),
      );
      keptAttachments.addAll(
        dynList(current['emailAttachmentImages']).whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .where((e) {
            final url = (e['url'] ?? '').toString().trim();
            return url.isNotEmpty && !hiddenEmailPhotoUrls.contains(url);
          }),
      );
    }
    final mergedOffline = <String, String>{
      ...((current['gmailOfflinePhotoPaths'] is Map)
          ? (current['gmailOfflinePhotoPaths'] as Map)
              .map((key, value) => MapEntry('$key', '$value'))
          : <String, String>{}),
      ...gmailOfflinePhotoPaths,
    };
    final updated = <String, dynamic>{
      ...current,
      'gmailStore': gmailStore.text.trim(),
      'gmailOrderNumber': gmailOrder.text.trim(),
      'gmailStatus': gmailStatus.text.trim(),
      'gmailEstimatedDelivery': gmailEta.text.trim(),
      'emailPhotoUrls': keptUrls,
      'emailAttachmentImages': keptAttachments,
      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),
      'gmailOfflinePhotoPaths': mergedOffline,
      'gmailRejectedImages': gmailRejectedImages.map((e) => Map<String, dynamic>.from(e)).toList(),
      'gmailPhotoAnalysisReport': gmailPhotoAnalysisReport,
      'gmailDeliveryPhotoHints': gmailDeliveryPhotoHints.toList(),
      'gmailSourceEmails': List<String>.from(gmailSourceEmails),
      'gmailItems': gmailItems.map((e) => Map<String, dynamic>.from(e)).toList(),
      'hiddenGmailItemKeys': hiddenGmailItemKeys.toList(),
      'gmailOcrScannedUrls': gmailOcrScannedUrls.toList(),
      'gmailLinkedAt': DateTime.now().toIso8601String(),
    };
    rows[index] = updated;
    await Store.saveList('packages', rows);
    Store.clearListCache('packages');
    final disk = await Store.list('packages', forceRefresh: true);
    final verified = disk.where((row) =>
        (row['id'] ?? '').toString() == (updated['id'] ?? '').toString()).toList();
    if (verified.length != 1 ||
        jsonEncode(verified.first['emailPhotoUrls']) != jsonEncode(keptUrls) ||
        jsonEncode(verified.first['emailAttachmentImages']) != jsonEncode(keptAttachments) ||
        jsonEncode(verified.first['gmailOfflinePhotoPaths']) != jsonEncode(mergedOffline)) {
      throw StateError('Las fotos no se pudieron verificar en el almacenamiento. '
          'La búsqueda seguirá disponible para recuperarlas.');
    }
  }

'''
# This method was injected by the v9 patch and must be replaced exactly once.
assert s.count('  Future<void> _persistRecoveredGmailSnapshot() async {') == 1
s=s[:start]+replacement+s[end:]
p.write_text(s)

# Purchases lacked an automatic write altogether: the link screen could show
# the images without writing any Gmail fields unless Save was tapped manually.
p=Path('app/lib/purchases.dart')
s=p.read_text()
anchor='  Future<void> linkPurchaseWithGmail() async {'
assert s.count(anchor)==1
method=r'''  Future<bool> _persistLinkedGmailPurchaseSnapshot() async {
    final id = '${widget.existing?['id'] ?? ''}'.trim();
    if (id.isEmpty) return false; // New purchases use the ordinary Save button.
    final rows = await Store.list('purchases', forceRefresh: true);
    final index = rows.indexWhere((row) => '${row['id'] ?? ''}' == id);
    if (index < 0) {
      throw StateError('No se encontró la compra guardada. '
          'Las fotos siguen en esta pantalla; no cierres sin guardar.');
    }
    final current = Map<String, dynamic>.from(rows[index]);
    final urls = gmailPurchasePhotoUrls
        .map((e) => e.trim()).where((e) => e.isNotEmpty && !hiddenGmailPurchasePhotoUrls.contains(e))
        .toList();
    final attachments = gmailPurchaseAttachmentImages
        .where((e) {
          final url = (e['url'] ?? '').toString().trim();
          return url.isNotEmpty && !hiddenGmailPurchasePhotoUrls.contains(url);
        }).map((e) => Map<String, dynamic>.from(e)).toList();

    // Preserve saved photos if this automatic lookup yielded zero new images.
    if (urls.isEmpty && attachments.isEmpty) {
      urls.addAll(dynList(current['emailPhotoUrls']).map((e) => e.toString().trim())
          .where((e) => e.isNotEmpty && !hiddenGmailPurchasePhotoUrls.contains(e)));
      attachments.addAll(dynList(current['emailAttachmentImages'])
          .whereType<Map>().map((e) => Map<String, dynamic>.from(e))
          .where((e) {
            final url = (e['url'] ?? '').toString().trim();
            return url.isNotEmpty && !hiddenGmailPurchasePhotoUrls.contains(url);
          }));
    }
    final offline = <String, String>{
      ...((current['gmailOfflinePhotoPaths'] is Map)
          ? (current['gmailOfflinePhotoPaths'] as Map)
              .map((key, value) => MapEntry('$key', '$value'))
          : <String, String>{}),
      ...gmailPurchaseOfflinePhotoPaths,
    };
    final updated = <String, dynamic>{
      ...current,
      'gmailLinkedOrderNumbers': List<String>.from(gmailLinkedOrderNumbers),
      'gmailSourceEmails': List<String>.from(gmailPurchaseSourceEmails),
      'gmailStatus': gmailPurchaseStatus,
      'gmailEstimatedDelivery': gmailPurchaseEta,
      'emailPhotoUrls': urls,
      'emailAttachmentImages': attachments,
      'hiddenEmailPhotoUrls': hiddenGmailPurchasePhotoUrls.toList(),
      'gmailOfflinePhotoPaths': offline,
      'gmailRejectedImages': gmailPurchaseRejectedImages
          .map((e) => Map<String, dynamic>.from(e)).toList(),
      'gmailDeliveryPhotoHints': gmailPurchaseDeliveryPhotoHints.toList(),
      'gmailLinkedAt': DateTime.now().toIso8601String(),
    };
    rows[index] = updated;
    await Store.saveList('purchases', rows);
    Store.clearListCache('purchases');
    final disk = await Store.list('purchases', forceRefresh: true);
    final matches = disk.where((row) => (row['id'] ?? '').toString() == id).toList();
    if (matches.length != 1 ||
        jsonEncode(matches.first['emailPhotoUrls']) != jsonEncode(urls) ||
        jsonEncode(matches.first['emailAttachmentImages']) != jsonEncode(attachments) ||
        jsonEncode(matches.first['gmailOfflinePhotoPaths']) != jsonEncode(offline)) {
      throw StateError('No se pudieron verificar las fotos guardadas de la compra.');
    }
    return true;
  }

'''
s=s.replace(anchor,method+anchor,1)
a=s.index('  Future<void> linkPurchaseWithGmail() async {')
b=s.find('\n  Future<void> ',a+10)
if b<0: b=len(s)
fn=s[a:b]
old='''      await _smartFilterAndCachePurchaseGmailPhotos();'''
assert fn.count(old)==1
fn=fn.replace(old,'''      await _smartFilterAndCachePurchaseGmailPhotos();
      final saved = await _persistLinkedGmailPurchaseSnapshot();''',1)
old="""'Compra vinculada con Gmail: ${items.length} artículo(s), ${_purchaseEmailPhotoEntries().length} foto(s).'"""
assert fn.count(old)==1
fn=fn.replace(old,"""saved
                  ? 'Compra vinculada: ${_purchaseEmailPhotoEntries().length} fotos guardadas y verificadas.'
                  : 'Fotos encontradas: ${_purchaseEmailPhotoEntries().length}. Pulsa Guardar para conservarlas.'""",1)
# Do not conceal persistence failure behind a success snackbar.
old='''    } finally {
      if (mounted) setState(() => gmailPurchaseLoading = false);
    }'''
assert fn.count(old)==1
fn=fn.replace(old,'''    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No se pudieron guardar las fotos: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => gmailPurchaseLoading = false);
    }''',1)
s=s[:a]+fn+s[b:]
p.write_text(s)
print('Gmail v49: verified package photo persistence; purchase auto-save on existing purchases; no silent false success.')
