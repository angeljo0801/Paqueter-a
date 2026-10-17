from pathlib import Path

# v52: The review action was nested under "if (emailImages.isNotEmpty)".
# When the classifier accepted 0, the whole card (including "discarded")
# disappeared, although 9 raw candidates were available in the screenshot.
# Render recovery independently of acceptance and restore inbox on demand.
p=Path('app/lib/packages.dart')
s=p.read_text()

panel="        if (emailImages.isNotEmpty) ...["
assert s.count(panel)==1, 'Gmail review panel locator changed'
s=s.replace(panel,
    "        if (emailImages.isNotEmpty || gmailRejectedImages.isNotEmpty ||\n"
    "            gmailCandidateInbox.isNotEmpty) ...[",1)

anchor="                  const SizedBox(height: 10),\n                  GridView.builder("
assert s.count(anchor)>=1, 'Missing package photo grid'
# Only show the product grid for accepted photos; an empty grid must not
# prevent the separate review UI from rendering.
photo_at=s.index("        if (emailImages.isNotEmpty || gmailRejectedImages.isNotEmpty ||")
end_at=s.index("        if (widget.existing != null && (remote.isNotEmpty",photo_at)
section=s[photo_at:end_at]
assert section.count(anchor)==1, 'Gmail section changed'
section=section.replace(anchor,
    "                  if (emailImages.isEmpty)\n"
    "                    const Padding(\n"
    "                      padding: EdgeInsets.symmetric(vertical: 8),\n"
    "                      child: Text('No hay fotos aprobadas automáticamente. '\n"
    "                          'Revisa las imágenes encontradas para recuperar productos válidos.'),\n"
    "                    ),\n"
    "                  const SizedBox(height: 10),\n"
    "                  if (emailImages.isNotEmpty) GridView.builder(",1)

old_btn="                  if (gmailRejectedImages.isNotEmpty)"
new_btn="                  if (gmailRejectedImages.isNotEmpty || gmailCandidateInbox.isNotEmpty)"
assert section.count(old_btn)==1,'Gmail rejected button hidden in a different place'
section=section.replace(old_btn,new_btn,1)
old_label="'Ver imágenes descartadas (\${gmailRejectedImages.length})'"
new_label="'Ver imágenes para revisar (\${gmailRejectedImages.isNotEmpty ? gmailRejectedImages.length : gmailCandidateInbox.length})'"
assert section.count(old_label)==1, 'Gmail button label changed'
section=section.replace(old_label,new_label,1)
s=s[:photo_at]+section+s[end_at:]

# On a saved package, the inbox is an independent durable collection. Its
# review action must not require prior automatic classification.
start=s.index('  Future<void> _showRejectedGmailPhotos() async {')
after=s.index('    final recovered = <String>{};',start)
block=s[start:after]
old_guard="    if (gmailRejectedImages.isEmpty) return;"
assert block.count(old_guard)==1
block=block.replace(old_guard,"""    if (gmailRejectedImages.isEmpty && gmailCandidateInbox.isNotEmpty) {
      setState(() => _restoreGmailCandidateInboxReview());
    }
    if (gmailRejectedImages.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Todavía no hay fotos recuperables para revisar.')),
      );
      return;
    }""",1)
s=s[:start]+block+s[after:]

# Save and re-open must have the review panel's state. Fail build if a
# regression removes persisted candidates or the recovery callback.
assert "'gmailCandidateInbox': gmailCandidateInbox," in s
assert "gmailCandidateInbox = dynList(saved['gmailCandidateInbox'])" in s
assert "_showRejectedGmailPhotos" in s
assert "await _persistRecoveredGmailSnapshot();" in s
assert "gmailRejectedImages.isNotEmpty || gmailCandidateInbox.isNotEmpty" in s
assert "if (emailImages.isNotEmpty) GridView.builder(" in s

p.write_text(s)
print("Gmail v52: 0 accepted photos cannot hide review; raw inbox stays accessible and recoverable.")
