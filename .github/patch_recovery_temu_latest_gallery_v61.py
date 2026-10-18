from pathlib import Path

# v61 -- For Temu the latest VERIFIED Gmail message alone is authoritative.
# A successful fresh lookup must not re-add photos from an older Gmail run.
# The earlier "don't erase photos when OCR fails" rule may continue to apply
# for all other merchants and for failed/offline searches.
p=Path('app/lib/packages.dart')
s=p.read_text()
field="  String gmailVerifiedPhotoSourceRule = '';"
assert s.count(field)==1, 'v61 Temu selector state anchor'
s=s.replace(field,field+"\n  bool gmailLatestTemuFreshResult = false;",1)

a=s.index('  Future<void> _captureRawGmailPhotoResult(Map<String, dynamic> data) async {')
b=s.index('  Future<void> _stageGmailCandidateInbox() async {',a)
part=s[a:b]
needle="    final hasServerImages ="
assert part.count(needle)==1,'v61 fresh Gmail raw source changed'
part=part.replace(needle,r'''    // Mark ONLY a successful, explicitly initiated Temu lookup as the source
    // of truth for this package. Do not touch existing data after a network
    // error, no Gmail match, or resuming another background job.
    final sourceRule = (data['photoSourceRule'] ?? '').toString().trim();
    gmailLatestTemuFreshResult =
        !_recoveringFinishedGmailSearch &&
        data['found'] == true &&
        data['photoSearchScope'] == 'single_priority_email' &&
        sourceRule.startsWith('temu_');
'''+needle,1)
old="""    if (!_recoveringFinishedGmailSearch &&
        data['found'] == true && hasServerImages) {"""
assert part.count(old)==1,'v61 raw reset anchor'
part=part.replace(old,"""    if (!_recoveringFinishedGmailSearch &&
        data['found'] == true &&
        (hasServerImages || gmailLatestTemuFreshResult)) {""",1)
old="""    if (candidates.isEmpty) {
      gmailPhotoInboxStatus ="""
assert part.count(old)==1, 'v61 empty Gmail candidates'
part=part.replace(old, """    if (candidates.isEmpty) {
      if (gmailLatestTemuFreshResult) {
        // An empty latest Temu email does NOT mean old order photos.
        await _saveGmailCandidateInboxIndependently();
      }
      gmailPhotoInboxStatus =""",1)
s=s[:a]+part+s[b:]

a=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedGmailPhotos() async {',a)
part=s[a:b]
# v46 previously-saved fallback can turn old photos back into accepted items.
old="""    if (accepted.isEmpty) {
      final previousUrls = <String>{"""
assert part.count(old)==1, 'v61 old-photo fallback'
part=part.replace(old,"""    if (accepted.isEmpty && !gmailLatestTemuFreshResult) {
      final previousUrls = <String>{""",1)
# v58's empty-result workaround can silently re-accept raw cards, but only
# raw candidates from the newly captured email should be eligible.
s=s[:a]+part+s[b:]

a=s.index('  Future<void> _persistRecoveredGmailSnapshot() async {')
b=s.index('  Future<void> removeMultipleEmailPhotos() async {',a)
part=s[a:b]
old="    if (keptUrls.isEmpty && keptAttachments.isEmpty) {"
assert part.count(old)==1,'v61 stored fallback'
part=part.replace(old,"    if (keptUrls.isEmpty && keptAttachments.isEmpty &&\n        !gmailLatestTemuFreshResult) {",1)
# Store only the current selection even when no image is available.
# Existing offline files are left on disk and can be manually recovered.
s=s[:a]+part+s[b:]
p.write_text(s)

assert 'gmailLatestTemuFreshResult' in s
assert 'hasServerImages || gmailLatestTemuFreshResult' in s
assert 'accepted.isEmpty && !gmailLatestTemuFreshResult' in s
assert 'keptAttachments.isEmpty &&\n        !gmailLatestTemuFreshResult' in s
print('v61: fresh Temu selects latest Gmail message, never resurrects older photo gallery.')
