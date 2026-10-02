from pathlib import Path

purchases = Path('app/lib/purchases.dart')
pus = purchases.read_text()

photo_helper = """String purchasePhotoPath(Map<String, dynamic> purchase) {
  final photos = purchasePhotoPaths(purchase);
  return photos.isEmpty ? '' : photos.first;
}
"""
order_helpers = """String purchasePhotoPath(Map<String, dynamic> purchase) {
  final photos = purchasePhotoPaths(purchase);
  return photos.isEmpty ? '' : photos.first;
}

List<String> purchaseOrderNumbers(Map<String, dynamic> purchase) {
  final out = <String>[];
  void add(dynamic raw) {
    if (raw == null) return;
    if (raw is List) {
      for (final value in raw) {
        add(value);
      }
      return;
    }
    for (final part in '$raw'.split(RegExp(r'[\\n|;]+'))) {
      final value = part.trim();
      if (value.isNotEmpty && !out.contains(value)) out.add(value);
    }
  }
  add(purchase['orderNumbers']);
  add(purchase['orderNumber']);
  return out;
}

String purchaseOrderNumbersText(Map<String, dynamic> purchase) =>
    purchaseOrderNumbers(purchase).join(' · ');
"""
if 'List<String> purchaseOrderNumbers(' not in pus:
    if photo_helper not in pus:
        raise SystemExit('purchasePhotoPath helper not found')
    pus = pus.replace(photo_helper, order_helpers, 1)

pus = pus.replace("        p['orderNumber'],", "        purchaseOrderNumbers(p).join(' '),", 1)

pus = pus.replace(
    "  List<String> photoPaths = [];\n  bool loaded = false;",
    "  List<String> photoPaths = [];\n  List<String> orderNumbers = [];\n  bool loaded = false;",
    1,
)

pus = pus.replace(
    "      order.text = '${widget.existing!['orderNumber'] ?? ''}';",
    "      orderNumbers = purchaseOrderNumbers(widget.existing!);",
    1,
)

pus = pus.replace(
    "      if (order.text.trim().isEmpty && r.orderNumber.isNotEmpty) order.text = r.orderNumber;",
    "      if (r.orderNumber.isNotEmpty) {\n        for (final value in purchaseOrderNumbers({'orderNumber': r.orderNumber})) {\n          if (!orderNumbers.contains(value)) orderNumbers.add(value);\n        }\n      }",
    1,
)

pus = pus.replace(
    "    var learnedCorrections = 0;\n    if (ocrText.trim().isNotEmpty && ocrMeta.isNotEmpty) {",
    "    final currentOrderNumbers = purchaseOrderNumbers({\n      'orderNumbers': orderNumbers,\n      'orderNumber': order.text,\n    });\n    var learnedCorrections = 0;\n    if (ocrText.trim().isNotEmpty && ocrMeta.isNotEmpty) {",
    1,
)

pus = pus.replace(
    "        correctedOrderNumber: order.text.trim(),",
    "        correctedOrderNumber: currentOrderNumbers.isEmpty ? '' : currentOrderNumbers.first,",
    1,
)

pus = pus.replace(
    "      'orderNumber': order.text.trim(),",
    "      'orderNumbers': currentOrderNumbers,\n      'orderNumber': currentOrderNumbers.isEmpty ? '' : currentOrderNumbers.first,",
    1,
)

old_field = "        TextField(controller: order, decoration: const InputDecoration(labelText: 'Número de pedido (opcional)'))," 
new_field = """        if (orderNumbers.isNotEmpty) ...[
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final value in orderNumbers)
                InputChip(
                  label: Text(value),
                  onDeleted: () => setState(() => orderNumbers.remove(value)),
                ),
            ],
          ),
          const SizedBox(height: 8),
        ],
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: order,
                decoration: const InputDecoration(
                  labelText: 'Número de pedido / paquete (opcional)',
                  hintText: 'Añade uno y toca +',
                ),
                onSubmitted: (_) {
                  final values = purchaseOrderNumbers({'orderNumber': order.text});
                  if (values.isEmpty) return;
                  setState(() {
                    for (final value in values) {
                      if (!orderNumbers.contains(value)) orderNumbers.add(value);
                    }
                    order.clear();
                  });
                },
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filledTonal(
              tooltip: 'Añadir otro número',
              onPressed: () {
                final values = purchaseOrderNumbers({'orderNumber': order.text});
                if (values.isEmpty) return;
                setState(() {
                  for (final value in values) {
                    if (!orderNumbers.contains(value)) orderNumbers.add(value);
                  }
                  order.clear();
                });
              },
              icon: const Icon(Icons.add),
            ),
          ],
        ),"""
if old_field not in pus:
    raise SystemExit('order number field not found')
pus = pus.replace(old_field, new_field, 1)

purchases.write_text(pus)

bulletins = Path('app/lib/bulletins.dart')
bs = bulletins.read_text()
bs = bs.replace(
    "          if ('${purchase['orderNumber'] ?? ''}'.trim().isNotEmpty) pw.Text('Pedido: ${purchase['orderNumber']}'),",
    "          if (purchaseOrderNumbers(purchase).isNotEmpty) pw.Text('Pedidos: ${purchaseOrderNumbers(purchase).join(', ')}'),",
    1,
)
bulletins.write_text(bs)

sync = Path('app/lib/whatsbot_sync.dart')
ss = sync.read_text()
ss = ss.replace(
    "        'orderNumber': (purchase['orderNumber'] ?? '').toString(),",
    "        'orderNumbers': purchaseOrderNumbers(purchase),",
    1,
)
ss = ss.replace(
    "        'order_number': (purchase['orderNumber'] ?? '').toString(),",
    "        'order_number': purchaseOrderNumbers(purchase).join(' | '),",
    1,
)
sync.write_text(ss)
