from pathlib import Path

p = Path('app/lib/background_sync.dart')
s = p.read_text()
old = '''      final result = await _processPackagePhotosInBackground(
        result: rawResult,
        baseUrl: '${data['baseUrl'] ?? ''}',
        apiKey: '${data['apiKey'] ?? ''}',
        packageId: '${data['packageId'] ?? ''}',
        tracking: '${data['tracking'] ?? ''}',
      );'''
new = '''    // WorkManager's headless FlutterEngine cannot use the Activity native
    // per-key preferences channel, and the old getAll() can fail when local
    // photo lists are large. Save the COMPLETE RAW Gmail payload durably.
    // When the editor resumes, its main engine prepares all candidate photos.
    // Never acknowledge a result with empty pictures just because a headless
    // isolate could not load the preference database.
    final result = <String, dynamic>{
      ...rawResult,
      '_backgroundProcessed': false,
      '_photosWaitingForEditor': true,
      '_backgroundPhotoCount': 0,
      '_backgroundPhotoCandidateCount':
          _backgroundPhotoCandidates(rawResult, <String>{}).length,
    };'''
if s.count(old)!=1: raise SystemExit('Gmail v41: background photo premature processing anchor changed')
s=s.replace(old,new,1)
old_note = '''          : '$photoCount foto(s) preparada(s)$suffix','''
new_note = '''          : photoCount < 0
              ? 'Correos encontrados. Abre el paquete para preparar fotos$suffix'
              : '$photoCount foto(s) preparada(s)$suffix','''
if s.count(old_note)!=1:raise SystemExit('Gmail v41: background notification anchor changed')
s=s.replace(old_note,new_note,1)
old_photo_count='''      photoCount: (result['_backgroundPhotoCount'] as num?)?.toInt() ?? 0,'''
new_photo_count='''      photoCount: result['_photosWaitingForEditor'] == true
          ? -1 : (result['_backgroundPhotoCount'] as num?)?.toInt() ?? 0,'''
if s.count(old_photo_count)!=1:raise SystemExit('Gmail v41: background completion notification count changed')
s=s.replace(old_photo_count,new_photo_count,1)
p.write_text(s)

p=Path('app/lib/packages.dart')
s=p.read_text()
start=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
end=s.index('  Future<void> _showRejectedGmailPhotos() async {',start)
method=s[start:end]
old='''    final offline = result['offlinePaths'];'''
new='''    // If filtering could not certify any picture, retain every candidate in
    // the manual-review gallery. Do not silently discard product photos when
    // OCR, image fetching or aggressive catalog detection returns zero.
    final seen = <String>{
      for (final image in accepted) '${image['url'] ?? ''}'.trim(),
      for (final image in rejected) '${image['url'] ?? ''}'.trim(),
    };
    if (accepted.isEmpty) {
      for (final image in allImages) {
        final url = '${image['url'] ?? ''}'.trim();
        if (url.isEmpty || !seen.add(url)) continue;
        rejected.add({
          ...image,
          'rejectReason': 'sin verificar; revisar manualmente',
        });
      }
    }
    final offline = result['offlinePaths'];'''
if method.count(old)!=1:raise SystemExit('Gmail v41: photo filtering anchor changed')
method=method.replace(old,new,1)
s=s[:start]+method+s[end:]
# Existing discard button lives inside the photo grid; it vanishes when all
# images have been rejected. Give the user a separate way to inspect them.
anchor="""        TextField(controller: gmailStore, decoration: const InputDecoration(labelText: 'Tienda detectada / tienda')),"""
add="""        if (gmailRejectedImages.isNotEmpty &&
            emailPhotoUrls.isEmpty && emailAttachmentImages.isEmpty)
          Card(
            child: ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: Text('Imágenes del correo por revisar (${gmailRejectedImages.length})'),
              subtitle: const Text(
                'No se confirmó automáticamente ninguna foto como artículo. '
                'Puedes revisar y recuperar las correctas, sin perderlas.',
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: _showRejectedGmailPhotos,
            ),
          ),
        TextField(controller: gmailStore, decoration: const InputDecoration(labelText: 'Tienda detectada / tienda')),"""
if s.count(anchor)!=1:raise SystemExit('Gmail v41: editor review card anchor changed')
s=s.replace(anchor,add,1)
p.write_text(s)
print('Gmail v41: background preserves raw photo payload; foreground review never silently loses candidates.')


# v46: server-prepared media must be actually used by the editor.
# They are authenticated/cached on Railway; original Temu/SHEIN CDN URLs may
# reject direct Android requests even though the server already downloaded them.
p = Path('app/lib/packages.dart')
s = p.read_text()
start = s.index('  Future<void> reconstructFromGmail() async {')
end = s.index('  Future<void> openEmailPhoto(', start)
method = s[start:end]
anchor = "        for (final value in dynList(data['emailPhotoUrls'])) {\n"
if method.count(anchor) != 1:
    raise SystemExit('Gmail v46: package editor raw-photo insertion changed')
insertion = """        // Prefer prepared copies served by WhatsBot. Do not discard the original
        // URLs: either one can still be useful if its counterpart has expired.
        for (final value in dynList(data['emailPhotoCandidates'])) {
          if (value is! Map) continue;
          final row = Map<String, dynamic>.from(value);
          final url = (row['url'] ?? '').toString().trim();
          if (url.isEmpty || hiddenEmailPhotoUrls.contains(url)) continue;
          if (row['kind'] == 'attachment') {
            if (!emailAttachmentImages.any(
                (e) => (e['url'] ?? '').toString().trim() == url)) {
              emailAttachmentImages.add(row);
            }
          } else if (!emailPhotoUrls.contains(url)) {
            emailPhotoUrls.add(url);
          }
        }
"""
method=method.replace(anchor,insertion+anchor,1)
s=s[:start]+method+s[end:]
p.write_text(s)

# Never replace an existing confirmed photo with an empty automated decision.
# Manual rejection still works; previously saved photos belong to the user.
p = Path('app/lib/packages.dart')
s = p.read_text()
start = s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
end = s.index('  Future<void> _showRejectedGmailPhotos() async {',start)
method=s[start:end]
anchor = "    if (accepted.isEmpty) {\n"
if method.count(anchor) != 1:
    raise SystemExit('Gmail v46: fallback gate changed')
preserve = """    if (accepted.isEmpty) {
      final previousUrls = <String>{
        ...dynList(widget.existing?['emailPhotoUrls'])
            .map((e) => e.toString().trim()),
        ...dynList(widget.existing?['emailAttachmentImages'])
            .whereType<Map>()
            .map((e) => (e['url'] ?? '').toString().trim()),
      };
      final present = <String>{
        ...accepted.map((e) => (e['url'] ?? '').toString().trim()),
      };
      for (final image in allImages) {
        final url = (image['url'] ?? '').toString().trim();
        if (url.isEmpty || !previousUrls.contains(url) ||
            hiddenEmailPhotoUrls.contains(url) || !present.add(url)) continue;
        accepted.add({...image, 'photoClass': 'previously_saved'});
      }
      rejected.removeWhere((e) =>
          present.contains((e['url'] ?? '').toString().trim()));
    }
"""
method=method.replace(anchor,preserve+anchor,1)
s=s[:start]+method+s[end:]
p.write_text(s)

# Purchase photo filter must also never erase every candidate without giving
# the owner a review path. Rejecting an image is different from losing it.
p=Path('app/lib/purchases.dart')
s=p.read_text()
start=s.index('  Future<void> _smartFilterAndCachePurchaseGmailPhotos() async {')
end=s.index('  Future<void> _showRejectedPurchaseGmailPhotos() async {',start)
method=s[start:end]
anchor="    final offline = result['offlinePaths'];"
if method.count(anchor)!=1: raise SystemExit('Gmail v46: purchase fallback changed')
method=method.replace(anchor,"""    if (accepted.isEmpty) {
      final seen = <String>{
        ...rejected.map((e) => (e['url'] ?? '').toString().trim()),
      };
      for (final image in allImages) {
        final url = (image['url'] ?? '').toString().trim();
        if (url.isEmpty || !seen.add(url)) continue;
        rejected.add({...image, 'rejectReason': 'sin verificar; revisar manualmente'});
      }
    }
"""+anchor,1)
s=s[:start]+method+s[end:]
p.write_text(s)
print('Gmail v46: worker preserves raw result, server thumbnails are used, prior photos survive empty filters.')
