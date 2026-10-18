from pathlib import Path

# v76: Package rows in Trash now present the same data/badges/thumbnail as
# the active Packages dashboard. Tapping a deleted package opens read-only
# details, never the editor (which might otherwise undo the deletion).
# The existing Restore/Delete/Empty Trash operations remain intact.
p = Path('app/lib/extras.dart')
s = p.read_text()
start = s.index('class _TrashPageState extends State<TrashPage> {')
end = s.index('\nclass MorePage extends StatelessWidget', start)
segment = s[start:end]

old = '''  List<Map<String, dynamic>> deleted = [];
  bool busy = false;'''
new = '''  List<Map<String, dynamic>> deleted = [];
  List<Map<String, dynamic>> clients = [];
  bool busy = false;'''
assert segment.count(old) == 1, 'v76: Trash data fields moved'
segment = segment.replace(old, new, 1)

old = '''    if (mounted) setState(() => deleted = out);'''
new = '''    // Include even deleted clients: a trashed package must keep showing its
    // original client name, not "Sin cliente".
    final allClients = await Store.list('clients', forceRefresh: true);
    if (mounted) setState(() {
      deleted = out;
      clients = allClients;
    });'''
assert segment.count(old) == 1, 'v76: Trash load changed'
segment = segment.replace(old, new, 1)

anchor = '  @override\n  Widget build(BuildContext context) => Scaffold('
assert segment.count(anchor) == 1, 'v76: Trash build anchor changed'
methods = r'''  Widget _packageTrashTile(Map<String, dynamic> row) {
    final photoPaths = packagePhotoPaths(row)
        .where((path) => File(path).existsSync())
        .toList();
    final remoteStatus = (row['courierStatusEs'] ?? '').toString().trim();
    final status = remoteStatus.isNotEmpty
        ? remoteStatus : (row['status'] ?? '').toString();
    final tracking = (row['tracking'] ?? '').toString();
    final carrier = (row['carrier'] ?? '').toString();
    final customer = clientName(clients, (row['clientId'] ?? '').toString());

    return ListTile(
      leading: photoPaths.isEmpty
          ? const Icon(Icons.inventory_2)
          : ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.file(
                File(photoPaths.first),
                width: 52,
                height: 52,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) =>
                    const Icon(Icons.inventory_2),
              ),
            ),
      title: Row(
        children: [
          Expanded(
            child: Text(tracking, overflow: TextOverflow.ellipsis),
          ),
          if ((row['status'] ?? '').toString() == 'Completed') ...[
            const SizedBox(width: 8),
            packageCompletedBadge(context),
          ],
          if (gmailRecordNotFound(row)) ...[
            const SizedBox(width: 8),
            gmailNotFoundBadge(context),
          ] else if (gmailRecordIsLinked(row)) ...[
            const SizedBox(width: 8),
            gmailLinkedBadge(context),
          ],
        ],
      ),
      subtitle: Text(
        customer + ' · ' + carrier + '\n' +
        status + ' · ' + number(row['billWeight']).toStringAsFixed(1) + ' lb',
      ),
      isThreeLine: true,
      onTap: () => _showTrashedPackageDetails(row),
      trailing: PopupMenuButton<String>(
        tooltip: 'Opciones del paquete eliminado',
        onSelected: (value) {
          if (value == 'restore') {
            restore(row);
          } else if (value == 'delete') {
            permanent(row);
          }
        },
        itemBuilder: (_) => const [
          PopupMenuItem(
            value: 'restore',
            child: Text('Restaurar'),
          ),
          PopupMenuItem(
            value: 'delete',
            child: Text('Eliminar definitivamente'),
          ),
        ],
      ),
    );
  }

  void _showTrashedPackageDetails(Map<String, dynamic> row) {
    final photos = packagePhotoPaths(row)
        .where((path) => File(path).existsSync())
        .toList();
    final remoteStatus = (row['courierStatusEs'] ?? '').toString().trim();
    final status = remoteStatus.isNotEmpty
        ? remoteStatus : (row['status'] ?? '').toString();

    Widget detail(String name, dynamic value) {
      final result = (value ?? '').toString().trim();
      if (result.isEmpty) return const SizedBox.shrink();
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 112,
              child: Text(
                name,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
            Expanded(child: SelectableText(result)),
          ],
        ),
      );
    }

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: FractionallySizedBox(
          heightFactor: .82,
          child: ListView(
            padding: const EdgeInsets.symmetric(
                horizontal: 20, vertical: 8),
            children: [
              Text(
                'Detalles del paquete',
                style: Theme.of(sheetContext).textTheme.titleLarge,
              ),
              const SizedBox(height: 6),
              const Text(
                'Solo lectura. Restaura el paquete desde la papelera '
                'para poder editarlo.',
              ),
              const SizedBox(height: 12),
              if (photos.isNotEmpty)
                SizedBox(
                  height: 135,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: photos.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 8),
                    itemBuilder: (_, i) => ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: Image.file(
                        File(photos[i]),
                        width: 130,
                        height: 130,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => const Icon(
                          Icons.broken_image_outlined, size: 48),
                      ),
                    ),
                  ),
                ),
              detail('Tracking', row['tracking']),
              detail('Cliente',
                  clientName(clients, (row['clientId'] ?? '').toString())),
              detail('Transportista', row['carrier']),
              detail('Estado', status),
              detail('Peso facturado',
                  number(row['billWeight']).toStringAsFixed(1) + ' lb'),
              detail('Peso EE. UU.',
                  number(row['weightUs']).toStringAsFixed(1) + ' lb'),
              detail('Peso Cuba',
                  number(row['weightCu']).toStringAsFixed(1) + ' lb'),
              detail('Pedido Gmail', row['gmailOrderNumber']),
              detail('Tienda Gmail', row['gmailStore']),
              detail('Estado Gmail', row['gmailStatus']),
              detail('Entrega estimada', row['gmailEstimatedDelivery']),
              detail('Compra vinculada', row['purchaseId']),
              detail('Destinatario', row['recipientId']),
              detail('Recibido', row['receivedAt']),
              detail('Eliminado', row['deletedAt']),
              detail('Notas', row['notes']),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: () => Navigator.pop(sheetContext),
                icon: const Icon(Icons.close),
                label: const Text('Cerrar'),
              ),
            ],
          ),
        ),
      ),
    );
  }

'''
segment = segment.replace(anchor, methods + anchor, 1)

old = '''              final row = deleted[i];
              return ListTile('''
new = '''              final row = deleted[i];
              if (row['_key'] == 'packages') {
                return _packageTrashTile(row);
              }
              return ListTile('''
assert segment.count(old) == 1, 'v76: Trash row rendering changed'
segment = segment.replace(old,new,1)
assert 'Vaciar definitivamente' in segment
assert 'PackageDeletionLedger.remember' in segment
assert 'gmailRecordNotFound(row)' in segment
assert 'packageCompletedBadge(context)' in segment
s=s[:start]+segment+s[end:]
p.write_text(s)
print('v76: Trash package tiles match active list data, badges and thumbnails; details are read-only.')
