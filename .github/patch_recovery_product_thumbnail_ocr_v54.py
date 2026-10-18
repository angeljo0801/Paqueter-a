from pathlib import Path

# v54: real retailer product thumbnails do not need text to be products.
# OCR is a text detector, not a visual product classifier. Keep the true
# product-source information and use it only for small square thumbnails;
# delivery proof, tracking strips, logos and promo text remain reviewable.
p=Path('app/lib/gmail_purchase_link.dart')
s=p.read_text()
key="Future<Map<String, dynamic>> gmailPrepareProductPhotos({"
assert s.count(key)==1
start=s.index(key)
end=s.index('\nWidget gmailSmartPhotoImage(',start)
fn=s[start:end]

a='  required List<Map<String, dynamic>> items,'
assert fn.count(a)==1
fn=fn.replace(a,a+"\n  String photoSourceRule = '',",1)
a="  var ocrAttempts = 0;"
assert fn.count(a)==1
fn=fn.replace(a,a+"\n  var ocrTextFound = 0;\n  var recoveredSmallProductPhotos = 0;",1)

# Genuine source means a message that WhatsBot matched to this tracking/order,
# not an arbitrary delivered notification or a courier proof.
key="    final deliveryProofHint = image['deliveryProofHint'] == true ||"
assert fn.count(key)==1
source=r'''    final matchedStoreSource =
        photoSourceRule.startsWith('shein_predelivery_first') ||
        photoSourceRule.startsWith('temu_latest_first');
'''
fn=fn.replace(key,source+key,1)

# Calculate thumbnail provenance only AFTER geometry is available.
a="      if (width > 0 && height > 0 && (width < 90 || height < 90)) {"
assert fn.count(a)==1
new=r'''      final sourceThumbnail = matchedStoreSource && !deliveryProofHint &&
          width >= 70 && height >= 70 &&
          width <= 220 && height <= 220 &&
          width / height >= 0.72 && width / height <= 1.38;
      if (width > 0 && height > 0 && (width < 90 || height < 90) &&
          !sourceThumbnail) {'''
fn=fn.replace(a,new,1)
a="        ocr = await _gmailOcrFile(temp.path);"
assert fn.count(a)==1
fn=fn.replace(a,a+"\n        if (ocr.trim().isNotEmpty) ocrTextFound++;",1)

# Learning must not suppress a real item thumbnail because the image is
# visually similar to an earlier rejected header in another email.
a="      if (learnedDecision.reject &&"
assert fn.count(a)==1
fn=fn.replace(a,"      if (learnedDecision.reject && !sourceThumbnail &&",1)

# Keep existing severe banner/catalog/proof rejections. Add a small thumbnail
# boost only after these guards and only for the verified store source.
a="      if (score < 2) {"
assert fn.count(a)==1
boost=r'''      // Source provenance plus square product-thumbnail geometry is useful
      // evidence when ML Kit finds no readable words (e.g. SHEIN watch photo).
      // A lone SHEIN/TEMU wordmark is a brand graphic, not a purchase.
      final onlyBrandWordmark = RegExp(
        r'^\s*(?:shein|temu)\s*$',
        caseSensitive: false,
      ).hasMatch(ocr.trim());
      if (sourceThumbnail && !onlyBrandWordmark) {
        score += 3;
        recoveredSmallProductPhotos++;
      }

'''
fn=fn.replace(a,boost+a,1)
a="      'ocrAttempts': ocrAttempts,"
assert fn.count(a)==1
fn=fn.replace(a,a+"""
      'ocrTextFound': ocrTextFound,
      'smallStoreThumbnails': recoveredSmallProductPhotos,
      'unavailable': rejected.where((e) =>
          (e['rejectReason'] ?? '') == 'imagen no disponible').length,
      'tooSmall': rejected.where((e) =>
          (e['rejectReason'] ?? '') == 'icono pequeño').length,
      'insufficientEvidence': rejected.where((e) =>
          (e['rejectReason'] ?? '') == 'sin señales suficientes de producto').length,
      'analysisFailed': rejected.where((e) =>
          (e['rejectReason'] ?? '') == 'no se pudo analizar').length,""",1)
s=s[:start]+fn+s[end:]

# The old OCR utility masked all ML Kit exceptions and made a failed reader
# indistinguishable in logs from a genuinely text-free photo.
old="  } catch (_) {\n    return '';\n  } finally {\n    recognizer.close();\n  }\n}"
assert s.count(old)>=1
s=s.replace(old,"  } catch (error) {\n    debugPrint('Gmail OCR unavailable: $error');\n    return '';\n  } finally {\n    recognizer.close();\n  }\n}",1)
p.write_text(s)

p=Path('app/lib/packages.dart')
s=p.read_text()
anchor="  String gmailPhotoInboxStatus = '';"
assert s.count(anchor)==1, 'v54: v53 status field changed'
s=s.replace(anchor,anchor+"\n  String gmailVerifiedPhotoSourceRule = '';",1)

# v53 stores the raw server response BEFORE the filter starts. Preserve the
# verified photo source rule at this exact point for the OCR classifier.
a="  Future<void> _captureRawGmailPhotoResult(Map<String, dynamic> data) async {"
assert s.count(a)==1
s=s.replace(a,a+"""
    gmailVerifiedPhotoSourceRule =
        (data['photoSourceRule'] ?? '').toString().trim();""",1)

start=s.index("  Future<void> _smartFilterAndCacheGmailPhotos() async {")
end=s.index("  Future<void> _showRejectedGmailPhotos() async {",start)
fn=s[start:end]
anchor="      items: gmailItems,"
assert fn.count(anchor)==1
fn=fn.replace(anchor,anchor+"\n      photoSourceRule: gmailVerifiedPhotoSourceRule,",1)
a="    final rawStats = result['analysisDiagnostics'];"
assert fn.count(a)==1
# Reports show how many images genuinely returned readable OCR versus calls
# to ML Kit and how many tiny product photos provenance rescued.
fn=fn.replace(a,a,1)
old="        '\${n('evaluated')} evaluadas · \${n('ocrAttempts')} OCR · '\n"
# Actual Dart string is dollar interpolation not escaped; patch applied in the
# generated final file, not the Python patch text.
old=old.replace("\\$","$")
new="        '\${n('evaluated')} evaluadas · \${n('ocrAttempts')} OCR '\n        '(\${n('ocrTextFound')} con texto) · '\n        '\${n('smallStoreThumbnails')} miniaturas recuperadas · '\n"
new=new.replace("\\$","$")
assert fn.count(old)==1, 'v54: diagnostic report changed'
fn=fn.replace(old,new,1)
s=s[:start]+fn+s[end:]
# Make diagnostics visible in the always-visible section beside Save, not
# only next to the upper Gmail store field.
anchor="        if (gmailPhotoInboxStatus.isNotEmpty)"
assert s.count(anchor)==1
s=s.replace(anchor,"""        if (gmailPhotoAnalysisReport.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: SelectableText(
              gmailPhotoAnalysisReport,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
"""+anchor,1)
p.write_text(s)

assert "String photoSourceRule = ''" in Path('app/lib/gmail_purchase_link.dart').read_text()
assert "photoSourceRule: gmailVerifiedPhotoSourceRule" in s
assert "gmailPhotoAnalysisReport" in s
print('v54: source-verified compact thumbnails survive empty OCR; detailed photo diagnostics visible by Save.')
