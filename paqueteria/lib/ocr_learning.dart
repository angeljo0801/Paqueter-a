part of 'main.dart';

class OcrLearningApplication {
  final StoreOcrParse parsed;
  final int appliedRules;
  const OcrLearningApplication(this.parsed, this.appliedRules);
}

class OcrLearningService {
  static const String _key = 'ocrLearningSamples';
  static const int _maxSamples = 120;

  static final RegExp _money = RegExp(
    r'(?:US\s*)?\$?\s*(-?\d{1,6}(?:,\d{3})*(?:[.,]\d{2}))',
    caseSensitive: false,
  );

  static Future<OcrLearningApplication> apply(
    String rawText,
    StoreOcrParse parsed,
  ) async {
    final samples = await Store.list(_key);
    if (samples.isEmpty || rawText.trim().isEmpty) {
      return OcrLearningApplication(parsed, 0);
    }

    var store = parsed.store;
    var total = parsed.total;
    var orderNumber = parsed.orderNumber;
    final items = parsed.items.map((e) => {...e}).toList();
    var applied = 0;
    final upper = _normalizeText(rawText).toUpperCase();

    for (final sample in samples.reversed) {
      final token = '\${sample['storeToken'] ?? ''}'.trim();
      final corrected = '\${sample['correctedStore'] ?? ''}'.trim();
      if (token.isEmpty || corrected.isEmpty) continue;
      if (upper.contains(token.toUpperCase()) &&
          corrected.toLowerCase() != store.toLowerCase()) {
        store = corrected;
        applied++;
        break;
      }
    }

    final totalLabels = <String, int>{};
    final orderLabels = <String, int>{};
    final itemNames = <String, String>{};
    final pricePreferences = <String, int>{};

    for (final sample in samples) {
      if (!_sampleMatchesStore(sample, store)) continue;

      final totalLabel = '\${sample['totalLabel'] ?? ''}'.trim();
      if (totalLabel.isNotEmpty) {
        totalLabels[totalLabel] = (totalLabels[totalLabel] ?? 0) + 1;
      }

      final orderLabel = '\${sample['orderLabel'] ?? ''}'.trim();
      if (orderLabel.isNotEmpty) {
        orderLabels[orderLabel] = (orderLabels[orderLabel] ?? 0) + 1;
      }

      for (final raw in dynList(sample['itemNameCorrections'])) {
        if (raw is! Map) continue;
        final correction = Map<String, dynamic>.from(raw);
        final from = _normalizeItem('\${correction['from'] ?? ''}');
        final to = '\${correction['to'] ?? ''}'.trim();
        if (from.isNotEmpty && to.isNotEmpty) itemNames[from] = to;
      }

      final preference = '\${sample['pricePreference'] ?? ''}'.trim();
      if (preference.isNotEmpty) {
        pricePreferences[preference] =
            (pricePreferences[preference] ?? 0) + 1;
      }
    }

    final learnedTotal = _findLearnedAmount(rawText, totalLabels);
    if (learnedTotal > 0 && (learnedTotal - total).abs() > 0.009) {
      total = learnedTotal;
      applied++;
    }

    final learnedOrder = _findLearnedOrder(rawText, orderLabels);
    if (learnedOrder.isNotEmpty &&
        learnedOrder.toUpperCase() != orderNumber.toUpperCase()) {
      orderNumber = learnedOrder;
      applied++;
    }

    for (final item in items) {
      final from = _normalizeItem('\${item['name'] ?? ''}');
      final replacement = itemNames[from];
      if (replacement != null &&
          replacement.isNotEmpty &&
          replacement != '\${item['name'] ?? ''}') {
        item['name'] = replacement;
        applied++;
      }
    }

    if (pricePreferences.isNotEmpty) {
      final sorted = pricePreferences.entries.toList()
        ..sort((a, b) => b.value.compareTo(a.value));
      final best = sorted.first;
      final runnerUp = sorted.length > 1 ? sorted[1].value : 0;
      if (best.value >= 2 && best.value > runnerUp) {
        for (final item in items) {
          final learnedPrice =
              _priceForItem(rawText, '\${item['name'] ?? ''}', best.key);
          if (learnedPrice > 0 &&
              (learnedPrice - number(item['price'])).abs() > 0.009) {
            item['price'] = learnedPrice;
            applied++;
          }
        }
      }
    }

    final adjusted = StoreOcrParse(
      store: store,
      orderNumber: orderNumber,
      total: total,
      subtotal: parsed.subtotal,
      tax: parsed.tax,
      shipping: parsed.shipping,
      discount: parsed.discount,
      expectedItemCount: parsed.expectedItemCount,
      items: items,
      warnings: parsed.warnings,
      confidence:
          (parsed.confidence + (applied > 0 ? 0.03 : 0.0)).clamp(0.0, 1.0),
    );
    return OcrLearningApplication(adjusted, applied);
  }

  static Future<int> learnFromCorrection({
    required String rawText,
    required String detectedStore,
    required double detectedTotal,
    required String detectedOrderNumber,
    required List<Map<String, dynamic>> detectedItems,
    required String correctedStore,
    required double correctedTotal,
    required String correctedOrderNumber,
    required List<Map<String, dynamic>> correctedItems,
  }) async {
    if (rawText.trim().isEmpty) return 0;

    var changes = 0;
    final sample = <String, dynamic>{
      'id': newId(),
      'createdAt': DateTime.now().toIso8601String(),
      'detectedStore': detectedStore,
      'correctedStore': correctedStore,
    };

    if (correctedStore.trim().isNotEmpty &&
        correctedStore.trim().toLowerCase() !=
            detectedStore.trim().toLowerCase()) {
      final token = _storeToken(rawText, correctedStore);
      if (token.isNotEmpty) {
        sample['storeToken'] = token;
        changes++;
      }
    }

    if (correctedTotal > 0 &&
        (correctedTotal - detectedTotal).abs() > 0.009) {
      final label = _labelForAmount(rawText, correctedTotal);
      if (label.isNotEmpty) sample['totalLabel'] = label;
      changes++;
    }

    if (correctedOrderNumber.trim().isNotEmpty &&
        correctedOrderNumber.trim().toUpperCase() !=
            detectedOrderNumber.trim().toUpperCase()) {
      final label = _labelForOrder(rawText, correctedOrderNumber);
      if (label.isNotEmpty) sample['orderLabel'] = label;
      changes++;
    }

    final detectedById = <String, Map<String, dynamic>>{
      for (final item in detectedItems) '\${item['id'] ?? ''}': item,
    };
    final nameCorrections = <Map<String, dynamic>>[];
    String pricePreference = '';

    for (final corrected in correctedItems) {
      final id = '\${corrected['id'] ?? ''}';
      final detected = detectedById[id];
      if (detected == null) continue;

      final oldName = '\${detected['name'] ?? ''}'.trim();
      final newName = '\${corrected['name'] ?? ''}'.trim();
      if (oldName.isNotEmpty &&
          newName.isNotEmpty &&
          _normalizeItem(oldName) != _normalizeItem(newName)) {
        nameCorrections.add({'from': oldName, 'to': newName});
        changes++;
      }

      final oldPrice = number(detected['price']);
      final newPrice = number(corrected['price']);
      if (newPrice > 0 && (newPrice - oldPrice).abs() > 0.009) {
        final preference =
            _pricePreferenceForCorrection(rawText, oldName, oldPrice, newPrice);
        if (preference.isNotEmpty) pricePreference = preference;
        changes++;
      }
    }

    if (nameCorrections.isNotEmpty) {
      sample['itemNameCorrections'] = nameCorrections;
    }
    if (pricePreference.isNotEmpty) {
      sample['pricePreference'] = pricePreference;
    }

    if (changes == 0) return 0;

    final samples = await Store.list(_key);
    samples.add(sample);
    if (samples.length > _maxSamples) {
      samples.removeRange(0, samples.length - _maxSamples);
    }
    await Store.saveList(_key, samples);
    return changes;
  }

  static Future<int> ruleCount() async => (await Store.list(_key)).length;

  static Future<void> clear() async => Store.saveList(_key, []);

  static bool _sampleMatchesStore(
    Map<String, dynamic> sample,
    String store,
  ) {
    final key = store.trim().toLowerCase();
    if (key.isEmpty) return false;
    final detected = '\${sample['detectedStore'] ?? ''}'.trim().toLowerCase();
    final corrected = '\${sample['correctedStore'] ?? ''}'.trim().toLowerCase();
    return detected == key || corrected == key;
  }

  static String _normalizeText(String raw) => raw
      .replaceAll('\u00A0', ' ')
      .replaceAll('＄', r'$')
      .replaceAll('–', '-')
      .replaceAll('—', '-')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();

  static List<String> _lines(String raw) => raw
      .replaceAll('\u00A0', ' ')
      .split(RegExp(r'[\r\n]+'))
      .map((e) => e.replaceAll(RegExp(r'\s+'), ' ').trim())
      .where((e) => e.isNotEmpty)
      .toList();

  static String _normalizeLabel(String raw) {
    var value = raw.toUpperCase();
    value = value.replaceAll(_money, ' ');
    value = value.replaceAll(RegExp(r'\b\d+\b'), ' ');
    value = value.replaceAll(RegExp(r'[^A-ZÁÉÍÓÚÑ ]'), ' ');
    value = value.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (value.length > 56) value = value.substring(0, 56).trim();
    return value;
  }

  static String _normalizeItem(String raw) => raw
      .toUpperCase()
      .replaceAll(RegExp(r'[^A-Z0-9ÁÉÍÓÚÑ ]'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();

  static List<double> _moneyValues(String line) {
    final out = <double>[];
    for (final match in _money.allMatches(line)) {
      var raw = '\${match.group(1) ?? ''}'
          .replaceAll(RegExp(r'[^0-9,.\-]'), '');
      if (raw.contains(',') && !raw.contains('.')) {
        if (RegExp(r',\d{2}$').hasMatch(raw)) {
          raw = raw.replaceAll(',', '.');
        } else {
          raw = raw.replaceAll(',', '');
        }
      } else {
        raw = raw.replaceAll(',', '');
      }
      final value = double.tryParse(raw);
      if (value != null) out.add(value.abs());
    }
    return out;
  }

  static bool _sameAmount(double a, double b) => (a - b).abs() <= 0.011;

  static String _labelForAmount(String raw, double amount) {
    final lines = _lines(raw);
    for (var i = lines.length - 1; i >= 0; i--) {
      final values = _moneyValues(lines[i]);
      if (!values.any((v) => _sameAmount(v, amount))) continue;
      final label = _normalizeLabel(lines[i]);
      if (label.isNotEmpty) return label;
      if (i > 0) {
        final previous = _normalizeLabel(lines[i - 1]);
        if (previous.isNotEmpty) return previous;
      }
      if (i + 1 < lines.length) {
        final next = _normalizeLabel(lines[i + 1]);
        if (next.isNotEmpty) return next;
      }
    }
    return '';
  }

  static double _findLearnedAmount(
    String raw,
    Map<String, int> labels,
  ) {
    if (labels.isEmpty) return 0;
    final ranked = labels.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final lines = _lines(raw);
    for (final entry in ranked) {
      final label = entry.key;
      for (var i = lines.length - 1; i >= 0; i--) {
        if (!_normalizeLabel(lines[i]).contains(label)) continue;
        final values = _moneyValues(lines[i]);
        if (values.isNotEmpty) return values.last;
        if (i + 1 < lines.length) {
          final next = _moneyValues(lines[i + 1]);
          if (next.isNotEmpty) return next.first;
        }
      }
    }
    return 0;
  }

  static String _labelForOrder(String raw, String order) {
    final target = order.trim().toUpperCase();
    if (target.isEmpty) return '';
    final lines = _lines(raw);
    for (var i = 0; i < lines.length; i++) {
      final upper = lines[i].toUpperCase();
      if (!upper.contains(target)) continue;
      final label = _normalizeLabel(
        upper.replaceAll(target, ' '),
      );
      if (label.isNotEmpty) return label;
      if (i > 0) {
        final previous = _normalizeLabel(lines[i - 1]);
        if (previous.isNotEmpty) return previous;
      }
    }
    return '';
  }

  static String _findLearnedOrder(
    String raw,
    Map<String, int> labels,
  ) {
    if (labels.isEmpty) return '';
    final ranked = labels.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final lines = _lines(raw);
    final candidate = RegExp(r'\b[A-Z0-9][A-Z0-9-]{4,}\b');
    for (final entry in ranked) {
      for (final line in lines) {
        if (!_normalizeLabel(line).contains(entry.key)) continue;
        for (final match in candidate.allMatches(line.toUpperCase())) {
          final value = match.group(0) ?? '';
          if (!RegExp(r'\d').hasMatch(value)) continue;
          if (entry.key.split(' ').contains(value)) continue;
          return value;
        }
      }
    }
    return '';
  }

  static String _storeToken(String raw, String correctedStore) {
    final upper = raw.toUpperCase();
    final tokens = correctedStore
        .toUpperCase()
        .replaceAll(RegExp(r'[^A-Z0-9 ]'), ' ')
        .split(RegExp(r'\s+'))
        .where((e) => e.length >= 3 && upper.contains(e))
        .toList()
      ..sort((a, b) => b.length.compareTo(a.length));
    return tokens.isEmpty ? '' : tokens.first;
  }

  static String _pricePreferenceForCorrection(
    String raw,
    String itemName,
    double oldPrice,
    double correctedPrice,
  ) {
    if (itemName.trim().isEmpty) return '';
    final line = _bestItemLine(raw, itemName);
    if (line.isEmpty) return '';
    final values = _moneyValues(line);
    if (values.length < 2) return '';
    final correctedIndex =
        values.indexWhere((v) => _sameAmount(v, correctedPrice));
    final oldIndex = values.indexWhere((v) => _sameAmount(v, oldPrice));
    if (correctedIndex < 0 || oldIndex < 0 || correctedIndex == oldIndex) {
      return '';
    }
    if (correctedIndex == 0) return 'first';
    if (correctedIndex == values.length - 1) return 'last';
    return '';
  }

  static double _priceForItem(
    String raw,
    String itemName,
    String preference,
  ) {
    final line = _bestItemLine(raw, itemName);
    if (line.isEmpty) return 0;
    final values = _moneyValues(line);
    if (values.length < 2) return 0;
    if (preference == 'first') return values.first;
    if (preference == 'last') return values.last;
    return 0;
  }

  static String _bestItemLine(String raw, String itemName) {
    final wanted = _normalizeItem(itemName)
        .split(' ')
        .where((e) => e.length >= 4)
        .take(5)
        .toList();
    if (wanted.isEmpty) return '';
    String best = '';
    var bestScore = 0;
    for (final line in _lines(raw)) {
      final normalized = _normalizeItem(line);
      var score = 0;
      for (final token in wanted) {
        if (normalized.contains(token)) score++;
      }
      if (score > bestScore && _moneyValues(line).isNotEmpty) {
        best = line;
        bestScore = score;
      }
    }
    return bestScore > 0 ? best : '';
  }
}
