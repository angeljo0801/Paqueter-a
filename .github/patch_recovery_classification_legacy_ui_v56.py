from pathlib import Path
import re

# v56: Deleting a Gmail photo means remove it from THIS package, not "teach
# the AI this is never a product." That mistake made users' genuine purchase
# images be permanently discarded on the next Gmail search.
#
# Restore the original compact Gmail editor UI: one photo grid, the original
# "Ver imágenes descartadas" affordance and full-screen swipe viewer. Keep
# independent rescue storage / fresh search without the noisy extra controls.
h=Path('app/lib/gmail_purchase_link.dart')
s=h.read_text()

# Safe to stop writing automatic negative examples. Preserve training when
# the user explicitly recovers a picture as a product.
pattern=r'\s*await GmailPhotoLearningService\.rememberImage\(\s*\n(?:[^\n]*\n){0,9}?\s*product: false,\s*\n\s*\);\s*\n'
matches=list(re.finditer(pattern,s))
assert len(matches)==1, f'v56: expected shared gallery delete-training call, got {len(matches)}'
s=re.sub(pattern,'\n',s)

# Existing negative memories from test-deleted product photos may already be
# stored in gmail_photo_learning_v1. Make these old negative labels advisory,
# not a reason to discard. Seeded high-confidence delivery/help examples
# still remain a rejection, as do catalog/banner/transport OCR guards.
a=s.index('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
b=s.index('\nWidget gmailSmartPhotoImage(',a)
fn=s[a:b]
rejectStart="      if (learnedDecision.reject && !sourceThumbnail &&"
assert fn.count(rejectStart)==1, 'v56: learned rejection structure moved'
fn=fn.replace(rejectStart,
"""      if (learnedDecision.reject &&
          learnedDecision.reason != 'descartada por aprendizaje local' &&
          !sourceThumbnail &&""",1)
# Clean product shots from an identified source can be any resolution, not
# just thumbnail sizes <= 220px. This helps the watch pictured in the SHEIN
# pre-delivery order section, without accepting status strips and banners.
boost="      if (sourceThumbnail && !onlyBrandWordmark) {"
assert fn.count(boost)==1, 'v56: thumbnail boost moved'
fn=fn.replace(boost,
"""      final verifiedSquareProductImage = matchedStoreSource &&
          !deliveryProofHint && !onlyBrandWordmark &&
          width >= 110 && height >= 110 &&
          ratio >= 0.74 && ratio <= 1.35 &&
          !catalogCard && !_gmailPromoText(ocr);
      if (sourceThumbnail || verifiedSquareProductImage) {""",1)
# Preserve the same scoring budget; no indiscriminate accepting of all Gmail
# images. Photo control icons < 70px and promo OCR still rejected first.
s=s[:a]+fn+s[b:]
h.write_text(s)

for path in [Path('app/lib/packages.dart'),Path('app/lib/purchases.dart'),Path('app/lib/clients.dart')]:
    s=path.read_text()
    matches=list(re.finditer(pattern,s))
    if path.name=='packages.dart':
        assert len(matches)>=1, 'v56: package delete no longer teaches negatives'
    # Normal removal is not explicit "not a product"; never train negative.
    s=re.sub(pattern,'\n',s)
    path.write_text(s)
    print(f'v56 {path.name}: removed {len(matches)} implicit negative training calls')

p=Path('app/lib/packages.dart')
s=p.read_text()

# Unclutter Gmail photo UI: these controls were added only in v52/v53. The
# original selected photo grid + "Ver imágenes descartadas" already supports
# the swipe-and-recover gallery from the older working releases.
extraTop=r'''        OutlinedButton.icon(
          onPressed: gmailLoading ? null : _openGmailCandidateReview,
          icon: const Icon(Icons.photo_library_outlined),
          label: Text(gmailCandidateInbox.isEmpty
              ? 'Ver y recuperar imágenes de Gmail'
              : 'Ver y recuperar imágenes de Gmail (' +
                  gmailCandidateInbox.length.toString() + ')'),
        ),
        const SizedBox(height: 8),
'''
assert s.count(extraTop)==1, 'v56: added top recovery button missing'
s=s.replace(extraTop,'',1)
extraBottom=r'''        OutlinedButton.icon(
          onPressed: _openGmailCandidateReview,
          icon: const Icon(Icons.photo_library_outlined),
          label: const Text('Ver / recuperar fotos de Gmail'),
        ),
        if (gmailPhotoAnalysisReport.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: SelectableText(
              gmailPhotoAnalysisReport,
              style: Theme.of(context).textTheme.bodySmall,
            ),
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
assert s.count(extraBottom)==1, 'v56: added footer recovery/status block moved'
s=s.replace(extraBottom,'',1)
upperDiagnostics=r'''        if (gmailPhotoAnalysisReport.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: SelectableText(gmailPhotoAnalysisReport),
          ),
'''
assert s.count(upperDiagnostics)==1, 'v56: upper diagnostics block moved'
s=s.replace(upperDiagnostics,'',1)

# The original version showed ONE review action directly above the grid,
# not multiple buttons below the items. Wire it to the independent persistent
# inbox so it survives even when OCR labels 0 photos as products.
original="""                  if (gmailRejectedImages.isNotEmpty)
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed: _showRejectedGmailPhotos,
                        icon: const Icon(Icons.filter_alt_off_outlined),
                        label: Text('Ver imágenes descartadas (\${gmailRejectedImages.length})'),
                      ),
                    ),"""
assert s.count(original.replace("\\$","$"))==1, 'v56: original older review link missing'
new="""                  if (gmailRejectedImages.isNotEmpty ||
                      gmailCandidateInbox.isNotEmpty)
                    Align(
                      alignment: Alignment.centerLeft,
                      child: TextButton.icon(
                        onPressed: _openGmailCandidateReview,
                        icon: const Icon(Icons.filter_alt_off_outlined),
                        label: Text('Ver imágenes descartadas (\${gmailRejectedImages.length})'),
                      ),
                    ),"""
s=s.replace(original.replace("\\$","$"),new.replace("\\$","$"),1)
# No accepted image may be repeated in the review list. Keep the independent
# raw inbox only behind the original "descartadas" affordance.
p.write_text(s)

assert "'gmailCandidateInbox':" in s and "_openGmailCandidateReview" in s
assert "label: const Text('Ver / recuperar fotos de Gmail')" not in s
assert "onPressed: gmailLoading ? null : _openGmailCandidateReview" not in s
print('v56: original Gmail UI restored; test-deleted product no longer trained as negative.')
