from pathlib import Path

p=Path('app/lib/gmail_purchase_link.dart')
s=p.read_text()
a=s.index('class GmailPhotoLearningService {')
b=s.index('\nbool gmailOrderItemPhotoSignals(',a)
part=s[a:b]
needle="""    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);"""
replacement="""    // Never load the full preference database just to read learning examples.
    // Failure to read learning data must not make photo evaluation fail.
    String? raw;
    try {
      raw = await Store._readRaw(_key);
    } catch (e) {
      debugPrint('Gmail learning unavailable: ${e.runtimeType}');
      return <Map<String, dynamic>>[];
    }"""
assert part.count(needle)==1
part=part.replace(needle,replacement,1)
needle="    final prefs = await SharedPreferences.getInstance();\n    final compact ="
assert part.count(needle)==1
part=part.replace(needle,"    final compact =",1)
needle="    await prefs.setString(_key, jsonEncode(compact));"
assert part.count(needle)==1
part=part.replace(needle,"    await Store._writeRaw(_key, jsonEncode(compact));",1)
s=s[:a]+part+s[b:]

# ML Kit reads a file URI, so the temporary OCR file needs a real image
# extension, not a trailing ".tmp" (which can leave recognition empty).
tmp_old="final temp = File('${dir.path}/.$digest.$ext.tmp');"
tmp_new="final temp = File('${dir.path}/.gmail_analysis_$digest.$ext');"
assert s.count(tmp_old)==1, 'OCR temporary path changed'
s=s.replace(tmp_old,tmp_new,1)

a=s.index('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
b=s.index('\nWidget gmailSmartPhotoImage(',a)
part=s[a:b]
def replace(old,new,name):
    global part
    if part.count(old)!=1: raise RuntimeError('Missing Gmail v47 anchor: '+name)
    part=part.replace(old,new,1)
replace("  final seenDigests = <String>{};","""  final seenDigests = <String>{};
  var downloaded = 0;
  var decodedImages = 0;
  var evaluated = 0;
  var ocrAttempts = 0;""","counts")
replace("      final bytes = response.bodyBytes;","      final bytes = response.bodyBytes;\n      downloaded++;","download")
replace("        height = frame.image.height;","        height = frame.image.height;\n        if (width > 0 && height > 0) decodedImages++;","decoded")
replace("        ocr = await _gmailOcrFile(temp.path);","        ocrAttempts++;\n        ocr = await _gmailOcrFile(temp.path);","ocr")
old="""      final learnedDecision = await GmailPhotoLearningService.decide(
        bytes: bytes,
        ocrText: ocr,
        url: rawUrl,
        width: width,
        height: height,
      );"""
new="""      GmailPhotoLearningDecision learnedDecision;
      try {
        learnedDecision = await GmailPhotoLearningService.decide(
          bytes: bytes,
          ocrText: ocr,
          url: rawUrl,
          width: width,
          height: height,
        );
      } catch (e) {
        debugPrint('Photo learning skipped: ${e.runtimeType}');
        learnedDecision = const GmailPhotoLearningDecision(
          reject: false, positive: false, negativeScore: 0,
          positiveScore: 0, reason: '',
        );
      }
      evaluated++;"""
replace(old,new,"learning fails open")
replace("    'offlinePaths': offlinePaths,","""    'offlinePaths': offlinePaths,
    'analysisDiagnostics': <String, int>{
      'candidates': images.take(80).length,
      'downloaded': downloaded,
      'decoded': decodedImages,
      'evaluated': evaluated,
      'ocrAttempts': ocrAttempts,
      'accepted': accepted.length,
      'rejected': rejected.length,
    },""","analysis diagnostic")
s=s[:a]+part+s[b:]
p.write_text(s)

p=Path('app/lib/packages.dart')
s=p.read_text()
a=s.index('  Future<void> reconstructFromGmail() async {')
b=s.index('  Future<void> openEmailPhoto(',a)
part=s[a:b]
ocr="      await _mergeItemsFromEmailImageOcr();"
photo="      await _smartFilterAndCacheGmailPhotos();"
assert part.count(ocr)==1 and part.count(photo)==1 and part.index(ocr)<part.index(photo)
i,j=part.index(ocr),part.index(photo)
part=part[:i]+photo+part[i+len(ocr):j]+ocr+part[j+len(photo):]
s=s[:a]+part+s[b:]

anchor="  List<Map<String, dynamic>> gmailRejectedImages = [];"
assert s.count(anchor)==1
s=s.replace(anchor,anchor+"\n  String gmailPhotoAnalysisReport = '';",1)
anchor="    gmailRejectedImages = dynList(widget.existing?['gmailRejectedImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();"
assert s.count(anchor)==1
s=s.replace(anchor,anchor+"\n    gmailPhotoAnalysisReport = (widget.existing?['gmailPhotoAnalysisReport'] ?? '').toString();",1)

a=s.index('  Future<void> _smartFilterAndCacheGmailPhotos() async {')
b=s.index('  Future<void> _showRejectedGmailPhotos() async {',a)
part=s[a:b]
anchor="    final offline = result['offlinePaths'];"
assert part.count(anchor)==1
report="""    final rawStats = result['analysisDiagnostics'];
    final stats = rawStats is Map ? rawStats : <String, dynamic>{};
    int n(String key) => (stats[key] as num?)?.toInt() ?? 0;
    final report = 'Imágenes: ${n('candidates')} recibidas · '
        '${n('downloaded')} descargadas · ${n('decoded')} abiertas · '
        '${n('evaluated')} evaluadas · ${n('ocrAttempts')} OCR · '
        '${accepted.length} aceptadas · ${rejected.length} por revisar';
    // A network/analysis failure is not a classification. Keep the original
    // Gmail result pending so the user can retry without losing the photos.
    const transient = <String>{'imagen no disponible', 'no se pudo analizar'};
    if (accepted.isEmpty && rejected.isNotEmpty &&
        rejected.every((e) => transient.contains(
            (e['rejectReason'] ?? '').toString()))) {
      throw StateError('Gmail encontró imágenes, pero falló su análisis. '
          'No se han borrado y puedes reintentar.');
    }
"""
part=part.replace(anchor,report+anchor,1)
anchor="      gmailRejectedImages = rejected;"
assert part.count(anchor)==1
part=part.replace(anchor,anchor+"\n      gmailPhotoAnalysisReport = report;",1)
s=s[:a]+part+s[b:]
# Preserve report on explicit save and durable auto save.
key="'gmailRejectedImages': gmailRejectedImages,"
assert s.count(key)>=1
s=s.replace(key,key+"\n      'gmailPhotoAnalysisReport': gmailPhotoAnalysisReport,")
ui="        TextField(controller: gmailStore, decoration: const InputDecoration(labelText: 'Tienda detectada / tienda')),"
assert s.count(ui)==1
s=s.replace(ui,"""        if (gmailPhotoAnalysisReport.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: SelectableText(gmailPhotoAnalysisReport),
          ),
"""+ui,1)
p.write_text(s)
print('Gmail v47: learning per-key, photo filtering before auxiliary OCR, diagnostic counts and safe retry.')
