from pathlib import Path

p = Path('app/lib/background_sync.dart')
s = p.read_text()
old = '''    final result = await _processPackagePhotosInBackground(
      result: rawResult,
      baseUrl: baseUrl,
      apiKey: apiKey,
      packageId: packageId,
      tracking: tracking,
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
