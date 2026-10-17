from pathlib import Path

p=Path('app/lib/packages.dart')
s=p.read_text()
anchor='  Future<void> _stageGmailCandidateInbox() async {'
assert s.count(anchor)==1, 'v52: inbox method changed'
helper=r'''  String _gmailInboxStorageKey() {
    final id = (widget.existing?['id'] ?? '').toString().trim();
    if (id.isNotEmpty) return 'gmailCandidateInbox_package_$id';
    final track = tracking.text.trim().toLowerCase();
    if (track.isEmpty) return '';
    return 'gmailCandidateInbox_tracking_$track';
  }

  Future<void> _saveGmailCandidateInboxIndependently() async {
    final key = _gmailInboxStorageKey();
    if (key.isEmpty) return;
    final unique = <String, Map<String, dynamic>>{};
    for (final image in gmailCandidateInbox) {
      final url = (image['url'] ?? '').toString().trim();
      if (url.isEmpty) continue;
      final minimal = Map<String, dynamic>.from(image);
      final ocr = (minimal['ocrText'] ?? '').toString();
      if (ocr.length > 700) minimal['ocrText'] = ocr.substring(0, 700);
      minimal.remove('bytes');
      minimal.remove('html');
      unique[url] = minimal;
    }
    await Store._writeRaw(key, jsonEncode(unique.values.toList()));
    final check = await Store._readRaw(key);
    final verified = check == null ? const <dynamic>[] : dynList(jsonDecode(check));
    if (verified.length != unique.length) {
      throw StateError('No se pudo verificar la copia de las imágenes Gmail.');
    }
  }

  Future<void> _loadGmailCandidateInboxIndependently() async {
    final key = _gmailInboxStorageKey();
    if (key.isEmpty) return;
    final raw = await Store._readRaw(key);
    if (raw == null || raw.isEmpty) return;
    final rows = dynList(jsonDecode(raw)).whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e)).toList();
    final merged = <String, Map<String, dynamic>>{};
    for (final image in [...gmailCandidateInbox, ...rows]) {
      final url = (image['url'] ?? '').toString().trim();
      if (url.isEmpty) continue;
      merged[url] = image;
    }
    gmailCandidateInbox = merged.values.toList();
    _restoreGmailCandidateInboxReview();
  }

  Future<void> _openGmailCandidateReview() async {
    try {
      await _loadGmailCandidateInboxIndependently();
      if (!mounted) return;
      if (gmailRejectedImages.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text(
            'No hay imágenes guardadas para revisar en este paquete. '
            'Ejecuta una búsqueda nueva de Gmail.',
          )),
        );
        return;
      }
      setState(() {});
      await _showRejectedGmailPhotos();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('No se pudo abrir la bandeja de Gmail: $e')),
      );
    }
  }

'''
s=s.replace(anchor,helper+anchor,1)
a=s.index('  Future<void> _stageGmailCandidateInbox() async {')
b=s.index('  void _restoreGmailCandidateInboxReview()',a)
part=s[a:b]
line='    gmailCandidateInbox = inbox;'
assert part.count(line)==1
part=part.replace(line,line+"\n    await _saveGmailCandidateInboxIndependently();",1)
s=s[:a]+part+s[b:]
anchor='    if (mounted) {\n      setState(() => loaded = true);'
assert s.count(anchor)==1, 'v52: editor init finish changed'
s=s.replace(anchor,'''    try {
      await _loadGmailCandidateInboxIndependently();
    } catch (e) {
      debugPrint('Gmail inbox reload skipped: $e');
    }
'''+anchor,1)
anchor="        TextField(controller: gmailStore, decoration: const InputDecoration(labelText: 'Tienda detectada / tienda')),"
assert s.count(anchor)==1, 'v52: review control anchor changed'
control=r'''        OutlinedButton.icon(
          onPressed: gmailLoading ? null : _openGmailCandidateReview,
          icon: const Icon(Icons.photo_library_outlined),
          label: Text(gmailCandidateInbox.isEmpty
              ? 'Ver y recuperar imágenes de Gmail'
              : 'Ver y recuperar imágenes de Gmail (' +
                  gmailCandidateInbox.length.toString() + ')'),
        ),
        const SizedBox(height: 8),
'''
s=s.replace(anchor,control+anchor,1)
p.write_text(s)
assert "onPressed: gmailLoading ? null : _openGmailCandidateReview" in s
print('v52: candidate inbox stored per-package separately from all package writes.')
