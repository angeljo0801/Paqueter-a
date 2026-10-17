from pathlib import Path

helper=Path('app/lib/gmail_purchase_link.dart')
s=helper.read_text()
anchor='Future<Map<String, dynamic>> gmailPrepareProductPhotos({'
assert s.count(anchor)==1

classification = r'''
// Delivery proof is a logistics photograph, not a product image.
// Do not reject a product simply because its order is marked DELIVERED.
// The OCR-only path requires explicit photo-proof language. Address numbers,
// door mats and parcel labels count only with source-email proof metadata.
String? gmailDeliveryProofRejectReason({
  required String ocrText,
  required bool deliveryProofHint,
  required int width,
  required int height,
  required bool orderItemSignals,
  required bool matchedProduct,
}) {
  final normalized = ocrText.toLowerCase().replaceAll(RegExp(r'\s+'), ' ').trim();
  final explicitProof = RegExp(
    r'\b(?:proof of delivery|delivery photos?|delivery pictures?|'
    r'delivered to (?:your|the) door|photo of (?:your|the) delivery|'
    r'drop[- ]off photo|foto de entrega|prueba de entrega)\b',
    caseSensitive: false,
  ).hasMatch(normalized);
  // A receipt or a real item row must not disappear due to the shipment state.
  if ((orderItemSignals || matchedProduct) && !explicitProof) return null;
  if (explicitProof) return 'prueba fotográfica de entrega (OCR)';
  if (!deliveryProofHint) return null;

  final portrait = width > 0 && height > 0 && height >= width * 1.14;
  final addressNumber = RegExp(
    r'(?:^|\s)(?:\d{3,5}|\d(?:\s+\d){2,4})(?:\s|$)',
  ).hasMatch(normalized);
  final doorstep = RegExp(
    r'\b(?:front door|front porch|doorstep|welcome|doormat|'
    r'left at|delivered at|package drop|delivered)\b',
    caseSensitive: false,
  ).hasMatch(normalized);
  // A photo from a courier's completed delivery with portrait camera framing
  // normally documents a doorstep/house. Keep ambiguous landscape shots
  // reviewable rather than rejecting every image in the delivery email.
  if (portrait || addressNumber || doorstep) {
    return 'foto del lugar de entrega (no artículo)';
  }
  return null;
}

'''
s=s.replace(anchor,classification+anchor,1)
a=s.index(anchor);b=s.index('\nWidget gmailSmartPhotoImage(',a);fn=s[a:b]
def one(old,new,label):
    global fn
    assert fn.count(old)==1,'Gmail POD v48: '+label
    fn=fn.replace(old,new,1)
one('  required List<Map<String, dynamic>> items,',
    '  required List<Map<String, dynamic>> items,\n  Set<String> deliveryProofUrls = const <String>{},',
    'optional proof URL parameter')
one("    if (rawUrl.isEmpty) continue;",
    """    if (rawUrl.isEmpty) continue;
    final originalUrl = (image['originalUrl'] ?? '').toString().trim();
    final proofFromUrl = RegExp(
      r'(?:proof[-_]?of[-_]?delivery|delivery[-_]?photo|delivery[-_]?proof|'
      r'pod[-_]?photo|dropoff[-_]?photo)',
      caseSensitive: false,
    ).hasMatch('$rawUrl $originalUrl');
    final deliveryProofHint = image['deliveryProofHint'] == true ||
        deliveryProofUrls.contains(rawUrl) ||
        (originalUrl.isNotEmpty && deliveryProofUrls.contains(originalUrl)) ||
        proofFromUrl;""",
    'proof from source metadata')
# Photo filter v2 already performs OCR on every available candidate.
# Keep that behavior; the delivery-proof decision below consumes its result.
one('      final learnedDecision =', '      final learnedDecision =', 'dummy') if False else None
# Learning state uses v47 safe wrapping. Run proof filter BEFORE learned rules.
anchor="      GmailPhotoLearningDecision learnedDecision;"
assert fn.count(anchor)==1
intro="""      final deliveryReason = gmailDeliveryProofRejectReason(
        ocrText: ocr,
        deliveryProofHint: deliveryProofHint,
        width: width,
        height: height,
        orderItemSignals: orderItemSignals,
        matchedProduct: matchedItem.isNotEmpty,
      );
      if (deliveryReason != null) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': deliveryReason,
          'photoClass': 'delivery_proof',
        });
        continue;
      }
"""
fn=fn.replace(anchor,intro+anchor,1)
s=s[:a]+fn+s[b:]
helper.write_text(s)

# Package screen: keep proof provenance across resumes and saves. It affects
# automatic filtering only, not manually added photos.
p=Path('app/lib/packages.dart')
s=p.read_text()
key="  String gmailPhotoAnalysisReport = '';"
assert s.count(key)==1
s=s.replace(key,key+"\n  final Set<String> gmailDeliveryPhotoHints = <String>{};",1)
load="    gmailPhotoAnalysisReport = (widget.existing?['gmailPhotoAnalysisReport'] ?? '').toString();"
assert s.count(load)==1
s=s.replace(load,load+"""
    gmailDeliveryPhotoHints.addAll(
      dynList(widget.existing?['gmailDeliveryPhotoHints'])
          .map((e) => e.toString().trim()).where((e) => e.isNotEmpty),
    );""",1)

a=s.index('  Future<void> reconstructFromGmail() async {')
b=s.index('  Future<void> openEmailPhoto(',a)
method=s[a:b]
source="        for (final value in dynList(data['emailPhotoCandidates'])) {"
assert method.count(source)==1
method=method.replace(source,"""        gmailDeliveryPhotoHints.addAll(
          dynList(data['deliveryPhotoUrls'])
              .map((e) => e.toString().trim()).where((e) => e.isNotEmpty),
        );
"""+source,1)
mark="          final url = (row['url'] ?? '').toString().trim();"
assert method.count(mark)==1
method=method.replace(mark,mark+"""
          if (row['deliveryProofHint'] == true) {
            gmailDeliveryPhotoHints.add(url);
            final original = (row['originalUrl'] ?? '').toString().trim();
            if (original.isNotEmpty) gmailDeliveryPhotoHints.add(original);
          }""",1)
s=s[:a]+method+s[b:]
a=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedGmailPhotos() async {',a)
method=s[a:b]
call='      items: gmailItems,\n'
assert method.count(call)==1
method=method.replace(call,call+'      deliveryProofUrls: gmailDeliveryPhotoHints,\n',1)
s=s[:a]+method+s[b:]
key="'gmailPhotoAnalysisReport': gmailPhotoAnalysisReport,"
assert s.count(key)>=1
s=s.replace(key,key+"\n      'gmailDeliveryPhotoHints': gmailDeliveryPhotoHints.toList(),")
p.write_text(s)

p=Path('app/lib/purchases.dart')
s=p.read_text()
key="  List<Map<String, dynamic>> gmailPurchaseRejectedImages = [];"
assert s.count(key)==1
s=s.replace(key,key+"\n  final Set<String> gmailPurchaseDeliveryPhotoHints = <String>{};",1)
load="      gmailPurchaseRejectedImages = dynList(widget.existing!['gmailRejectedImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();"
assert s.count(load)==1
s=s.replace(load,load+"""
      gmailPurchaseDeliveryPhotoHints.addAll(
        dynList(widget.existing!['gmailDeliveryPhotoHints'])
            .map((e) => e.toString().trim()).where((e) => e.isNotEmpty),
      );""",1)

a=s.index('  Future<void> linkPurchaseWithGmail() async {')
b=s.find('\n  Future<void> ',a+10)
if b < 0: b=len(s)
method=s[a:b]
source="          for (final raw in dynList(data['emailPhotoCandidates'])) {"
assert method.count(source)==1
method=method.replace(source,"""          gmailPurchaseDeliveryPhotoHints.addAll(
            dynList(data['deliveryPhotoUrls'])
                .map((e) => e.toString().trim()).where((e) => e.isNotEmpty),
          );
"""+source,1)
mark="            final url = (image['url'] ?? '').toString().trim();"
assert method.count(mark)==1
method=method.replace(mark,mark+"""
            if (image['deliveryProofHint'] == true) {
              gmailPurchaseDeliveryPhotoHints.add(url);
              final original = (image['originalUrl'] ?? '').toString().trim();
              if (original.isNotEmpty) gmailPurchaseDeliveryPhotoHints.add(original);
            }""",1)
s=s[:a]+method+s[b:]
a=s.index('  Future<void> _smartFilterAndCachePurchaseGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedPurchaseGmailPhotos() async {',a)
method=s[a:b]
key='      items: items,\n'
assert method.count(key)==1
method=method.replace(key,key+'      deliveryProofUrls: gmailPurchaseDeliveryPhotoHints,\n',1)
s=s[:a]+method+s[b:]
key="'gmailRejectedImages': gmailPurchaseRejectedImages,"
assert s.count(key)>=1
s=s.replace(key,key+"\n      'gmailDeliveryPhotoHints': gmailPurchaseDeliveryPhotoHints.toList(),")
p.write_text(s)
print('Gmail v48: courier proof-of-delivery OCR + provenance, photo gallery review, unchanged genuine products.')
