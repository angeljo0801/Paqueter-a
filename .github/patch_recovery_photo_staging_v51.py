from pathlib import Path

# v51: Keep a separate durable inbox of Gmail candidates BEFORE the smart
# classifier replaces its transient preview lists. Inbox items are NOT
# automatically accepted product photos; they remain reviewable if OCR fails.
p=Path('app/lib/packages.dart')
s=p.read_text()
field="  String gmailPhotoAnalysisReport = '';"
assert s.count(field)==1
s=s.replace(field,field+"\n  List<Map<String, dynamic>> gmailCandidateInbox = [];",1)

start=s.index('  Future<void> reconstructFromGmail() async {')
end=s.index('  Future<void> openEmailPhoto(',start)
flow=s[start:end]
marker="      await _smartFilterAndCacheGmailPhotos();"
assert flow.count(marker)==1, 'v51: photo-filter call not unique'
flow=flow.replace(marker,"""      // Candidate previews were visible already. Persist their identities
      // separately before an automated reject can empty the product gallery.
      await _stageGmailCandidateInbox();
"""+marker,1)
s=s[:start]+flow+s[end:]

anchor="  Future<void> _smartFilterAndCacheGmailPhotos() async {"
assert s.count(anchor)==1
methods=r'''  Future<void> _stageGmailCandidateInbox() async {
    final candidates = _emailPhotoEntries()
        .where((e) {
          final u = (e['url'] ?? '').toString().trim();
          return u.isNotEmpty && !hiddenEmailPhotoUrls.contains(u);
        })
        .take(80)
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    if (candidates.isEmpty) return;

    final seen = <String>{};
    final inbox = <Map<String, dynamic>>[];
    for (final image in [...gmailCandidateInbox, ...candidates]) {
      final url = (image['url'] ?? '').toString().trim();
      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url) || !seen.add(url)) continue;
      inbox.add(image);
    }
    gmailCandidateInbox = inbox;
    final id = (widget.existing?['id'] ?? '').toString().trim();
    final track = tracking.text.trim().toLowerCase();
    final rows = await Store.list('packages', forceRefresh: true);
    var index = rows.indexWhere((e) => id.isNotEmpty &&
        (e['id'] ?? '').toString() == id);
    if (index < 0 && id.isEmpty && track.isNotEmpty) {
      index = rows.indexWhere((e) =>
          (e['tracking'] ?? '').toString().trim().toLowerCase() == track);
    }
    if (index < 0) {
      // New packages are persisted by the ordinary Save button.
      return;
    }
    rows[index] = {
      ...rows[index],
      'gmailCandidateInbox': inbox,
    };
    await Store.saveList('packages', rows);
    // No acknowledgement here. The complete filtered state has not arrived.
  }

  void _restoreGmailCandidateInboxReview() {
    final accepted = <String>{
      ...emailPhotoUrls.map((e) => e.trim()),
      ...emailAttachmentImages
          .map((e) => (e['url'] ?? '').toString().trim()),
    };
    final seen = <String>{
      ...gmailRejectedImages
          .map((e) => (e['url'] ?? '').toString().trim()),
    };
    for (final raw in gmailCandidateInbox) {
      final url = (raw['url'] ?? '').toString().trim();
      if (url.isEmpty || accepted.contains(url) ||
          hiddenEmailPhotoUrls.contains(url) ||
          gmailManuallyAcceptedPhotoUrls.contains(url) || !seen.add(url)) {
        continue;
      }
      gmailRejectedImages.add({
        ...raw,
        'rejectReason': (raw['rejectReason'] ?? '').toString().isEmpty
            ? 'Candidata del correo para revisión'
            : raw['rejectReason'],
      });
    }
  }

'''
s=s.replace(anchor,methods+anchor,1)

# On re-entry, reload the actual current disk version, not the stale
# dashboard widget.existing snapshot. Reconstruct only photo fields.
entry="    if (mounted) {\n      setState(() => loaded = true);"
assert s.count(entry)==1, 'v51: editor load completion anchor changed'
restore=r'''    try {
      final id = (widget.existing?['id'] ?? '').toString().trim();
      final track = tracking.text.trim().toLowerCase();
      final savedRows = await Store.list('packages', forceRefresh: true);
      final matches = savedRows.where((e) =>
          (id.isNotEmpty && (e['id'] ?? '').toString() == id) ||
          (id.isEmpty && track.isNotEmpty &&
           (e['tracking'] ?? '').toString().trim().toLowerCase() == track));
      if (matches.isNotEmpty) {
        final saved = matches.first;
        emailPhotoUrls = dynList(saved['emailPhotoUrls'])
            .map((e) => e.toString().trim())
            .where((e) => e.isNotEmpty).toList();
        emailAttachmentImages = dynList(saved['emailAttachmentImages'])
            .whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
        final offline = saved['gmailOfflinePhotoPaths'];
        if (offline is Map) {
          gmailOfflinePhotoPaths = offline.map(
            (k, v) => MapEntry(k.toString(), v.toString()));
        }
        gmailRejectedImages = dynList(saved['gmailRejectedImages'])
            .whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
        gmailCandidateInbox = dynList(saved['gmailCandidateInbox'])
            .whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
        hiddenEmailPhotoUrls
          ..clear()
          ..addAll(dynList(saved['hiddenEmailPhotoUrls'])
              .map((e) => e.toString().trim()).where((e) => e.isNotEmpty));
        gmailManuallyAcceptedPhotoUrls
          ..clear()
          ..addAll(dynList(saved['manuallyAcceptedGmailPhotoUrls'])
              .map((e) => e.toString().trim()).where((e) => e.isNotEmpty));
        _restoreGmailCandidateInboxReview();
      }
    } catch (error) {
      debugPrint('Gmail photo rehydrate warning: $error');
    }
'''
s=s.replace(entry,restore+entry,1)

# Add the inbox and manual recovery list to verified snapshots, otherwise
# the recovery overrides were forgotten by the automatic save.
field="'gmailPhotoAnalysisReport': gmailPhotoAnalysisReport,"
assert s.count(field)>=2, 'v51: both ordinary and automatic save fields expected'
s=s.replace(field,field+"\n      'gmailCandidateInbox': gmailCandidateInbox,\n      'manuallyAcceptedGmailPhotoUrls': gmailManuallyAcceptedPhotoUrls.toList(),")

# Important: the manual Restore button historically changed only in-memory
# state; save immediately and verify so the next editor open honors it.
start=s.index('  Future<void> _showRejectedGmailPhotos() async {')
end=s.find('\n  Future<void> ',start+10)
assert end>start
method=s[start:end]
marker="    });\n  }"
assert method.endswith(marker+"\n"), 'v51: manual recover method changed'
method=method[:-len(marker+"\n")]+"""    });
    try {
      await _persistRecoveredGmailSnapshot();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Fotos recuperadas y guardadas.')),
        );
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Fotos recuperadas, pero no guardadas: $error')),
        );
      }
    }
  }
"""
s=s[:start]+method+s[end:]

# Update the main filtered result's review shelf immediately as well.
start=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
end=s.index('  Future<void> _showRejectedGmailPhotos() async {',start)
method=s[start:end]
a="      gmailRejectedImages = rejected;"
assert method.count(a)==1
method=method.replace(a,a+"\n      _restoreGmailCandidateInboxReview();",1)
s=s[:start]+method+s[end:]

p.write_text(s)
print('v51 Gmail staging: candidate inbox survives rejected previews; manual restores save instantly; reopens load fresh disk.')
