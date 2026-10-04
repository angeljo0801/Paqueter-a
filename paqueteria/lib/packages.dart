part of 'main.dart';

List<String> packagePhotoPaths(Map<String, dynamic> package) {
  final out = <String>[];
  final raw = package['photoPaths'];
  if (raw is List) {
    for (final value in raw) {
      final path = '$value'.trim();
      if (path.isNotEmpty && !out.contains(path)) out.add(path);
    }
  }
  final legacy = '${package['photoPath'] ?? ''}'.trim();
  if (legacy.isNotEmpty && !out.contains(legacy)) out.add(legacy);
  return out;
}

class PackagesPage extends StatefulWidget {
  const PackagesPage({super.key});
  @override
  State<PackagesPage> createState() => _PackagesPageState();
}

class _PackagesPageState extends State<PackagesPage> {
  List<Map<String, dynamic>> rows = [], clients = [];
  String q = '';
  @override
  void initState() { super.initState(); load(); }
  Future<void> load() async {
    final r = await Future.wait([Store.list('packages'), Store.list('clients')]);
    if (!mounted) return;
    setState(() { rows = active(r[0]); clients = active(r[1]); });
  }

  @override
  Widget build(BuildContext context) {
    final f = rows.where((p) => ('${p['tracking']} ${clientName(clients, '${p['clientId']}')} ${p['status']} ${p['carrier']}').toLowerCase().contains(q.toLowerCase())).toList();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Paquetes'),
        actions: [
          IconButton(
            tooltip: 'Escanear código',
            icon: const Icon(Icons.qr_code_scanner),
            onPressed: () async {
              final code = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScannerPage()));
              if (code != null && mounted) {
                final existing = rows.where((e) => '${e['tracking']}' == code).firstOrNull;
                if (existing != null) {
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Este código ya pertenece a ${clientName(clients, '${existing['clientId']}')}.')));
                  await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(existing: existing)));
                } else {
                  await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(initialTracking: code)));
                }
                load();
              }
            },
          ),
        ],
      ),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: TextField(
            onChanged: (v) => setState(() => q = v),
            decoration: const InputDecoration(prefixIcon: Icon(Icons.search), hintText: 'Tracking o nombre del cliente'),
          ),
        ),
        Expanded(
          child: f.isEmpty
              ? const Center(child: Text('No hay paquetes.'))
              : ListView.builder(
                  itemCount: f.length,
                  itemBuilder: (_, i) {
                    final p = f[i];
                    final remote = '${p['courierStatusEs'] ?? ''}'.trim();
                    return ListTile(
                      leading: Builder(builder: (_) {
                        final photos = packagePhotoPaths(p)
                            .where((path) => File(path).existsSync())
                            .toList();
                        if (photos.isEmpty) return const Icon(Icons.inventory_2);
                        return ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: Image.file(
                            File(photos.first),
                            width: 52,
                            height: 52,
                            fit: BoxFit.cover,
                          ),
                        );
                      }),
                      title: Text('${p['tracking']}'),
                      subtitle: Text('${clientName(clients, '${p['clientId']}')} · ${p['carrier']}\n${remote.isNotEmpty ? remote : p['status']} · ${number(p['billWeight']).toStringAsFixed(1)} lb'),
                      isThreeLine: true,
                      onTap: () async { await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(existing: p))); load(); },
                      trailing: IconButton(icon: const Icon(Icons.delete_outline), onPressed: () async { if (await confirmDelete(context, 'este paquete')) { await softDelete('packages', '${p['id']}'); load(); } }),
                    );
                  },
                ),
        ),
      ]),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async { await Navigator.push(context, MaterialPageRoute(builder: (_) => const PackageEditPage())); load(); },
        icon: const Icon(Icons.add),
        label: const Text('Paquete'),
      ),
    );
  }
}

String inferCarrier(String tracking) {
  final t = tracking.trim().toUpperCase();
  if (t.startsWith('1Z')) return 'UPS';
  if (t.startsWith('TBA')) return 'Amazon';
  if (t.startsWith('GFUS')) return 'GOFO';
  if (t.startsWith('SPX') || t.startsWith('SPXPBI')) return 'SpeedX';
  if (RegExp(r'^(94|93|92|95)\d{18,22}$').hasMatch(t)) return 'USPS';
  if (RegExp(r'^\d{12,15}$').hasMatch(t)) return 'FedEx';
  if (RegExp(r'^\d{10}$').hasMatch(t)) return 'DHL';
  return 'Auto / Otro';
}

List<String> trackingCandidates(String text) {
  final out = <String>{};
  final lines = text.toUpperCase().split('\n');
  final patterns = <RegExp>[
    RegExp(r'\b1Z[A-Z0-9]{16}\b'),
    RegExp(r'\bTBA[A-Z0-9]{8,24}\b'),
    RegExp(r'\b(?:94|93|92|95)\d{18,22}\b'),
    RegExp(r'\b\d{12,22}\b'),
    RegExp(r'\b[A-Z]{2}\d{9}[A-Z]{2}\b'),
  ];
  for (final raw in lines) {
    final line = raw.replaceAll(RegExp(r'[^A-Z0-9\s-]'), ' ');
    final compact = line.replaceAll(RegExp(r'[\s-]+'), '');
    for (final source in [line, compact]) {
      for (final p in patterns) {
        for (final m in p.allMatches(source)) {
          final v = m.group(0)?.replaceAll(RegExp(r'[\s-]'), '') ?? '';
          if (v.length >= 10 && v.length <= 34) out.add(v);
        }
      }
    }
  }
  return out.toList();
}

Future<String?> readTrackingFromImage(BuildContext context) async {
  final source = await showModalBottomSheet<ImageSource>(
    context: context,
    builder: (_) => SafeArea(child: Wrap(children: [
      ListTile(leading: const Icon(Icons.camera_alt), title: const Text('Fotografiar etiqueta'), onTap: () => Navigator.pop(context, ImageSource.camera)),
      ListTile(leading: const Icon(Icons.image), title: const Text('Elegir foto / screenshot'), onTap: () => Navigator.pop(context, ImageSource.gallery)),
    ])),
  );
  if (source == null) return null;
  final x = await ImagePicker().pickImage(source: source, imageQuality: 90);
  if (x == null) return null;
  final recognizer = TextRecognizer(script: TextRecognitionScript.latin);
  try {
    final result = await recognizer.processImage(InputImage.fromFilePath(x.path));
    final candidates = trackingCandidates(result.text);
    if (candidates.isEmpty) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No pude detectar un número de rastreo. Puedes escribirlo manualmente.')));
      return null;
    }
    if (candidates.length == 1) return candidates.first;
    if (!context.mounted) return null;
    return showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Selecciona el tracking'),
        content: SizedBox(
          width: double.maxFinite,
          child: ListView(shrinkWrap: true, children: [for (final c in candidates) ListTile(title: Text(c), subtitle: Text(inferCarrier(c)), onTap: () => Navigator.pop(context, c))]),
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancelar'))],
      ),
    );
  } finally {
    recognizer.close();
  }
}

class ScannerPage extends StatefulWidget {
  const ScannerPage({super.key});
  @override
  State<ScannerPage> createState() => _ScannerPageState();
}

class _ScannerPageState extends State<ScannerPage> {
  bool done = false;
  final manual = TextEditingController();
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Escanear paquete')),
        body: Column(children: [
          Expanded(
            child: MobileScanner(onDetect: (capture) {
              if (done) return;
              for (final b in capture.barcodes) {
                final v = b.rawValue;
                if (v != null && v.trim().isNotEmpty) {
                  done = true;
                  Navigator.pop(context, v.trim());
                  break;
                }
              }
            }),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(children: [
              Row(children: [
                Expanded(child: TextField(controller: manual, decoration: const InputDecoration(labelText: 'O escribir tracking manualmente'))),
                const SizedBox(width: 8),
                IconButton.filled(onPressed: () { if (manual.text.trim().isNotEmpty) Navigator.pop(context, manual.text.trim()); }, icon: const Icon(Icons.check)),
              ]),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () async {
                    final c = await readTrackingFromImage(context);
                    if (c != null && context.mounted) Navigator.pop(context, c);
                  },
                  icon: const Icon(Icons.document_scanner),
                  label: const Text('Leer tracking impreso con OCR'),
                ),
              ),
            ]),
          ),
        ]),
      );
}

class PackageEditPage extends StatefulWidget {
  final Map<String, dynamic>? existing;
  final String? initialTracking;
  final String? initialClientId;
  const PackageEditPage({
    super.key,
    this.existing,
    this.initialTracking,
    this.initialClientId,
  });
  @override
  State<PackageEditPage> createState() => _PackageEditPageState();
}

class _PackageEditPageState extends State<PackageEditPage> {
  final tracking = TextEditingController(), weightUs = TextEditingController(), weightCu = TextEditingController(), billWeight = TextEditingController(), notes = TextEditingController();
  final gmailStore = TextEditingController(), gmailOrder = TextEditingController(), gmailStatus = TextEditingController(), gmailEta = TextEditingController();
  List<Map<String, dynamic>> clients = [], purchases = [], recipients = [];
  String? clientId, purchaseId, recipientId;
  String carrier = 'Auto / Otro', status = 'Tracking creado';
  List<String> photoPaths = [];
  List<String> emailPhotoUrls = [];
  List<Map<String, dynamic>> emailAttachmentImages = [];
  final Set<String> hiddenEmailPhotoUrls = <String>{};
  String gmailBackendUrl = '', gmailApiKey = '';
  bool loaded = false, syncing = false, gmailLoading = false;

  @override
  void initState() { super.initState(); init(); }

  Future<void> init() async {
    final r = await Future.wait([Store.list('clients'), Store.list('purchases'), Store.list('recipients'), Store.settings()]);
    clients = active(r[0]); purchases = active(r[1]); recipients = active(r[2]);
    tracking.text = '${widget.existing?['tracking'] ?? widget.initialTracking ?? ''}';
    carrier = '${widget.existing?['carrier'] ?? inferCarrier(tracking.text)}';
    status = '${widget.existing?['status'] ?? 'Tracking creado'}';
    clientId = widget.existing?['clientId']?.toString() ?? widget.initialClientId;
    purchaseId = widget.existing?['purchaseId']?.toString();
    recipientId = widget.existing?['recipientId']?.toString();
    weightUs.text = '${widget.existing?['weightUs'] ?? ''}';
    weightCu.text = '${widget.existing?['weightCu'] ?? ''}';
    billWeight.text = '${widget.existing?['billWeight'] ?? ''}';
    notes.text = '${widget.existing?['notes'] ?? ''}';
    if (widget.existing != null) photoPaths = packagePhotoPaths(widget.existing!);
    gmailStore.text = '${widget.existing?['gmailStore'] ?? widget.existing?['storeDetected'] ?? ''}';
    gmailOrder.text = '${widget.existing?['gmailOrderNumber'] ?? widget.existing?['orderNumberRelated'] ?? ''}';
    gmailStatus.text = '${widget.existing?['gmailStatus'] ?? widget.existing?['emailStatus'] ?? ''}';
    gmailEta.text = '${widget.existing?['gmailEstimatedDelivery'] ?? widget.existing?['emailEstimatedDelivery'] ?? ''}';
    emailPhotoUrls = dynList(widget.existing?['emailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();
    emailAttachmentImages = dynList(widget.existing?['emailAttachmentImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));
    gmailBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();
    gmailApiKey = await WhatsBotPurchaseSyncService.apiKey();
    if (mounted) setState(() => loaded = true);
  }

  void autoBillWeight() {
    final a = number(weightUs.text), b = number(weightCu.text);
    if (a > 0 || b > 0) billWeight.text = (a > 0 ? a : b).toStringAsFixed(2);
  }

  Future<void> openTracking() async {
    final t = Uri.encodeComponent(tracking.text.trim());
    late final Uri u;
    switch (carrier) {
      case 'UPS': u = Uri.parse('https://www.ups.com/track?tracknum=$t'); break;
      case 'FedEx': u = Uri.parse('https://www.fedex.com/fedextrack/?trknbr=$t'); break;
      case 'USPS': u = Uri.parse('https://tools.usps.com/go/TrackConfirmAction?tLabels=$t'); break;
      case 'DHL': u = Uri.parse('https://www.dhl.com/global-en/home/tracking.html?tracking-id=$t'); break;
      case 'Amazon': u = Uri.parse('https://www.amazon.com/progress-tracker/package/ref=ppx_yo_dt_b_track_package'); break;
      default: u = Uri.parse('https://www.google.com/search?q=${Uri.encodeComponent('${tracking.text} tracking')}');
    }
    await launchUrl(u, mode: LaunchMode.externalApplication);
  }

  Future<void> syncCourier() async {
    setState(() => syncing = true);
    final r = await EasyPostService.syncAll();
    if (!mounted) return;
    setState(() => syncing = false);
    final all = await Store.list('packages');
    final fresh = all.where((e) => '${e['id']}' == '${widget.existing?['id']}').firstOrNull;
    if (fresh != null && mounted) {
      status = '${fresh['status'] ?? status}';
      setState(() {});
    }
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(r.message ?? 'Revisados: ${r.checked} · Cambios: ${r.changed} · Errores: ${r.errors}')));
  }


  Future<String> _copyPackagePhoto(XFile picked) async {
    final dir = await getApplicationDocumentsDirectory();
    final lower = picked.path.toLowerCase();
    final ext = lower.endsWith('.png')
        ? 'png'
        : lower.endsWith('.webp')
            ? 'webp'
            : 'jpg';
    final target =
        '${dir.path}/package_photo_${DateTime.now().microsecondsSinceEpoch}_${photoPaths.length}.$ext';
    await File(picked.path).copy(target);
    return target;
  }

  Future<void> pickPackagePhotos() async {
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (_) => SafeArea(
        child: Wrap(children: [
          ListTile(
            leading: const Icon(Icons.camera_alt),
            title: const Text('Tomar una foto'),
            onTap: () => Navigator.pop(context, 'camera'),
          ),
          ListTile(
            leading: const Icon(Icons.collections_outlined),
            title: const Text('Elegir una o varias de la galería'),
            onTap: () => Navigator.pop(context, 'gallery'),
          ),
        ]),
      ),
    );
    if (action == null) return;
    final picker = ImagePicker();
    final added = <String>[];
    if (action == 'camera') {
      final image =
          await picker.pickImage(source: ImageSource.camera, imageQuality: 88);
      if (image != null) added.add(await _copyPackagePhoto(image));
    } else {
      final images = await picker.pickMultiImage(imageQuality: 88);
      for (final image in images) {
        added.add(await _copyPackagePhoto(image));
      }
    }
    if (!mounted || added.isEmpty) return;
    setState(() {
      for (final path in added) {
        if (!photoPaths.contains(path)) photoPaths.add(path);
      }
    });
  }

  Future<void> openPackagePhoto(String path) async {
    if (!File(path).existsSync()) return;
    await showDialog<void>(
      context: context,
      builder: (_) => Dialog(
        insetPadding: const EdgeInsets.all(12),
        child: Stack(
          children: [
            InteractiveViewer(
              minScale: 0.7,
              maxScale: 5,
              child: Image.file(File(path), fit: BoxFit.contain),
            ),
            Positioned(
              right: 4,
              top: 4,
              child: IconButton.filledTonal(
                onPressed: () => Navigator.pop(context),
                icon: const Icon(Icons.close),
              ),
            ),
          ],
        ),
      ),
    );
  }


  List<Map<String, dynamic>> _emailPhotoEntries() {
    final out = <Map<String, dynamic>>[];
    for (final raw in emailPhotoUrls) {
      final url = raw.trim();
      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url)) continue;
      out.add({'kind': 'remote', 'url': url, 'name': ''});
    }
    for (final row in emailAttachmentImages) {
      final url = '${row['url'] ?? ''}'.trim();
      if (url.isEmpty || hiddenEmailPhotoUrls.contains(url)) continue;
      if (out.any((e) => '${e['url']}' == url)) continue;
      out.add({'kind': 'attachment', 'url': url, 'name': '${row['name'] ?? ''}'});
    }
    return out;
  }

  String _fullEmailPhotoUrl(Map<String, dynamic> image) {
    final raw = '${image['url'] ?? ''}'.trim();
    if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
    final base = gmailBackendUrl.replaceAll(RegExp(r'/$'), '');
    return raw.startsWith('/') ? '$base$raw' : '$base/$raw';
  }

  Map<String, String>? _emailPhotoHeaders(Map<String, dynamic> image) {
    final raw = '${image['url'] ?? ''}'.trim();
    final isBackend = raw.startsWith('/') ||
        (gmailBackendUrl.isNotEmpty && raw.startsWith(gmailBackendUrl));
    if (!isBackend || gmailApiKey.isEmpty) return null;
    return {'x-api-key': gmailApiKey};
  }

  Future<void> reconstructFromGmail() async {
    final track = tracking.text.trim();
    final order = gmailOrder.text.trim();
    if (track.isEmpty && order.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Escribe un tracking o número de orden primero.')),
      );
      return;
    }
    gmailBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();
    gmailApiKey = await WhatsBotPurchaseSyncService.apiKey();
    if (gmailApiKey.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Falta la API key del servidor de WhatsBot en Configuración.')),
      );
      return;
    }
    setState(() => gmailLoading = true);
    try {
      final uri = Uri.parse('$gmailBackendUrl/api/gmail/reconstruct').replace(
        queryParameters: track.isNotEmpty
            ? {'tracking': track}
            : {'order_number': order},
      );
      final response = await http.get(
        uri,
        headers: {'x-api-key': gmailApiKey},
      ).timeout(const Duration(seconds: 75));
      if (response.statusCode != 200) {
        String detail = response.body;
        try {
          final decoded = jsonDecode(response.body);
          if (decoded is Map && decoded['detail'] != null) detail = '${decoded['detail']}';
        } catch (_) {}
        throw Exception(detail);
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) throw Exception('Respuesta inválida del servidor.');
      final data = Map<String, dynamic>.from(decoded);
      if (data['found'] != true) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('No encontré correos para ese tracking u orden.')),
          );
        }
        return;
      }
      if (!mounted) return;
      setState(() {
        gmailStore.text = '${data['store'] ?? ''}'.trim();
        gmailOrder.text = '${data['orderNumber'] ?? gmailOrder.text}'.trim();
        gmailStatus.text = '${data['status'] ?? ''}'.trim();
        gmailEta.text = '${data['estimatedDelivery'] ?? ''}'.trim();

        final detectedCarrier = '${data['carrier'] ?? ''}'.trim();
        if (detectedCarrier.isNotEmpty &&
            (carrier == 'Auto / Otro' || carrier.trim().isEmpty)) {
          carrier = detectedCarrier;
        }

        for (final value in dynList(data['emailPhotoUrls'])) {
          final url = '$value'.trim();
          if (url.isNotEmpty &&
              !hiddenEmailPhotoUrls.contains(url) &&
              !emailPhotoUrls.contains(url)) {
            emailPhotoUrls.add(url);
          }
        }
        for (final value in dynList(data['emailAttachmentImages'])) {
          if (value is! Map) continue;
          final row = Map<String, dynamic>.from(value);
          final url = '${row['url'] ?? ''}'.trim();
          if (url.isEmpty || hiddenEmailPhotoUrls.contains(url)) continue;
          if (!emailAttachmentImages.any((e) => '${e['url']}' == url)) {
            emailAttachmentImages.add(row);
          }
        }
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Compra reconstruida desde Gmail${gmailStore.text.isEmpty ? '' : ' · ${gmailStore.text}'}')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('No se pudo reconstruir desde Gmail: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => gmailLoading = false);
    }
  }

  Future<void> openEmailPhoto(Map<String, dynamic> image) async {
    final url = _fullEmailPhotoUrl(image);
    if (url.isEmpty) return;
    await showDialog<void>(
      context: context,
      builder: (_) => Dialog(
        insetPadding: EdgeInsets.zero,
        backgroundColor: Colors.black,
        child: SafeArea(
          child: Stack(
            children: [
              Positioned.fill(
                child: InteractiveViewer(
                  minScale: 0.7,
                  maxScale: 6,
                  child: Center(
                    child: Image.network(
                      url,
                      headers: _emailPhotoHeaders(image),
                      fit: BoxFit.contain,
                      loadingBuilder: (_, child, progress) => progress == null
                          ? child
                          : const Center(child: CircularProgressIndicator()),
                      errorBuilder: (_, __, ___) => const Center(
                        child: Icon(Icons.broken_image_outlined, size: 64),
                      ),
                    ),
                  ),
                ),
              ),
              Positioned(
                right: 8,
                top: 8,
                child: IconButton.filled(
                  tooltip: 'Cerrar',
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> removeEmailPhoto(Map<String, dynamic> image) async {
    final raw = '${image['url'] ?? ''}'.trim();
    if (raw.isEmpty) return;
    final remove = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Quitar foto'),
        content: const Text('¿Quieres quitar esta imagen de este paquete? No se borrará el correo original.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Quitar')),
        ],
      ),
    );
    if (remove != true || !mounted) return;
    setState(() {
      hiddenEmailPhotoUrls.add(raw);
      emailPhotoUrls.removeWhere((e) => e.trim() == raw);
      emailAttachmentImages.removeWhere((e) => '${e['url'] ?? ''}'.trim() == raw);
    });
  }

  Future<void> save() async {
    final code = tracking.text.trim();
    if (code.isEmpty || clientId == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Tracking y cliente son obligatorios.')));
      return;
    }
    final rows = await Store.list('packages');
    final duplicate = rows.where((e) => e['deleted'] != true && '${e['tracking']}' == code && '${e['id']}' != '${widget.existing?['id'] ?? ''}').firstOrNull;
    if (duplicate != null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Ese tracking ya existe.')));
      return;
    }
    final item = {
      'id': widget.existing?['id'] ?? newId(),
      'tracking': code,
      'carrier': carrier,
      'clientId': clientId,
      'purchaseId': purchaseId,
      'recipientId': recipientId,
      'weightUs': number(weightUs.text),
      'weightCu': number(weightCu.text),
      'billWeight': number(billWeight.text),
      'status': status,
      'notes': notes.text.trim(),
      'gmailStore': gmailStore.text.trim(),
      'gmailOrderNumber': gmailOrder.text.trim(),
      'gmailStatus': gmailStatus.text.trim(),
      'gmailEstimatedDelivery': gmailEta.text.trim(),
      'emailPhotoUrls': emailPhotoUrls,
      'emailAttachmentImages': emailAttachmentImages,
      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),
      'photoPaths': photoPaths,
      'photoPath': photoPaths.isEmpty ? '' : photoPaths.first,
      'receivedAt': status == 'Recibido' ? (widget.existing?['receivedAt'] ?? DateTime.now().toIso8601String()) : widget.existing?['receivedAt'],
      'deleted': false,
    };
    final i = rows.indexWhere((e) => e['id'] == item['id']);
    if (i >= 0) rows[i] = {...rows[i], ...item}; else rows.add(item);
    await Store.saveList('packages', rows);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    if (!loaded) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final cp = purchases.where((e) => clientId != null && purchaseHasClient(e, clientId!)).toList();
    final cr = recipients.where((e) => '${e['clientId']}' == clientId).toList();
    final remote = '${widget.existing?['courierStatusEs'] ?? ''}'.trim();
    final eta = '${widget.existing?['estimatedDelivery'] ?? ''}'.trim();
    final details = widget.existing?['courierDetails'] is List ? (widget.existing!['courierDetails'] as List).map((e) => Map<String, dynamic>.from(e as Map)).toList() : <Map<String, dynamic>>[];
    final emailImages = _emailPhotoEntries();
    return Scaffold(
      appBar: AppBar(title: Text(widget.existing == null ? 'Nuevo paquete' : 'Editar paquete'), actions: [if (tracking.text.trim().isNotEmpty) IconButton(tooltip: 'Rastrear en courier', onPressed: openTracking, icon: const Icon(Icons.local_shipping))]),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        TextField(
          controller: tracking,
          onChanged: (v) { if (widget.existing == null) setState(() => carrier = inferCarrier(v)); },
          decoration: InputDecoration(
            labelText: 'Tracking / QR / código *',
            suffixIcon: Row(mainAxisSize: MainAxisSize.min, children: [
              IconButton(icon: const Icon(Icons.document_scanner), tooltip: 'Leer texto de etiqueta', onPressed: () async {
                final c = await readTrackingFromImage(context);
                if (c != null) setState(() { tracking.text = c; carrier = inferCarrier(c); });
              }),
              IconButton(icon: const Icon(Icons.qr_code_scanner), tooltip: 'Escanear código', onPressed: () async {
                final c = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScannerPage()));
                if (c != null) setState(() { tracking.text = c; carrier = inferCarrier(c); });
              }),
            ]),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: FilledButton.tonalIcon(
            onPressed: gmailLoading ? null : reconstructFromGmail,
            icon: gmailLoading
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.manage_search),
            label: const Text('Buscar tracking en Gmail y reconstruir compra'),
          ),
        ),
        const SizedBox(height: 12),
        TextField(controller: gmailStore, decoration: const InputDecoration(labelText: 'Tienda detectada / tienda')),
        const SizedBox(height: 12),
        TextField(controller: gmailOrder, decoration: const InputDecoration(labelText: 'Número de orden relacionado')),
        const SizedBox(height: 12),
        TextField(controller: gmailStatus, decoration: const InputDecoration(labelText: 'Estado obtenido del correo')),
        const SizedBox(height: 12),
        TextField(controller: gmailEta, decoration: const InputDecoration(labelText: 'Entrega estimada obtenida del correo')),
        const SizedBox(height: 12),
        _drop('Courier / agencia', carrier, ['Auto / Otro', 'UPS', 'FedEx', 'USPS', 'DHL', 'Amazon', 'GOFO', 'SpeedX'].map((x) => DropdownMenuItem(value: x, child: Text(x))).toList(), (v) => setState(() => carrier = v ?? carrier)),
        const SizedBox(height: 12),
        _drop('Cliente *', clientId, clients.map((c) => DropdownMenuItem(value: '${c['id']}', child: Text('${c['name']}'))).toList(), (v) => setState(() { clientId = v; purchaseId = null; recipientId = null; })),
        const SizedBox(height: 12),
        _drop('Compra / pedido relacionado', purchaseId, cp.map((p) => DropdownMenuItem(value: '${p['id']}', child: Text('${p['store']} · ${p['description']}'))).toList(), (v) => setState(() => purchaseId = v)),
        const SizedBox(height: 12),
        _drop('Destinatario en Cuba', recipientId, cr.map((r) => DropdownMenuItem(value: '${r['id']}', child: Text('${r['name']} · ${r['province']}'))).toList(), (v) => setState(() => recipientId = v)),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: TextField(controller: weightUs, onChanged: (_) => autoBillWeight(), keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Peso EE. UU. (lb)'))),
          const SizedBox(width: 8),
          Expanded(child: TextField(controller: weightCu, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Peso Cuba (lb)'))),
        ]),
        const SizedBox(height: 12),
        TextField(controller: billWeight, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Peso facturado (lb)')),
        const SizedBox(height: 12),
        _drop('Estado', status, ['Tracking creado', 'En tránsito', 'Sale para entrega', 'Recibido', 'Verificado', 'Listo para Cuba', 'Asignado a viaje', 'En tránsito a Cuba', 'Llegó a Cuba', 'Entregado', 'Problema'].map((x) => DropdownMenuItem(value: x, child: Text(x))).toList(), (v) => setState(() => status = v ?? status)),
        const SizedBox(height: 12),
        TextField(controller: notes, maxLines: 3, decoration: const InputDecoration(labelText: 'Notas')),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: pickPackagePhotos,
          icon: const Icon(Icons.add_a_photo_outlined),
          label: Text(photoPaths.isEmpty ? 'Añadir foto del paquete' : 'Añadir otra foto del paquete'),
        ),
        if (photoPaths.isNotEmpty) ...[
          const SizedBox(height: 8),
          SizedBox(
            height: 82,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: photoPaths.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (_, i) {
                final path = photoPaths[i];
                return Stack(
                  children: [
                    InkWell(
                      onTap: () => openPackagePhoto(path),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: File(path).existsSync()
                            ? Image.file(File(path), width: 82, height: 82, fit: BoxFit.cover)
                            : Container(
                                width: 82,
                                height: 82,
                                alignment: Alignment.center,
                                child: const Icon(Icons.broken_image_outlined),
                              ),
                      ),
                    ),
                    Positioned(
                      right: 2,
                      top: 2,
                      child: IconButton.filledTonal(
                        visualDensity: VisualDensity.compact,
                        tooltip: 'Quitar foto',
                        onPressed: () => setState(() => photoPaths.removeAt(i)),
                        icon: const Icon(Icons.close, size: 18),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],

        if (emailImages.isNotEmpty) ...[
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(children: [
                    Icon(Icons.email_outlined, size: 19),
                    SizedBox(width: 8),
                    Text('Fotos obtenidas del correo', style: TextStyle(fontWeight: FontWeight.bold)),
                  ]),
                  const SizedBox(height: 6),
                  const Text(
                    'Se mantienen separadas de las fotos manuales de la compra. '
                    'Toca una imagen para verla en grande y usa × para quitarla.',
                    style: TextStyle(fontSize: 12),
                  ),
                  const SizedBox(height: 10),
                  GridView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 3,
                      crossAxisSpacing: 7,
                      mainAxisSpacing: 7,
                      childAspectRatio: 1,
                    ),
                    itemCount: emailImages.length,
                    itemBuilder: (_, i) {
                      final image = emailImages[i];
                      return Stack(
                        fit: StackFit.expand,
                        children: [
                          Material(
                            color: Theme.of(context).colorScheme.surfaceContainerHighest,
                            borderRadius: BorderRadius.circular(9),
                            clipBehavior: Clip.antiAlias,
                            child: InkWell(
                              onTap: () => openEmailPhoto(image),
                              child: Image.network(
                                _fullEmailPhotoUrl(image),
                                headers: _emailPhotoHeaders(image),
                                fit: BoxFit.cover,
                                loadingBuilder: (_, child, progress) => progress == null
                                    ? child
                                    : const Center(child: CircularProgressIndicator(strokeWidth: 2)),
                                errorBuilder: (_, __, ___) => const Center(
                                  child: Icon(Icons.broken_image_outlined),
                                ),
                              ),
                            ),
                          ),
                          Positioned(
                            right: 2,
                            top: 2,
                            child: IconButton.filled(
                              visualDensity: VisualDensity.compact,
                              tooltip: 'Quitar foto',
                              onPressed: () => removeEmailPhoto(image),
                              icon: const Icon(Icons.close, size: 17),
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        ],
        if (widget.existing != null && (remote.isNotEmpty || details.isNotEmpty)) ...[
          const SizedBox(height: 16),
          _sectionCard(context, 'Estado del courier', Icons.local_shipping, [
            if (remote.isNotEmpty) Text(remote, style: const TextStyle(fontWeight: FontWeight.bold)),
            if (eta.isNotEmpty && eta != 'null') Text('Entrega estimada: $eta'),
            for (final d in details.take(5)) Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('• ${d['message'] ?? d['status']} ${'${d['location'] ?? ''}'.isNotEmpty ? '· ${d['location']}' : ''}'),
            ),
          ]),
        ],
        const SizedBox(height: 14),
        if (tracking.text.trim().isNotEmpty) OutlinedButton.icon(onPressed: openTracking, icon: const Icon(Icons.open_in_new), label: const Text('Abrir tracking oficial')),
        if (widget.existing != null) ...[
          const SizedBox(height: 8),
          OutlinedButton.icon(onPressed: syncing ? null : syncCourier, icon: syncing ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.sync), label: const Text('Sincronizar con EasyPost')),
        ],
        const SizedBox(height: 8),
        FilledButton.icon(onPressed: save, icon: const Icon(Icons.save), label: const Text('Guardar paquete')),
        const SizedBox(height: 60),
      ]),
    );
  }
}
