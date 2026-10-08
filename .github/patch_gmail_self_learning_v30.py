from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'Missing expected block: {label}')
    return text.replace(old, new, 1)


main = Path('app/lib/main.dart')
ms = main.read_text()
if "import 'dart:typed_data';" not in ms:
    ms = replace_once(
        ms,
        "import 'dart:io';\n",
        "import 'dart:io';\nimport 'dart:typed_data';\n",
        'typed_data import',
    )
main.write_text(ms)

helper_path = Path('app/lib/gmail_purchase_link.dart')
hs = helper_path.read_text()

learning = r'''
class GmailPhotoLearningDecision {
  final bool reject;
  final bool positive;
  final double negativeScore;
  final double positiveScore;
  final String reason;

  const GmailPhotoLearningDecision({
    required this.reject,
    required this.positive,
    required this.negativeScore,
    required this.positiveScore,
    required this.reason,
  });
}

class GmailPhotoLearningService {
  static const String _key = 'gmail_photo_learning_v1';
  static const int _maxExamples = 420;

  static const List<String> _seedNegativeHashes = <String>[
    '00111000100110000010100010010000000100100000000100000010',
    '10000001000110100010010110000010011011001101100101110010',
    '01101010110101111010110101011010100101100000110010111001',
    '10101001000110111100001100010000110001000100000010000001',
    '01101101001011101100110110101011010101001001100010111011',
  ];

  static Set<String> _tokens(String text) {
    final normalized = text
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9áéíóúüñ]+'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    if (normalized.isEmpty) return <String>{};
    const stop = <String>{
      'the', 'and', 'for', 'with', 'from', 'your', 'you', 'this', 'that',
      'una', 'uno', 'unos', 'unas', 'para', 'con', 'por', 'del', 'las',
      'los', 'que', 'como', 'este', 'esta', 'sus', 'más', 'mas',
    };
    return normalized
        .split(' ')
        .where((e) => e.length >= 3 && !stop.contains(e))
        .take(36)
        .toSet();
  }

  static Set<String> _urlTokens(String url) {
    final value = Uri.tryParse(url);
    final host = value?.host ?? '';
    final path = value?.path ?? url;
    return _tokens('$host $path');
  }

  static int _hamming(String a, String b) {
    if (a.length != b.length || a.isEmpty) return 999;
    var diff = 0;
    for (var i = 0; i < a.length; i++) {
      if (a.codeUnitAt(i) != b.codeUnitAt(i)) diff++;
    }
    return diff;
  }

  static double _jaccard(Set<String> a, Set<String> b) {
    if (a.isEmpty || b.isEmpty) return 0;
    final intersection = a.intersection(b).length;
    final union = a.union(b).length;
    return union == 0 ? 0 : intersection / union;
  }

  static Future<String> _visualHash(List<int> rawBytes) async {
    if (rawBytes.isEmpty) return '';
    try {
      final bytes = rawBytes is Uint8List
          ? rawBytes
          : Uint8List.fromList(rawBytes);
      final codec = await ui.instantiateImageCodec(
        bytes,
        targetWidth: 8,
        targetHeight: 8,
      );
      final frame = await codec.getNextFrame();
      final image = frame.image;
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (data == null) {
        image.dispose();
        codec.dispose();
        return '';
      }
      final gray = <int>[];
      for (var i = 0; i < 64; i++) {
        final offset = i * 4;
        final r = data.getUint8(offset);
        final g = data.getUint8(offset + 1);
        final b = data.getUint8(offset + 2);
        gray.add(((r * 299) + (g * 587) + (b * 114)) ~/ 1000);
      }
      image.dispose();
      codec.dispose();

      final out = StringBuffer();
      for (var y = 0; y < 8; y++) {
        for (var x = 0; x < 7; x++) {
          out.write(gray[y * 8 + x] > gray[y * 8 + x + 1] ? '1' : '0');
        }
      }
      return out.toString();
    } catch (_) {
      return '';
    }
  }

  static bool _seededTextReject(String ocrText, String url) {
    final lower = ocrText
        .toLowerCase()
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    final lowerUrl = url.toLowerCase();

    final spanishReturnHelp =
        (lower.contains('pregunta') && lower.contains('necesitas ayuda')) ||
        lower.contains('proceso de devolución') ||
        lower.contains('proceso de devolucion') ||
        lower.contains('solicitud de devolución') ||
        lower.contains('solicitud de devolucion') ||
        (lower.contains('etiqueta de envío') &&
            lower.contains('devolución')) ||
        (lower.contains('etiqueta de envio') &&
            lower.contains('devolucion')) ||
        (lower.contains('inspección de calidad') &&
            lower.contains('reembolso')) ||
        (lower.contains('inspeccion de calidad') &&
            lower.contains('reembolso'));

    final deliveryUtilityUrl = <String>[
      'proof-of-delivery',
      'proof_delivery',
      'delivery-proof',
      'delivery_proof',
      'doorstep',
      'delivered-photo',
      'delivery-photo',
      'delivery_image',
      'deliveryimage',
      'pod-image',
      'pod_photo',
      'shipping-truck',
      'delivery-truck',
      'carrier-icon',
    ].any(lowerUrl.contains);

    final deliveryProofText =
        lower.contains('proof of delivery') ||
        lower.contains('delivery photo') ||
        lower.contains('delivered to your door') ||
        lower.contains('left at front door') ||
        lower.contains('left at the front door') ||
        lower.contains('package was left') ||
        lower.contains('foto de entrega') ||
        lower.contains('prueba de entrega');

    return spanishReturnHelp || deliveryUtilityUrl || deliveryProofText;
  }

  static Future<List<Map<String, dynamic>>> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.isEmpty) return <Map<String, dynamic>>[];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return <Map<String, dynamic>>[];
      return decoded
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    } catch (_) {
      return <Map<String, dynamic>>[];
    }
  }

  static Future<void> _save(List<Map<String, dynamic>> examples) async {
    final prefs = await SharedPreferences.getInstance();
    final compact = examples.length <= _maxExamples
        ? examples
        : examples.sublist(examples.length - _maxExamples);
    await prefs.setString(_key, jsonEncode(compact));
  }

  static Future<GmailPhotoLearningDecision> decide({
    required List<int> bytes,
    required String ocrText,
    required String url,
    required int width,
    required int height,
  }) async {
    if (_seededTextReject(ocrText, url)) {
      return const GmailPhotoLearningDecision(
        reject: true,
        positive: false,
        negativeScore: 100,
        positiveScore: 0,
        reason: 'corrección aprendida: entrega/ayuda',
      );
    }

    final hash = await _visualHash(bytes);
    if (hash.isNotEmpty) {
      for (final seed in _seedNegativeHashes) {
        if (_hamming(hash, seed) <= 7) {
          return const GmailPhotoLearningDecision(
            reject: true,
            positive: false,
            negativeScore: 100,
            positiveScore: 0,
            reason: 'corrección visual aprendida',
          );
        }
      }
    }

    final examples = await _load();
    if (examples.isEmpty) {
      return const GmailPhotoLearningDecision(
        reject: false,
        positive: false,
        negativeScore: 0,
        positiveScore: 0,
        reason: '',
      );
    }

    final words = _tokens(ocrText);
    final urls = _urlTokens(url);
    final ratio = height > 0 ? width / height : 0.0;
    var negative = 0.0;
    var positive = 0.0;

    for (final example in examples) {
      final label = '${example['label'] ?? ''}';
      var score = 0.0;

      final learnedHash = '${example['hash'] ?? ''}';
      if (hash.isNotEmpty && learnedHash.isNotEmpty) {
        final d = _hamming(hash, learnedHash);
        if (d <= 5) {
          score += 9;
        } else if (d <= 9) {
          score += 6;
        } else if (d <= 13) {
          score += 3;
        }
      }

      final learnedWords = dynList(example['tokens'])
          .map((e) => '$e')
          .toSet();
      final textSim = _jaccard(words, learnedWords);
      if (textSim >= .70) {
        score += 6;
      } else if (textSim >= .48) {
        score += 4;
      } else if (textSim >= .30) {
        score += 2;
      }

      final learnedUrls = dynList(example['urlTokens'])
          .map((e) => '$e')
          .toSet();
      final urlSim = _jaccard(urls, learnedUrls);
      if (urlSim >= .65) {
        score += 3;
      } else if (urlSim >= .40) {
        score += 1.5;
      }

      final learnedRatio = (example['ratio'] as num?)?.toDouble() ?? 0;
      if (ratio > 0 &&
          learnedRatio > 0 &&
          (ratio - learnedRatio).abs() <= .10) {
        score += .5;
      }

      if (label == 'negative') {
        negative = negative > score ? negative : score;
      } else if (label == 'positive') {
        positive = positive > score ? positive : score;
      }
    }

    final reject = negative >= 6 && negative >= positive + 2;
    final keep = positive >= 6 && positive >= negative + 2;
    return GmailPhotoLearningDecision(
      reject: reject,
      positive: keep,
      negativeScore: negative,
      positiveScore: positive,
      reason: reject ? 'descartada por aprendizaje local' : '',
    );
  }

  static Future<void> rememberImage({
    required Map<String, dynamic> image,
    required String baseUrl,
    required String apiKey,
    required bool product,
  }) async {
    try {
      List<int> bytes = const <int>[];
      var localPath = '${image['localPath'] ?? ''}'.trim();
      final url = '${image['url'] ?? ''}'.trim();

      if (localPath.isNotEmpty && File(localPath).existsSync()) {
        bytes = await File(localPath).readAsBytes();
      } else if (url.isNotEmpty) {
        final response = await http.get(
          Uri.parse(gmailPhotoUrl(baseUrl, image)),
          headers: gmailPhotoHeaders(baseUrl, apiKey, image) ??
              const <String, String>{},
        ).timeout(const Duration(seconds: 18));
        if (response.statusCode >= 200 && response.statusCode < 300) {
          bytes = response.bodyBytes;
        }
      }
      if (bytes.isEmpty) return;

      var ocrText = '${image['ocrText'] ?? ''}'.trim();
      File? temp;
      if (ocrText.isEmpty) {
        if (localPath.isEmpty || !File(localPath).existsSync()) {
          final dir = await getTemporaryDirectory();
          temp = File(
            '${dir.path}/gmail_learning_${DateTime.now().microsecondsSinceEpoch}.jpg',
          );
          await temp.writeAsBytes(bytes, flush: true);
          localPath = temp.path;
        }
        ocrText = await _gmailOcrFile(localPath);
      }

      final hash = await _visualHash(bytes);
      final width = (image['width'] as num?)?.toInt() ?? 0;
      final height = (image['height'] as num?)?.toInt() ?? 0;
      final example = <String, dynamic>{
        'label': product ? 'positive' : 'negative',
        'hash': hash,
        'tokens': _tokens(ocrText).toList(),
        'urlTokens': _urlTokens(url).toList(),
        'ratio': height > 0 ? width / height : 0.0,
        'learnedAt': DateTime.now().toIso8601String(),
      };

      final examples = await _load();
      examples.removeWhere((e) =>
          '${e['label'] ?? ''}' == example['label'] &&
          hash.isNotEmpty &&
          '${e['hash'] ?? ''}' == hash);
      examples.add(example);
      await _save(examples);
      if (temp != null && await temp.exists()) {
        await temp.delete();
      }
    } catch (_) {}
  }
}

'''

if 'class GmailPhotoLearningService {' not in hs:
    anchor = 'bool gmailOrderItemPhotoSignals(String text) {\n'
    hs = replace_once(
        hs,
        anchor,
        learning + anchor,
        'Gmail self-learning service',
    )

func_start = hs.find('Future<Map<String, dynamic>> gmailPrepareProductPhotos({')
func_end = hs.find('\nWidget gmailSmartPhotoImage(', func_start)
if func_start < 0 or func_end < 0:
    raise SystemExit('Could not locate gmailPrepareProductPhotos')
func = hs[func_start:func_end]

decision_anchor = r'''      final matchedItem = _gmailMatchedItem(ocr, items);
      final orderItemSignals = gmailOrderItemPhotoSignals(ocr);
      final catalogCard = gmailCatalogRecommendationCard(ocr);
'''
decision_new = r'''      final matchedItem = _gmailMatchedItem(ocr, items);
      final orderItemSignals = gmailOrderItemPhotoSignals(ocr);
      final catalogCard = gmailCatalogRecommendationCard(ocr);
      final learnedDecision = await GmailPhotoLearningService.decide(
        bytes: bytes,
        ocrText: ocr,
        url: rawUrl,
        width: width,
        height: height,
      );
      if (learnedDecision.reject &&
          matchedItem.isEmpty &&
          !orderItemSignals) {
        await temp.delete().catchError((_) => temp);
        rejected.add({
          ...image,
          'width': width,
          'height': height,
          'ocrText': ocr,
          'rejectReason': learnedDecision.reason,
          'learningNegativeScore': learnedDecision.negativeScore,
        });
        continue;
      }
'''
func = replace_once(
    func,
    decision_anchor,
    decision_new,
    'apply learned Gmail decision',
)

score_anchor = r'''      if (orderItemSignals) score += 6;
      if (matchedItem.isNotEmpty) score += 4;
'''
score_new = r'''      if (orderItemSignals) score += 6;
      if (matchedItem.isNotEmpty) score += 4;
      if (learnedDecision.positive) score += 5;
'''
func = replace_once(
    func,
    score_anchor,
    score_new,
    'boost learned positive product',
)

hs = hs[:func_start] + func + hs[func_end:]

delete_anchor = r'''                          if (!ok) return;

                          removed.add(raw);
'''
delete_new = r'''                          if (!ok) return;

                          await GmailPhotoLearningService.rememberImage(
                            image: image,
                            baseUrl: baseUrl,
                            apiKey: apiKey,
                            product: false,
                          );
                          removed.add(raw);
'''
hs = replace_once(
    hs,
    delete_anchor,
    delete_new,
    'learn from shared Gmail photo deletion',
)

recover_anchor = r'''                    onPressed: working.isEmpty
                        ? null
                        : () {
                            final image = working[currentIndex];
                            final raw = '${image['url'] ?? ''}'.trim();
                            if (raw.isEmpty) return;
                            recoveredSink?.add(raw);
'''
recover_new = r'''                    onPressed: working.isEmpty
                        ? null
                        : () async {
                            final image = working[currentIndex];
                            final raw = '${image['url'] ?? ''}'.trim();
                            if (raw.isEmpty) return;
                            await GmailPhotoLearningService.rememberImage(
                              image: image,
                              baseUrl: baseUrl,
                              apiKey: apiKey,
                              product: true,
                            );
                            recoveredSink?.add(raw);
'''
hs = replace_once(
    hs,
    recover_anchor,
    recover_new,
    'learn from restored Gmail product photo',
)

helper_path.write_text(hs)


packages = Path('app/lib/packages.dart')
ps = packages.read_text()
fn_start = ps.find('  Future<void> removeEmailPhoto(Map<String, dynamic> image) async {')
fn_end = ps.find('\n  Future<void> save() async {', fn_start)
if fn_start >= 0 and fn_end > fn_start:
    fn = ps[fn_start:fn_end]
    if 'GmailPhotoLearningService.rememberImage' not in fn:
        fn = replace_once(
            fn,
            "    if (remove != true || !mounted) return;\n",
            "    if (remove != true || !mounted) return;\n"
            "    await GmailPhotoLearningService.rememberImage(\n"
            "      image: image,\n"
            "      baseUrl: gmailBackendUrl,\n"
            "      apiKey: gmailApiKey,\n"
            "      product: false,\n"
            "    );\n"
            "    if (!mounted) return;\n",
            'learn from package X deletion',
        )
        ps = ps[:fn_start] + fn + ps[fn_end:]
packages.write_text(ps)


purchases = Path('app/lib/purchases.dart')
us = purchases.read_text()
fn_start = us.find(
    '  Future<void> _removePurchaseEmailPhoto(Map<String, dynamic> image) async {'
)
if fn_start >= 0:
    fn_end = us.find('\n  Future<void>', fn_start + 20)
    if fn_end < 0:
        fn_end = len(us)
    fn = us[fn_start:fn_end]
    if 'GmailPhotoLearningService.rememberImage' not in fn:
        marker = "    if (ok != true || !mounted) return;\n"
        if marker in fn:
            fn = fn.replace(
                marker,
                marker
                + "    await GmailPhotoLearningService.rememberImage(\n"
                + "      image: image,\n"
                + "      baseUrl: gmailPurchaseBackendUrl,\n"
                + "      apiKey: gmailPurchaseApiKey,\n"
                + "      product: false,\n"
                + "    );\n"
                + "    if (!mounted) return;\n",
                1,
            )
            us = us[:fn_start] + fn + us[fn_end:]
purchases.write_text(us)


clients = Path('app/lib/clients.dart')
cs = clients.read_text()

dstart = cs.find('  Future<void> _deletePhotos(List<Map<String, dynamic>> targets) async {')
dend = cs.find('\n  List<Map<String, dynamic>> _selectedPhotos()', dstart)
if dstart < 0 or dend < 0:
    raise SystemExit('Could not locate client photo delete method')
dfn = cs[dstart:dend]
delete_marker = r'''      final url = '${photo['url'] ?? ''}'.trim();
      if (url.isEmpty) continue;
'''
delete_replacement = r'''      await GmailPhotoLearningService.rememberImage(
        image: photo,
        baseUrl: gmailBackendUrl,
        apiKey: gmailApiKey,
        product: false,
      );
      final url = '${photo['url'] ?? ''}'.trim();
      if (url.isEmpty) continue;
'''
dfn = replace_once(
    dfn,
    delete_marker,
    delete_replacement,
    'learn from client dashboard Gmail deletion',
)
cs = cs[:dstart] + dfn + cs[dend:]

sstart = cs.find('  Future<void> _setReceived(')
send = cs.find('\n  Future<void> _deletePhotos(', sstart)
if sstart < 0 or send < 0:
    raise SystemExit('Could not locate client photo received method')
sfn = cs[sstart:send]
loop_anchor = r'''    for (final photo in targets) {
      final id = '${photo['packageId'] ?? ''}'.trim();
'''
loop_new = r'''    for (final photo in targets) {
      if (received && '${photo['source'] ?? 'gmail'}' == 'gmail') {
        await GmailPhotoLearningService.rememberImage(
          image: photo,
          baseUrl: gmailBackendUrl,
          apiKey: gmailApiKey,
          product: true,
        );
      }
      final id = '${photo['packageId'] ?? ''}'.trim();
'''
sfn = replace_once(
    sfn,
    loop_anchor,
    loop_new,
    'learn positive from Received in Cuba',
)
cs = cs[:sstart] + sfn + cs[send:]
clients.write_text(cs)

print('Gmail v30 applied: persistent self-learning photo filter + five supplied false-positive seeds.')
