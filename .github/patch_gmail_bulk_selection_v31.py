from pathlib import Path


def r1(s, a, b, label):
    if a not in s:
        raise SystemExit('Missing ' + label)
    return s.replace(a, b, 1)


bg = Path('app/lib/background_sync.dart')
s = bg.read_text()

s = r1(
    s,
    "  static Future<Map<String,dynamic>> start() async {\n",
    "  static Future<Map<String,dynamic>> start({\n"
    "    Iterable<String>? packageIds,\n"
    "    String scopeLabel = 'Todos los paquetes',\n"
    "  }) async {\n",
    'bulk start signature',
)

s = r1(
    s,
    "    final ps=active(await Store.list('packages',forceRefresh:true));\n"
    "    final q=<Map<String,dynamic>>[]; var skipped=0;\n"
    "    for(final p in ps){\n"
    "      final t='${p['tracking'] ?? ''}'.trim();\n",
    "    final ps=active(await Store.list('packages',forceRefresh:true));\n"
    "    final wanted = packageIds == null\n"
    "        ? null\n"
    "        : packageIds.map((e) => e.trim()).where((e) => e.isNotEmpty).toSet();\n"
    "    final q=<Map<String,dynamic>>[]; var skipped=0;\n"
    "    for(final p in ps){\n"
    "      final id='${p['id'] ?? ''}'.trim();\n"
    "      if(wanted != null && !wanted.contains(id)) continue;\n"
    "      final t='${p['tracking'] ?? ''}'.trim();\n",
    'bulk selected scope filter',
)

s = r1(
    s,
    "      q.add({'id':'${p['id'] ?? ''}','tracking':t,'clientId':'${p['clientId'] ?? ''}','order':'${p['gmailOrderNumber'] ?? ''}'});\n",
    "      q.add({'id':id,'tracking':t,'clientId':'${p['clientId'] ?? ''}','order':'${p['gmailOrderNumber'] ?? ''}'});\n",
    'bulk selected id queue',
)

s = r1(
    s,
    "      'token':token,'status':q.isEmpty?'completed':'waiting','queue':q,'total':q.length,\n",
    "      'token':token,'status':q.isEmpty?'completed':'waiting','queue':q,'total':q.length,\n"
    "      'scopeLabel':scopeLabel,\n",
    'bulk scope label',
)
bg.write_text(s)


p = Path('app/lib/packages.dart')
s = p.read_text()

s = r1(
    s,
    "  String _bulkStamp='';\n",
    "  String _bulkStamp='';\n"
    "  bool packageSelectionMode=false;\n"
    "  final Set<String> selectedPackageIds=<String>{};\n",
    'package selection fields',
)

s = r1(
    s,
    "  Future<void> _startBulk() async {\n"
    "    try {\n"
    "      final st=await GmailBulkPackageScan.start();\n",
    "  Future<void> _startBulk({\n"
    "    Iterable<String>? packageIds,\n"
    "    String scopeLabel='Todos los paquetes',\n"
    "  }) async {\n"
    "    try {\n"
    "      final st=await GmailBulkPackageScan.start(\n"
    "        packageIds:packageIds,\n"
    "        scopeLabel:scopeLabel,\n"
    "      );\n",
    'package scoped bulk helper',
)

helpers_anchor = "  Future<void> _cancelBulk() async {\n"
helpers = r'''  void _togglePackageSelection(Map<String,dynamic> p){
    final id='${p['id'] ?? ''}'.trim();
    if(id.isEmpty) return;
    setState((){
      packageSelectionMode=true;
      if(!selectedPackageIds.add(id)) selectedPackageIds.remove(id);
    });
  }

  void _toggleSelectAll(List<Map<String,dynamic>> visible){
    final ids=visible.map((e)=>'${e['id'] ?? ''}'.trim()).where((e)=>e.isNotEmpty).toSet();
    setState((){
      packageSelectionMode=true;
      final allSelected=ids.isNotEmpty && ids.every(selectedPackageIds.contains);
      if(allSelected){
        selectedPackageIds.removeAll(ids);
      }else{
        selectedPackageIds.addAll(ids);
      }
    });
  }

  Future<void> _searchSelectedInGmail() async {
    final ids=selectedPackageIds.toList();
    if(ids.isEmpty) return;
    setState((){
      packageSelectionMode=false;
      selectedPackageIds.clear();
    });
    await _startBulk(
      packageIds:ids,
      scopeLabel:'${ids.length} paquete(s) seleccionados',
    );
  }

  Future<void> _deleteSelectedPackages() async {
    final ids=selectedPackageIds.toList();
    if(ids.isEmpty) return;
    final ok=await confirmDelete(
      context,
      ids.length==1?'este paquete':'estos ${ids.length} paquetes',
    );
    if(!ok) return;
    for(final id in ids){
      await softDelete('packages',id);
    }
    if(!mounted) return;
    setState((){
      packageSelectionMode=false;
      selectedPackageIds.clear();
    });
    await load(forceRefresh:true);
    if(mounted){
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content:Text('${ids.length} paquete(s) enviados a Papelera.')),
      );
    }
  }

  Widget _packageSelectionBar(){
    final count=selectedPackageIds.length;
    return Material(
      elevation:10,
      child:SafeArea(
        top:false,
        child:Padding(
          padding:const EdgeInsets.symmetric(horizontal:10,vertical:8),
          child:Row(children:[
            Expanded(
              child:FilledButton.icon(
                onPressed:count==0?null:_searchSelectedInGmail,
                icon:const Icon(Icons.manage_search),
                label:Text('Gmail ($count)'),
              ),
            ),
            const SizedBox(width:8),
            Expanded(
              child:OutlinedButton.icon(
                onPressed:count==0?null:_deleteSelectedPackages,
                icon:const Icon(Icons.delete_outline),
                label:Text('Borrar ($count)'),
              ),
            ),
          ]),
        ),
      ),
    );
  }

'''
s = r1(s, helpers_anchor, helpers + helpers_anchor, 'package selection helpers')

s = r1(
    s,
    "        title: const Text('Paquetes'),\n"
    "        actions: [\n"
    "          _bulkButton(),\n",
    "        title: packageSelectionMode\n"
    "            ? Text('${selectedPackageIds.length} seleccionados')\n"
    "            : const Text('Paquetes'),\n"
    "        actions: [\n"
    "          if(packageSelectionMode)\n"
    "            IconButton(\n"
    "              tooltip:'Seleccionar todos los visibles',\n"
    "              onPressed:()=>_toggleSelectAll(f),\n"
    "              icon:const Icon(Icons.select_all),\n"
    "            ),\n"
    "          IconButton(\n"
    "            tooltip:packageSelectionMode?'Salir de selección':'Seleccionar paquetes',\n"
    "            onPressed:()=>setState((){\n"
    "              packageSelectionMode=!packageSelectionMode;\n"
    "              if(!packageSelectionMode) selectedPackageIds.clear();\n"
    "            }),\n"
    "            icon:Icon(packageSelectionMode?Icons.close:Icons.checklist),\n"
    "          ),\n"
    "          if(!packageSelectionMode) _bulkButton(),\n",
    'package selection appbar',
)

leading_old = r'''                      leading: Builder(builder: (_) {
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
'''
leading_new = r'''                      leading: packageSelectionMode
                          ? Checkbox(
                              value:selectedPackageIds.contains('${p['id'] ?? ''}'),
                              onChanged:(_)=>_togglePackageSelection(p),
                            )
                          : Builder(builder: (_) {
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
'''
s = r1(s, leading_old, leading_new, 'package selection checkbox')

s = r1(
    s,
    "                      onTap: () async { await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(existing: p))); load(); },\n"
    "                      trailing: IconButton(icon: const Icon(Icons.delete_outline), onPressed: () async { if (await confirmDelete(context, 'este paquete')) { await softDelete('packages', '${p['id']}'); load(); } }),\n",
    "                      onTap: () async {\n"
    "                        if(packageSelectionMode){\n"
    "                          _togglePackageSelection(p);\n"
    "                          return;\n"
    "                        }\n"
    "                        await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(existing: p)));\n"
    "                        load(forceRefresh:true);\n"
    "                      },\n"
    "                      onLongPress:()=>_togglePackageSelection(p),\n"
    "                      trailing: packageSelectionMode\n"
    "                          ? null\n"
    "                          : IconButton(icon: const Icon(Icons.delete_outline), onPressed: () async { if (await confirmDelete(context, 'este paquete')) { await softDelete('packages', '${p['id']}'); load(forceRefresh:true); } }),\n",
    'package selection tap delete',
)

s = r1(
    s,
    "      floatingActionButton: FloatingActionButton.extended(\n",
    "      bottomNavigationBar: packageSelectionMode ? _packageSelectionBar() : null,\n"
    "      floatingActionButton: packageSelectionMode ? null : FloatingActionButton.extended(\n",
    'package selection bottom bar',
)

p.write_text(s)


cpath = Path('app/lib/clients.dart')
cs = cpath.read_text()

client_method_anchor = "  Future<void> editRecipient([Map<String, dynamic>? existing]) async {\n"
client_method = r'''  Future<void> _searchAllClientPackagesInGmail() async {
    final ids=packages
        .map((e)=>'${e['id'] ?? ''}'.trim())
        .where((e)=>e.isNotEmpty)
        .toList();
    if(ids.isEmpty){
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content:Text('Este cliente no tiene paquetes para buscar.')),
      );
      return;
    }
    try{
      final name='${client?['name'] ?? 'Cliente'}'.trim();
      final st=await GmailBulkPackageScan.start(
        packageIds:ids,
        scopeLabel:'Paquetes de $name',
      );
      if(!mounted) return;
      final n=(st['total'] as num?)?.toInt()??0;
      final sk=(st['skipped'] as num?)?.toInt()??0;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content:Text(
          n==0
              ? 'No hay paquetes pendientes. $sk ya tienen Gmail y fotos.'
              : 'Búsqueda Gmail iniciada para $n paquete(s) de $name. $sk omitido(s).',
        )),
      );
    }catch(e){
      if(mounted){
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content:Text('$e'.replaceFirst('Exception: ',''))),
        );
      }
    }
  }

'''
cs = r1(cs, client_method_anchor, client_method + client_method_anchor, 'client bulk Gmail method')

new_package_anchor = r'''              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: createPackage,
                  icon: const Icon(Icons.add),
                  label: const Text('Nuevo paquete'),
                ),
              ),
'''
new_package_new = r'''              Align(
                alignment: Alignment.centerLeft,
                child: Wrap(
                  spacing:8,
                  runSpacing:4,
                  children:[
                    TextButton.icon(
                      onPressed: createPackage,
                      icon: const Icon(Icons.add),
                      label: const Text('Nuevo paquete'),
                    ),
                    OutlinedButton.icon(
                      onPressed: packages.isEmpty
                          ? null
                          : _searchAllClientPackagesInGmail,
                      icon: const Icon(Icons.manage_search),
                      label: const Text('Buscar todos en Gmail'),
                    ),
                  ],
                ),
              ),
'''
cs = r1(cs, new_package_anchor, new_package_new, 'client bulk Gmail button')
cpath.write_text(cs)

print('v31 applied: selected/all package Gmail scans, multi-delete, and client-scoped bulk Gmail search.')
