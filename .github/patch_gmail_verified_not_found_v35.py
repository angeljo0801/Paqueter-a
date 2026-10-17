from pathlib import Path

def one(src, old, new, label):
    count = src.count(old)
    if count != 1:
        raise SystemExit(f'Gmail v35: {label}: expected one anchor, got {count}')
    return src.replace(old, new, 1)


helper = Path('app/lib/gmail_purchase_link.dart')
h = helper.read_text()

h = one(h,
"""  return status == 'not_found';
}

Future<void> persistPackageGmailLookupState({""",
"""  if (status != 'not_found') return false;
  final checkedTracking = '${record['gmailLookupTracking'] ?? ''}'.trim().toLowerCase();
  final currentTracking = '${record['tracking'] ?? ''}'.trim().toLowerCase();
  return checkedTracking.isEmpty || currentTracking.isEmpty ||
      checkedTracking == currentTracking;
}

Future<void> persistPackageGmailLookupState({""",
'not-found must match the tracking currently shown')

h = one(h,
"""  if (index < 0) return;

  rows[index] = {
    ...rows[index],
    'gmailLookupStatus': state,
    'gmailBulkLastResult': state,
    'gmailLastCheckedAt': DateTime.now().toIso8601String(),
  };
""",
"""  if (index < 0) return;
  // An old WorkManager job must not overwrite a package whose tracking has
  // since been edited.
  if (cleanTracking.isNotEmpty &&
      '${rows[index]['tracking'] ?? ''}'.trim().toLowerCase() != cleanTracking) {
    return;
  }
  final isNotFound = state == 'not_found';
  rows[index] = {
    ...rows[index],
    'gmailLookupStatus': state,
    'gmailLookupTracking': tracking.trim(),
    'gmailBulkLastResult': state,
    'gmailLastCheckedAt': DateTime.now().toIso8601String(),
    // Do not destroy manual photos, product corrections or store information.
    // Only clear Gmail-specific claims that are now disproved by the search.
    if (isNotFound) ...{
      'gmailSourceEmails': <String>[],
      'gmailStatus': '',
      'gmailEstimatedDelivery': '',
      'emailStatus': '',
      'emailEstimatedDelivery': '',
      'gmailLinkedAt': null,
    },
  };
""",
'persist the exact queried tracking and remove stale Gmail provenance')

h = one(h,
"""bool gmailRecordIsLinked(Map<String, dynamic> record) {
  const evidenceKeys = <String>[""",
"""bool gmailRecordIsLinked(Map<String, dynamic> record) {
  // A package must not get a Gmail-check badge merely because some old
  // cached email/ETA/photos existed for a different or unverified tracking.
  final currentTracking = '${record['tracking'] ?? ''}'.trim().toUpperCase();
  if (currentTracking.isNotEmpty) {
    final verifiedTracking = '${record['gmailLookupTracking'] ?? ''}'.trim().toUpperCase();
    if ('${record['gmailLookupStatus'] ?? ''}'.trim().toLowerCase() != 'found' ||
        verifiedTracking != currentTracking) {
      return false;
    }
  }
  const evidenceKeys = <String>[""",
'Gmail linked badge requires evidence for same tracking')
helper.write_text(h)

pkg = Path('app/lib/packages.dart')
s = pkg.read_text()

s = one(s,
"""  bool loaded = false, syncing = false, gmailLoading = false;""",
"""  bool loaded = false, syncing = false, gmailLoading = false;
  String gmailVerifiedLookupStatus = '';
  String gmailVerifiedTracking = '';
  bool get _gmailVerifiedForCurrent =>
      gmailVerifiedLookupStatus == 'found' &&
      gmailVerifiedTracking.trim().toUpperCase() == tracking.text.trim().toUpperCase();
  bool get _gmailNotFoundForCurrent =>
      gmailVerifiedLookupStatus == 'not_found' &&
      (gmailVerifiedTracking.trim().isEmpty ||
       gmailVerifiedTracking.trim().toUpperCase() == tracking.text.trim().toUpperCase());""",
'editor verification flags')

s = one(s,
"""    gmailEta.text = '${widget.existing?['gmailEstimatedDelivery'] ?? widget.existing?['emailEstimatedDelivery'] ?? ''}';""",
"""    gmailEta.text = '${widget.existing?['gmailEstimatedDelivery'] ?? widget.existing?['emailEstimatedDelivery'] ?? ''}';
    gmailVerifiedLookupStatus = '${widget.existing?['gmailLookupStatus'] ?? ''}'.trim().toLowerCase();
    gmailVerifiedTracking = '${widget.existing?['gmailLookupTracking'] ?? ''}'.trim();""",
'load verification flags')

s = one(s,
"""    gmailSourceEmails = dynList(widget.existing?['gmailSourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();""",
"""    gmailSourceEmails = dynList(widget.existing?['gmailSourceEmails']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();
    if (_gmailNotFoundForCurrent) {
      gmailSourceEmails.clear();
      gmailStatus.clear();
      gmailEta.clear();
    }""",
'hide disproved previous Gmail results on editor opening')

s = one(s,
"""          state: 'not_found',
        );
""",
"""          state: 'not_found',
        );
        if (!mounted) return;
        setState(() {
          gmailVerifiedLookupStatus = 'not_found';
          gmailVerifiedTracking = track;
          gmailSourceEmails.clear();
          gmailStatus.clear();
          gmailEta.clear();
        });
""",
'update editor immediately after not-found')

s = one(s,
"""      if (!mounted) return;
      setState(() {
        gmailStore.text =""",
"""      if (!mounted || tracking.text.trim().toUpperCase() != track.toUpperCase()) return;
      setState(() {
        gmailVerifiedLookupStatus = 'found';
        gmailVerifiedTracking = track;
        gmailStore.text =""",
'only confirm same-tracking Gmail success')

s = one(s,
"""      'gmailLinkedAt': DateTime.now().toIso8601String(),
""",
"""      'gmailLinkedAt': DateTime.now().toIso8601String(),
      'gmailLookupStatus': 'found',
      'gmailLookupTracking': track,
""",
'recovered background success ties source to tracking')

s = one(s,
"""      'gmailEstimatedDelivery': gmailEta.text.trim(),
      'emailPhotoUrls': emailPhotoUrls,
""",
"""      'gmailEstimatedDelivery': _gmailNotFoundForCurrent ? '' : gmailEta.text.trim(),
      'gmailLookupStatus': gmailVerifiedLookupStatus,
      'gmailLookupTracking': gmailVerifiedTracking,
      'emailPhotoUrls': emailPhotoUrls,
""",
'persist editor lookup status')

s = one(s,
"""      'gmailSourceEmails': gmailSourceEmails,
""",
"""      'gmailSourceEmails': _gmailVerifiedForCurrent
          ? List<String>.from(gmailSourceEmails) : <String>[],
""",
'never save legacy/unverified source emails as confirmed')

s = one(s,
"""        TextField(controller: gmailStore, decoration: const InputDecoration(labelText: 'Tienda detectada / tienda')),
""",
"""        if (_gmailNotFoundForCurrent) ...[
          Card(
            child: ListTile(
              leading: Icon(Icons.search_off_outlined,
                  color: Theme.of(context).colorScheme.error),
              title: const Text('No encontrado en Gmail',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              subtitle: const Text(
                'La última búsqueda terminó sin correos que coincidan con este tracking. '
                'No se mostrarán fuentes ni estados de correo anteriores.',
              ),
            ),
          ),
          const SizedBox(height: 8),
        ] else if (!_gmailVerifiedForCurrent && gmailSourceEmails.isNotEmpty) ...[
          const Card(
            child: ListTile(
              leading: Icon(Icons.info_outline),
              title: Text('Datos de Gmail anteriores sin verificar'),
              subtitle: Text(
                'El origen guardado aún no está confirmado para este tracking. '
                'Pulsa Buscar tracking para comprobarlo.',
              ),
            ),
          ),
          const SizedBox(height: 8),
        ],
        TextField(controller: gmailStore, decoration: const InputDecoration(labelText: 'Tienda detectada / tienda')),
""",
'editor visible no-match status')

s = one(s,
"""        if (gmailSourceEmails.isNotEmpty) ...[
""",
"""        if (_gmailVerifiedForCurrent && gmailSourceEmails.isNotEmpty) ...[
""",
'hide previously saved source until verified exact tracking')

pkg.write_text(s)

# Background processing writes packages even if the editor is not on screen.
# The same truth-in-status requirement applies to those persisted results.
bg = Path('app/lib/background_sync.dart')
b = bg.read_text()
key = """          'gmailLinkedAt': DateTime.now().toIso8601String(),"""
count = b.count(key)
if count != 2:
    raise SystemExit(f'Gmail v35: expected two background success branches; got {count}')
b = b.replace(key,
"""          'gmailLinkedAt': DateTime.now().toIso8601String(),
          'gmailLookupStatus': 'found',
          'gmailLookupTracking': tracking,""")
bg.write_text(b)

print('Gmail v35: show exact-tracking verified matches only; persist genuine not-found, preserve manual edits.')
