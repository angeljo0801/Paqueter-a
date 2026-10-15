part of 'main.dart';

/// Paquetes guardan purchaseIds; purchaseId se mantiene para Gmail y WhatsBot.
class PackagePurchaseLinks {
  static List<String> ids(Map<String, dynamic> package) {
    final result = <String>[];
    for (final value in dynList(package['purchaseIds'])) {
      final id = value?.toString().trim() ?? '';
      if (id.isNotEmpty && id != 'null' && !result.contains(id)) result.add(id);
    }
    final legacy = package['purchaseId']?.toString().trim() ?? '';
    if (legacy.isNotEmpty && legacy != 'null' && !result.contains(legacy)) {
      result.add(legacy);
    }
    return result;
  }

  static Map<String, dynamic> withIds(
    Map<String, dynamic> package, Iterable<String> purchaseIds,
  ) {
    final unique = purchaseIds.where((id) => id.isNotEmpty).toSet().toList();
    return {...package, 'purchaseIds': unique,
      'purchaseId': unique.isEmpty ? null : unique.first};
  }

  static bool hasClient(Map<String, dynamic> purchase, String clientId) =>
      clientId.isNotEmpty && purchaseHasClient(purchase, clientId);

  static String description(Map<String, dynamic> purchase) {
    final kind = purchase['status'] == 'Pendiente de comprar' ? 'Pedido' : 'Compra';
    final store = (purchase['store'] ?? 'Sin tienda').toString();
    final order = purchaseOrderNumbers(purchase).join(', ');
    return '$kind · $store${order.isEmpty ? '' : ' · #$order'}';
  }

  static List<Map<String, dynamic>> forPurchase(
    List<Map<String, dynamic>> packages, String purchaseId,
  ) => active(packages).where((p) => ids(p).contains(purchaseId)).toList();

  /// null means the user cancelled the edit.
  static Future<Set<String>?> choosePurchases(
    BuildContext context, {
    required String clientId,
    required List<Map<String, dynamic>> purchases,
    required Iterable<String> selected,
  }) async {
    final chosen = selected.toSet();
    final available = active(purchases).where(
      (p) => hasClient(p, clientId) || chosen.contains('${p['id']}'),
    ).toList();
    String filter = '';
    return showModalBottomSheet<Set<String>>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, redraw) {
          final visible = available.where((p) =>
            description(p).toLowerCase().contains(filter.toLowerCase()) ||
            (p['description'] ?? '').toString().toLowerCase().contains(filter.toLowerCase()),
          ).toList();
          return SafeArea(
            child: SizedBox(
              height: MediaQuery.sizeOf(sheetContext).height * .75,
              child: Column(children: [
                const Padding(
                  padding: EdgeInsets.all(12),
                  child: Text('Vincular compras y pedidos',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: TextField(
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search),
                      labelText: 'Buscar tienda, número o descripción',
                    ),
                    onChanged: (v) => redraw(() => filter = v),
                  ),
                ),
                const SizedBox(height: 8),
                Expanded(
                  child: available.isEmpty
                    ? const Center(child: Text('No hay compras o pedidos asociados a este cliente.'))
                    : ListView.builder(
                        itemCount: visible.length,
                        itemBuilder: (_, index) {
                          final p = visible[index];
                          final id = '${p['id']}';
                          return CheckboxListTile(
                            value: chosen.contains(id),
                            title: Text(description(p)),
                            subtitle: Text('${p['description'] ?? ''}'),
                            onChanged: (checked) => redraw(() {
                              if (checked == true) { chosen.add(id); }
                              else { chosen.remove(id); }
                            }),
                          );
                        },
                      ),
                ),
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(children: [
                    Expanded(child: OutlinedButton(
                      onPressed: () => Navigator.pop(sheetContext),
                      child: const Text('Cancelar'),
                    )),
                    const SizedBox(width: 12),
                    Expanded(child: FilledButton(
                      onPressed: () => Navigator.pop(sheetContext, chosen),
                      child: Text('Guardar (${chosen.length})'),
                    )),
                  ]),
                ),
              ]),
            ),
          );
        },
      ),
    );
  }

  /// Desde compra/pedido se cambian vínculos sin modificar otros datos.
  static Future<bool> choosePackagesForPurchase(
    BuildContext context, Map<String, dynamic> purchase,
  ) async {
    final purchaseId = '${purchase['id']}';
    final original = await Store.list('packages');
    final selected = forPurchase(original, purchaseId)
        .map((p) => '${p['id']}').toSet();
    final eligible = active(original).where((p) =>
      hasClient(purchase, (p['clientId'] ?? '').toString()) ||
      selected.contains('${p['id']}'),
    ).toList();
    if (!context.mounted) return false;
    if (eligible.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Primero asocia este pedido o compra a un cliente con paquetes.'),
      ));
      return false;
    }
    String filter = '';
    final result = await showModalBottomSheet<Set<String>>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, redraw) {
          final visible = eligible.where((p) =>
            '${p['tracking']} ${p['carrier']}'
              .toLowerCase().contains(filter.toLowerCase()),
          ).toList();
          return SafeArea(child: SizedBox(
            height: MediaQuery.sizeOf(sheetContext).height * .75,
            child: Column(children: [
              const Padding(
                padding: EdgeInsets.all(12),
                child: Text('Paquetes vinculados',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: TextField(
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search),
                    labelText: 'Buscar tracking o transportista',
                  ),
                  onChanged: (value) => redraw(() => filter = value),
                ),
              ),
              Expanded(child: ListView.builder(
                itemCount: visible.length,
                itemBuilder: (_, i) {
                  final p = visible[i];
                  final id = '${p['id']}';
                  return CheckboxListTile(
                    value: selected.contains(id),
                    title: Text((p['tracking'] ?? '').toString()),
                    subtitle: Text('${p['carrier'] ?? ''} · ${p['status'] ?? ''}'),
                    onChanged: (checked) => redraw(() {
                      if (checked == true) { selected.add(id); }
                      else { selected.remove(id); }
                    }),
                  );
                },
              )),
              Padding(padding: const EdgeInsets.all(12),
                child: Row(children: [
                  Expanded(child: OutlinedButton(
                    onPressed: () => Navigator.pop(sheetContext),
                    child: const Text('Cancelar'),
                  )),
                  const SizedBox(width: 12),
                  Expanded(child: FilledButton(
                    onPressed: () => Navigator.pop(sheetContext, selected),
                    child: Text('Guardar (${selected.length})'),
                  )),
                ]),
              ),
            ]),
          ));
        },
      ),
    );
    if (result == null) return false;

    // Lectura actualizada: no tocar tracking, fotos ni estado por accidente.
    final latest = await Store.list('packages');
    final eligibleIds = eligible.map((p) => '${p['id']}').toSet();
    bool changed = false;
    for (var i = 0; i < latest.length; i++) {
      final p = latest[i];
      if (p['deleted'] == true || !eligibleIds.contains('${p['id']}')) continue;
      final oldIds = ids(p);
      final next = oldIds.toSet();
      if (result.contains('${p['id']}')) { next.add(purchaseId); }
      else { next.remove(purchaseId); }
      if (next.length != oldIds.length || !next.containsAll(oldIds)) {
        latest[i] = withIds(p, next);
        changed = true;
      }
    }
    if (changed) await Store.saveList('packages', latest);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(changed ? 'Vínculos actualizados.' : 'Sin cambios en los vínculos.'),
      ));
    }
    return changed;
  }
}
