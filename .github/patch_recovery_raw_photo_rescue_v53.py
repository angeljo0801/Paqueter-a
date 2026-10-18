from pathlib import Path

# Recovery v53: the raw Gmail server result is the earliest reliable source
# of photos. Capture it BEFORE any UI/filtering/background branches can clear
# photo arrays. Also make recovery available next to the Save button, so it is
# impossible to miss when the gallery disappears.
p=Path('app/lib/packages.dart')
s=p.read_text()
marker='  Future<void> _stageGmailCandidateInbox() async {'
assert s.count(marker)==1, 'raw capture: v51 stage anchor unavailable'
function=r'''  String gmailPhotoInboxStatus = '';

  Future<void> _captureRawGmailPhotoResult(Map<String, dynamic> data) async {
    final candidates = <Map<String, dynamic>>[];
    final seen = <String>{};

    void add(Map<String, dynamic> image) {
      final url = (image['url'] ?? '').toString().trim();
      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url) || !seen.add(url)) return;
      candidates.add(Map<String, dynamic>.from(image));
    }

    // Server-prepared image candidates include authenticated Railway media.
    // Preserve them before the OCR and email-state transformations start.
    for (final value in dynList(data['emailPhotoCandidates'])) {
      if (value is Map) add(Map<String, dynamic>.from(value));
    }
    for (final value in dynList(data['emailPhotoUrls'])) {
      final url = value.toString().trim();
      if (url.isNotEmpty) add({'kind': 'remote', 'url': url, 'name': ''});
    }
    for (final value in dynList(data['emailAttachmentImages'])) {
      if (value is Map) add(Map<String, dynamic>.from(value));
    }
    if (candidates.isEmpty) {
      gmailPhotoInboxStatus = data['_backgroundPending'] == true
          ? 'Gmail continúa buscando; las fotos se recuperarán al finalizar.'
          : 'El servidor no devolvió imágenes en esta respuesta.';
      if (mounted) setState(() {});
      return;
    }
    final merged = <String, Map<String, dynamic>>{};
    for (final image in [...gmailCandidateInbox, ...candidates]) {
      final url = (image['url'] ?? '').toString().trim();
      if (url.isNotEmpty && !hiddenEmailPhotoUrls.contains(url)) merged[url] = image;
    }
    gmailCandidateInbox = merged.values.toList();

    // Write an independent per-package snapshot immediately, before any
    // return, reject, OCR exception, ack, or background merge can occur.
    await _saveGmailCandidateInboxIndependently();
    gmailPhotoInboxStatus = 'Bandeja Gmail: ' +
        gmailCandidateInbox.length.toString() +
        ' imágenes conservadas para revisión.';
    _restoreGmailCandidateInboxReview();
    if (mounted) setState(() {});
  }

'''
s=s.replace(marker,function+marker,1)

a=s.index('  Future<void> reconstructFromGmail() async {')
b=s.index('  Future<void> openEmailPhoto(',a)
method=s[a:b]
head="      final data = await GmailBackgroundSearch.reconstruct("
idx=method.find(head)
assert idx>=0, 'raw capture: Gmail reconstruct invocation absent'
close=method.index('\n      );',idx)+len('\n      );')
method=method[:close]+r'''
      // Capture the untouched server images. The later classifier may reject
      // everything, but this per-package photo inbox will stay available.
      try {
        await _captureRawGmailPhotoResult(data);
      } catch (e) {
        gmailPhotoInboxStatus = 'Error al conservar imágenes de Gmail: $e';
        if (mounted) {
          setState(() {});
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(gmailPhotoInboxStatus)),
          );
        }
      }
'''+method[close:]
s=s[:a]+method+s[b:]

# The first inbox review button was above the Gmail metadata inputs. Users
# usually look for photos at the END of the editor, next to Guardar paquete.
# Give it a second permanent, distinct entry point here.
foot="        FilledButton.icon(onPressed: save, icon: const Icon(Icons.save), label: const Text('Guardar paquete')),"
assert s.count(foot)==1, 'raw capture: main Save button changed'
review=r'''        OutlinedButton.icon(
          onPressed: _openGmailCandidateReview,
          icon: const Icon(Icons.photo_library_outlined),
          label: const Text('Ver / recuperar fotos de Gmail'),
        ),
        if (gmailPhotoInboxStatus.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: SelectableText(
              gmailPhotoInboxStatus,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        const SizedBox(height: 8),
'''
s=s.replace(foot,review+foot,1)
p.write_text(s)

assert "await _captureRawGmailPhotoResult(data);" in s
assert "label: const Text('Ver / recuperar fotos de Gmail')" in s
print('v53: raw candidate capture before photo pipeline, independent disk inbox, visible button next to Save.')
