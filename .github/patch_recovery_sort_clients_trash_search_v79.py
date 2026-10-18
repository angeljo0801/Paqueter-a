from pathlib import Path

# v79: package sort choices, searchable client selection, and Trash search.
# Keep v74-v78 save/delete/visibility safeguards and all Gmail functions.
p = Path('app/lib/packages.dart')
s = p.read_text()
a=s.index('class _PackagesPageState extends State<PackagesPage> {')
b=s.index('\nString inferCarrier(String tracking)',a)
page=s[a:b]

state="  bool _refreshingPackages = false;"
assert page.count(state)==1
page=page.replace(state,state+"\n  String _packageSort = 'original';",1)
init="    load(forceRefresh:true);\n    _refreshBulk();"
assert page.count(init)==1
page=page.replace(init,"    load(forceRefresh:true);\n    _restorePackageSort();\n    _refreshBulk();",1)

anchor='  Future<void> _refreshPackages() async {'
assert page.count(anchor)==1
methods=r'''  Future<void> _restorePackageSort() async {
    try {
      final mode=(await Store._readRaw('ui_packages_sort_v1') ?? '').trim();
      const allowed=<String>{
        'original','newest','oldest','client_az','client_za',
        'tracking_az','tracking_za','weight_high','weight_low',
        'status_az','carrier_az'
      };
      if(mounted && allowed.contains(mode)){
        setState(()=>_packageSort=mode);
      }
    } catch(error){
      debugPrint('Package sort preference: $error');
    }
  }

  void _setPackageSort(String value){
    setState(()=>_packageSort=value);
    unawaited(Store._writeRaw('ui_packages_sort_v1',value)
      .catchError((Object error){
        debugPrint('Cannot save package sort: $error');
      }));
  }

  DateTime? _packageSortDate(Map<String,dynamic> row){
    // Creation dates are recorded for all newly created packages. Pre-v79
    // records may only carry a reception or manual-edition timestamp.
    for(final field in <String>[
      'createdAt','receivedAt','paqueteriaLocalEditedAt'
    ]){
      final value=(row[field] ?? '').toString().trim();
      final date=DateTime.tryParse(value);
      if(date!=null)return date;
    }
    return null;
  }

  void _sortVisiblePackages(List<Map<String,dynamic>> visible){
    final original=<String,int>{};
    for(var i=0;i<visible.length;i++){
      original[(visible[i]['id'] ?? '').toString()]=i;
    }
    int stable(Map<String,dynamic> a,Map<String,dynamic> b)=>
      (original[(a['id'] ?? '').toString()] ?? 0)
        .compareTo(original[(b['id'] ?? '').toString()] ?? 0);
    int alphabetical(String a,String b)=>
      a.toLowerCase().compareTo(b.toLowerCase());

    if(_packageSort=='original')return;
    visible.sort((a,b){
      var cmp=0;
      switch(_packageSort){
        case 'newest':
        case 'oldest':
          final one=_packageSortDate(a),two=_packageSortDate(b);
          if(one!=null && two!=null){
            cmp=one.compareTo(two);
          }else if(one!=null){
            cmp=1;
          }else if(two!=null){
            cmp=-1;
          }
          if(_packageSort=='newest')cmp=-cmp;
          break;
        case 'client_az':
        case 'client_za':
          cmp=alphabetical(
            clientName(clients,(a['clientId'] ?? '').toString()),
            clientName(clients,(b['clientId'] ?? '').toString()));
          if(_packageSort=='client_za')cmp=-cmp;
          break;
        case 'tracking_az':
        case 'tracking_za':
          cmp=alphabetical((a['tracking'] ?? '').toString(),
            (b['tracking'] ?? '').toString());
          if(_packageSort=='tracking_za')cmp=-cmp;
          break;
        case 'weight_high':
          cmp=number(b['billWeight']).compareTo(number(a['billWeight']));
          break;
        case 'weight_low':
          cmp=number(a['billWeight']).compareTo(number(b['billWeight']));
          break;
        case 'status_az':
          cmp=alphabetical((a['status'] ?? '').toString(),
            (b['status'] ?? '').toString());
          break;
        case 'carrier_az':
          cmp=alphabetical((a['carrier'] ?? '').toString(),
            (b['carrier'] ?? '').toString());
          break;
      }
      return cmp!=0?cmp:stable(a,b);
    });
  }

'''
page=page.replace(anchor,methods+anchor,1)

pin="    if (_latestSavedPackageId.isNotEmpty) {"
assert page.count(pin)==1
page=page.replace(pin,"    _sortVisiblePackages(f);\n"+pin,1)
btn="          IconButton(\n            tooltip: 'Actualizar lista de paquetes',"
assert page.count(btn)==1
sort_btn=r'''          PopupMenuButton<String>(
            tooltip: 'Ordenar paquetes',
            icon: const Icon(Icons.sort),
            onSelected: _setPackageSort,
            itemBuilder: (_) => const [
              PopupMenuItem(value:'original',child:Text('Orden original')),
              PopupMenuItem(value:'newest',child:Text('Más recientes')),
              PopupMenuItem(value:'oldest',child:Text('Más antiguos')),
              PopupMenuItem(value:'client_az',child:Text('Cliente A–Z')),
              PopupMenuItem(value:'client_za',child:Text('Cliente Z–A')),
              PopupMenuItem(value:'tracking_az',child:Text('Tracking A–Z')),
              PopupMenuItem(value:'tracking_za',child:Text('Tracking Z–A')),
              PopupMenuItem(value:'weight_high',child:Text('Mayor peso')),
              PopupMenuItem(value:'weight_low',child:Text('Menor peso')),
              PopupMenuItem(value:'status_az',child:Text('Estado')),
              PopupMenuItem(value:'carrier_az',child:Text('Transportista')),
            ],
          ),
'''
page=page.replace(btn,sort_btn+btn,1)
assert "_sortVisiblePackages(f);" in page
assert "if (_latestSavedPackageId.isNotEmpty)" in page
s=s[:a]+page+s[b:]

edit_a=s.index('class _PackageEditPageState extends State<PackageEditPage> {')
edit=s[edit_a:]
anchor="  void autoBillWeight() {"
assert edit.count(anchor)==1
picker=r'''  String _clientSearchKey(String text) => text.toLowerCase().trim()
    .replaceAll(RegExp(r'[áàâä]'),'a')
    .replaceAll(RegExp(r'[éèêë]'),'e')
    .replaceAll(RegExp(r'[íìîï]'),'i')
    .replaceAll(RegExp(r'[óòôö]'),'o')
    .replaceAll(RegExp(r'[úùûü]'),'u')
    .replaceAll('ñ','n');

  Future<void> _choosePackageClient() async {
    final ordered=List<Map<String,dynamic>>.from(clients)
      ..sort((a,b)=>_clientSearchKey((a['name'] ?? '').toString())
          .compareTo(_clientSearchKey((b['name'] ?? '').toString())));
    var query='';
    final chosen=await showModalBottomSheet<String>(
      context:context,
      isScrollControlled:true,
      showDragHandle:true,
      builder:(sheetContext)=>StatefulBuilder(
        builder:(sheetContext,updateSheet){
          final search=_clientSearchKey(query);
          final filtered=ordered.where((c){
            if(search.isEmpty)return true;
            return _clientSearchKey((c['name'] ?? '').toString())
              .contains(search) ||
              (c['phone'] ?? '').toString().contains(query.trim());
          }).toList();
          return SafeArea(child:Padding(
            padding:EdgeInsets.only(
              bottom:MediaQuery.of(sheetContext).viewInsets.bottom),
            child:SizedBox(
              height:MediaQuery.of(sheetContext).size.height*.72,
              child:Column(children:[
                Padding(
                  padding:const EdgeInsets.fromLTRB(16,4,16,10),
                  child:TextField(
                    autofocus:true,
                    textInputAction:TextInputAction.search,
                    onChanged:(value)=>updateSheet(()=>query=value),
                    decoration:const InputDecoration(
                      hintText:'Buscar cliente por nombre',
                      prefixIcon:Icon(Icons.search),
                    ),
                  ),
                ),
                Expanded(child:filtered.isEmpty
                  ? const Center(child:Text('No se encontraron clientes.'))
                  : ListView.builder(
                      itemCount:filtered.length,
                      itemBuilder:(context,index){
                        final c=filtered[index];
                        final id=(c['id'] ?? '').toString();
                        return ListTile(
                          title:Text((c['name'] ?? '').toString()),
                          trailing:id==clientId
                            ? const Icon(Icons.check_circle_outline)
                            : null,
                          onTap:id.isEmpty?null:()=>
                              Navigator.pop(sheetContext,id),
                        );
                      },
                    )),
              ]),
            ),
          ));
        },
      ),
    );
    if(chosen==null || !mounted || chosen==clientId)return;
    setState((){
      clientId=chosen;
      purchaseId=null;
      selectedPurchaseIds.clear();
      recipientId=null;
    });
  }

'''
edit=edit.replace(anchor,picker+anchor,1)
oldline=[line for line in edit.splitlines() if "_drop('Cliente *'," in line]
assert len(oldline)==1, 'v79: package client form row moved'
newrow=r'''        InkWell(
          borderRadius:BorderRadius.circular(8),
          onTap:_choosePackageClient,
          child:InputDecorator(
            decoration:const InputDecoration(
              labelText:'Cliente *',
              prefixIcon:Icon(Icons.person_search_outlined),
              suffixIcon:Icon(Icons.arrow_drop_down),
            ),
            child:Text(clientId==null
              ? 'Buscar y seleccionar cliente'
              : clients.where((c)=>
                    (c['id'] ?? '').toString()==clientId)
                  .map((c)=>(c['name'] ?? '').toString())
                  .firstOrNull ?? 'Seleccionar cliente'),
          ),
        ),'''
edit=edit.replace(oldline[0],newrow,1)

old="      'deleted': false,\n      'paqueteriaLocalEditedAt':"
assert edit.count(old)==1,'v79: metadata for saved package changed'
edit=edit.replace(old,r'''      'deleted': false,
      'createdAt': widget.existing?['createdAt'] ??
          (previousIndex>=0?rows[previousIndex]['createdAt']:null) ??
          DateTime.now().toUtc().toIso8601String(),
      'paqueteriaLocalEditedAt':''',1)
s=s[:edit_a]+edit
p.write_text(s)

p=Path('app/lib/extras.dart')
s=p.read_text()
a=s.index('class _TrashPageState extends State<TrashPage> {')
b=s.index('\nclass MorePage extends StatelessWidget',a)
seg=s[a:b]
marker="  bool busy = false;"
assert seg.count(marker)==1
seg=seg.replace(marker,marker+r'''
  bool _trashSearching=false;
  String _trashQuery='';
  final TextEditingController _trashSearchController=TextEditingController();
''',1)

marker="  @override\n  void initState() { super.initState(); load(); }"
assert seg.count(marker)==1
seg=seg.replace(marker,marker+r'''

  @override
  void dispose(){
    _trashSearchController.dispose();
    super.dispose();
  }
''',1)

build="  @override\n  Widget build(BuildContext context) => Scaffold("
assert seg.count(build)==1
seg=seg.replace(build,r'''  @override
  Widget build(BuildContext context) {
    final query=_trashQuery.toLowerCase().trim();
    final filtered=deleted.where((row){
      if(query.isEmpty)return true;
      final text=<String>[
        label(row),
        (row['_type'] ?? '').toString(),
        (row['tracking'] ?? '').toString(),
        (row['carrier'] ?? '').toString(),
        (row['status'] ?? '').toString(),
        (row['store'] ?? '').toString(),
        (row['notes'] ?? '').toString(),
        if(row['_key']=='packages')
          clientName(clients,(row['clientId'] ?? '').toString()),
      ].join(' ').toLowerCase();
      return text.contains(query);
    }).toList();
    return Scaffold(''',1)
tb="      title: const Text('Papelera'),\n      actions: ["
assert seg.count(tb)==1
seg=seg.replace(tb,tb+r'''
        IconButton(
          tooltip:_trashSearching?'Cerrar búsqueda':'Buscar en papelera',
          icon:Icon(_trashSearching?Icons.close:Icons.search),
          onPressed:()=>setState((){
            _trashSearching=!_trashSearching;
            if(!_trashSearching){
              _trashQuery='';
              _trashSearchController.clear();
            }
          }),
        ),
''',1)
old="""        : ListView.builder(
            itemCount: deleted.length,
            itemBuilder: (_, i) {
              final row = deleted[i];"""
assert seg.count(old)==1
new=r'''        : Column(children:[
            if(_trashSearching)
              Padding(
                padding:const EdgeInsets.all(12),
                child:TextField(
                  controller:_trashSearchController,
                  autofocus:true,
                  onChanged:(value)=>setState(()=>_trashQuery=value),
                  decoration:InputDecoration(
                    prefixIcon:const Icon(Icons.search),
                    hintText:'Tracking, cliente, nombre o tipo',
                    suffixIcon:_trashQuery.isEmpty?null:IconButton(
                      tooltip:'Limpiar búsqueda',
                      onPressed:()=>setState((){
                        _trashQuery='';
                        _trashSearchController.clear();
                      }),
                      icon:const Icon(Icons.clear),
                    ),
                  ),
                ),
              ),
            Expanded(
              child:filtered.isEmpty
                ? const Center(child:Text('No hay resultados en papelera.'))
                : ListView.builder(
                    itemCount:filtered.length,
                    itemBuilder:(_,i){
                      final row=filtered[i];'''
seg=seg.replace(old,new,1)
end="""            },
          ),
  );
}"""
assert seg.count(end)==1, 'v79: Trash list ending changed'
seg=seg.replace(end,"""                    },
                  ),
            ),
          ]),
    );
  }
}""",1)
assert '_showTrashedPackageDetails' in seg
assert 'Vaciar definitivamente' in seg
assert "if (row['_key'] == 'packages')" in seg
s=s[:a]+seg+s[b:]
p.write_text(s)
print('v79: persistent package sort, searchable client chooser, and Trash search applied.')
