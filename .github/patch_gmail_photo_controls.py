from pathlib import Path

p = Path('paqueteria/lib/packages.dart')
s = p.read_text()


def repl(old: str, new: str, label: str) -> None:
    global s
    if old not in s:
        raise SystemExit(f'Anchor not found: {label}')
    s = s.replace(old, new, 1)


# Preserve the couriers that are already visible in the Gmail-enabled APK.
repl(
    "  if (t.startsWith('TBA')) return 'Amazon';\n",
    "  if (t.startsWith('TBA')) return 'Amazon';\n"
    "  if (t.startsWith('GFUS')) return 'GOFO';\n"
    "  if (t.startsWith('SPX') || t.startsWith('SPXPBI')) return 'SpeedX';\n",
    'carrier inference',
)

# Gmail reconstruction state.  Manual package photos remain in photoPaths and
# Gmail images remain in their own lists, exactly as the UI explains.
repl(
    "  final tracking = TextEditingController(), weightUs = TextEditingController(), weightCu = TextEditingController(), billWeight = TextEditingController(), notes = TextEditingController();\n",
    "  final tracking = TextEditingController(), weightUs = TextEditingController(), weightCu = TextEditingController(), billWeight = TextEditingController(), notes = TextEditingController();\n"
    "  final gmailStore = TextEditingController(), gmailOrder = TextEditingController(), gmailStatus = TextEditingController(), gmailEta = TextEditingController();\n",
    'gmail controllers',
)

repl(
    "  List<String> photoPaths = [];\n  bool loaded = false, syncing = false;\n",
    "  List<String> photoPaths = [];\n"
    "  List<String> emailPhotoUrls = [];\n"
    "  List<Map<String, dynamic>> emailAttachmentImages = [];\n"
    "  final Set<String> hiddenEmailPhotoUrls = <String>{};\n"
    "  String gmailBackendUrl = '', gmailApiKey = '';\n"
    "  bool loaded = false, syncing = false, gmailLoading = false;\n",
    'gmail photo state',
)

repl(
    "    notes.text = '${widget.existing?['notes'] ?? ''}';\n    if (widget.existing != null) photoPaths = packagePhotoPaths(widget.existing!);\n    if (mounted) setState(() => loaded = true);\n",
    "    notes.text = '${widget.existing?['notes'] ?? ''}';\n"
    "    if (widget.existing != null) photoPaths = packagePhotoPaths(widget.existing!);\n"
    "    gmailStore.text = '${widget.existing?['gmailStore'] ?? widget.existing?['storeDetected'] ?? ''}';\n"
    "    gmailOrder.text = '${widget.existing?['gmailOrderNumber'] ?? widget.existing?['orderNumberRelated'] ?? ''}';\n"
    "    gmailStatus.text = '${widget.existing?['gmailStatus'] ?? widget.existing?['emailStatus'] ?? ''}';\n"
    "    gmailEta.text = '${widget.existing?['gmailEstimatedDelivery'] ?? widget.existing?['emailEstimatedDelivery'] ?? ''}';\n"
    "    emailPhotoUrls = dynList(widget.existing?['emailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty).toList();\n"
    "    emailAttachmentImages = dynList(widget.existing?['emailAttachmentImages']).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();\n"
    "    hiddenEmailPhotoUrls.addAll(dynList(widget.existing?['hiddenEmailPhotoUrls']).map((e) => '$e'.trim()).where((e) => e.isNotEmpty));\n"
    "    gmailBackendUrl = await WhatsBotPurchaseSyncService.backendUrl();\n"
    "    gmailApiKey = await WhatsBotPurchaseSyncService.apiKey();\n"
    "    if (mounted) setState(() => loaded = true);\n",
    'gmail init',
)

methods = r'''
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

'''
repl(
    "  Future<void> save() async {\n",
    methods + "  Future<void> save() async {\n",
    'gmail methods',
)

repl(
    "      'notes': notes.text.trim(),\n      'photoPaths': photoPaths,\n",
    "      'notes': notes.text.trim(),\n"
    "      'gmailStore': gmailStore.text.trim(),\n"
    "      'gmailOrderNumber': gmailOrder.text.trim(),\n"
    "      'gmailStatus': gmailStatus.text.trim(),\n"
    "      'gmailEstimatedDelivery': gmailEta.text.trim(),\n"
    "      'emailPhotoUrls': emailPhotoUrls,\n"
    "      'emailAttachmentImages': emailAttachmentImages,\n"
    "      'hiddenEmailPhotoUrls': hiddenEmailPhotoUrls.toList(),\n"
    "      'photoPaths': photoPaths,\n",
    'gmail saved fields',
)

repl(
    "    final details = widget.existing?['courierDetails'] is List ? (widget.existing!['courierDetails'] as List).map((e) => Map<String, dynamic>.from(e as Map)).toList() : <Map<String, dynamic>>[];\n",
    "    final details = widget.existing?['courierDetails'] is List ? (widget.existing!['courierDetails'] as List).map((e) => Map<String, dynamic>.from(e as Map)).toList() : <Map<String, dynamic>>[];\n"
    "    final emailImages = _emailPhotoEntries();\n",
    'email images build list',
)

# Reinsert the Gmail reconstruction controls in the canonical source so the
# release build cannot lose them again.
repl(
    "        const SizedBox(height: 12),\n        _drop('Courier', carrier, ['Auto / Otro', 'UPS', 'FedEx', 'USPS', 'DHL', 'Amazon'].map((x) => DropdownMenuItem(value: x, child: Text(x))).toList(), (v) => setState(() => carrier = v ?? carrier)),\n",
    "        const SizedBox(height: 12),\n"
    "        SizedBox(\n"
    "          width: double.infinity,\n"
    "          child: FilledButton.tonalIcon(\n"
    "            onPressed: gmailLoading ? null : reconstructFromGmail,\n"
    "            icon: gmailLoading\n"
    "                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))\n"
    "                : const Icon(Icons.manage_search),\n"
    "            label: const Text('Buscar tracking en Gmail y reconstruir compra'),\n"
    "          ),\n"
    "        ),\n"
    "        const SizedBox(height: 12),\n"
    "        TextField(controller: gmailStore, decoration: const InputDecoration(labelText: 'Tienda detectada / tienda')),\n"
    "        const SizedBox(height: 12),\n"
    "        TextField(controller: gmailOrder, decoration: const InputDecoration(labelText: 'Número de orden relacionado')),\n"
    "        const SizedBox(height: 12),\n"
    "        TextField(controller: gmailStatus, decoration: const InputDecoration(labelText: 'Estado obtenido del correo')),\n"
    "        const SizedBox(height: 12),\n"
    "        TextField(controller: gmailEta, decoration: const InputDecoration(labelText: 'Entrega estimada obtenida del correo')),\n"
    "        const SizedBox(height: 12),\n"
    "        _drop('Courier / agencia', carrier, ['Auto / Otro', 'UPS', 'FedEx', 'USPS', 'DHL', 'Amazon', 'GOFO', 'SpeedX'].map((x) => DropdownMenuItem(value: x, child: Text(x))).toList(), (v) => setState(() => carrier = v ?? carrier)),\n",
    'gmail controls ui',
)

# Make the manual-photo action impossible to miss and keep it separate from
# pictures reconstructed from email.
repl(
    "          label: Text(photoPaths.isEmpty ? 'Añadir fotos del paquete' : 'Añadir más fotos'),\n",
    "          label: Text(photoPaths.isEmpty ? 'Añadir foto del paquete' : 'Añadir otra foto del paquete'),\n",
    'manual photo label',
)

email_ui = r'''
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
'''

repl(
    "        if (widget.existing != null && (remote.isNotEmpty || details.isNotEmpty)) ...[\n",
    email_ui + "        if (widget.existing != null && (remote.isNotEmpty || details.isNotEmpty)) ...[\n",
    'email photo gallery ui',
)

p.write_text(s)
print('Patched paqueteria/lib/packages.dart with Gmail photo controls')
