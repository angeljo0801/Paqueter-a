from pathlib import Path


def r1(s,a,b,l):
    if a not in s:
        raise SystemExit('Missing '+l)
    return s.replace(a,b,1)

bg=Path('app/lib/background_sync.dart')
s=bg.read_text()

c="const String gmailPhotoUpgradeTask = 'gmailBackgroundPhotoUpgrade';\n"
if 'gmailBulkPackageScanTask' not in s:
    s=s.replace(c,c+"const String gmailBulkPackageScanTask = 'gmailBulkPackageScan';\n",1)

s=r1(s,
'''    if (taskName == gmailPhotoUpgradeTask) {
      return GmailBackgroundSearch.upgradeOriginalPhotos(inputData);
    }
    if (taskName != courierBackgroundTask) return true;
''',
'''    if (taskName == gmailPhotoUpgradeTask) {
      return GmailBackgroundSearch.upgradeOriginalPhotos(inputData);
    }
    if (taskName == gmailBulkPackageScanTask) {
      return GmailBulkPackageScan.execute(inputData);
    }
    if (taskName != courierBackgroundTask) return true;
''','dispatcher')

bulk=r'''
class GmailBulkPackageScan {
  static const _key = 'gmailBulkPackageScanState';
  static const _tag = 'gmail-bulk-package-scan';
  static const _maxAttempts = 36;

  static bool _doneWithPhotos(Map<String,dynamic> p) {
    if (!gmailRecordIsLinked(p)) return false;
    if (dynList(p['emailPhotoUrls']).any((e) => '$e'.trim().isNotEmpty)) return true;
    if (dynList(p['emailAttachmentImages']).whereType<Map>().any((e) => '${e['url'] ?? ''}'.trim().isNotEmpty)) return true;
    final m=p['gmailOfflinePhotoPaths'];
    return m is Map && m.isNotEmpty;
  }

  static Future<Map<String,dynamic>> status() async {
    final p=await SharedPreferences.getInstance(); await p.reload();
    final raw=p.getString(_key);
    if (raw==null || raw.isEmpty) return {'status':'idle'};
    try { final d=jsonDecode(raw); if (d is Map) return Map<String,dynamic>.from(d); } catch(_){}
    return {'status':'idle'};
  }

  static bool isActive(Map<String,dynamic> s) {
    final v='${s['status'] ?? ''}';
    return v=='running' || v=='waiting';
  }

  static Future<void> _save(Map<String,dynamic> st) async {
    final p=await SharedPreferences.getInstance();
    await p.setString(_key,jsonEncode({...st,'updatedAt':DateTime.now().toIso8601String()}));
  }

  static Future<bool> _same(String token) async {
    final st=await status();
    return '${st['token'] ?? ''}'==token && isActive(st);
  }

  static Future<void> _schedule(String token,int index,int attempt,String base,String key,{Duration delay=Duration.zero}) async {
    await Workmanager().registerOneOffTask(
      'gmail-bulk-$token-$index-$attempt',
      gmailBulkPackageScanTask,
      inputData:{'token':token,'index':index,'attempt':attempt,'base':base,'key':key},
      initialDelay:delay,
      constraints:Constraints(networkType:NetworkType.connected),
      existingWorkPolicy:ExistingWorkPolicy.keep,
      tag:_tag,
    );
  }

  static Future<Map<String,dynamic>> start() async {
    try { await Workmanager().cancelByTag(_tag); } catch(_){}
    final base=(await WhatsBotPurchaseSyncService.backendUrl()).trim();
    final key=(await WhatsBotPurchaseSyncService.apiKey()).trim();
    if (base.isEmpty) throw Exception('Falta la URL del servidor de WhatsBot.');
    if (key.isEmpty) throw Exception('Falta la API key del servidor de WhatsBot.');

    final ps=active(await Store.list('packages',forceRefresh:true));
    final q=<Map<String,dynamic>>[]; var skipped=0;
    for(final p in ps){
      final t='${p['tracking'] ?? ''}'.trim();
      if(t.isEmpty) continue;
      if(_doneWithPhotos(p)){ skipped++; continue; }
      q.add({'id':'${p['id'] ?? ''}','tracking':t,'clientId':'${p['clientId'] ?? ''}','order':'${p['gmailOrderNumber'] ?? ''}'});
    }
    final token='${DateTime.now().microsecondsSinceEpoch}';
    final st=<String,dynamic>{
      'token':token,'status':q.isEmpty?'completed':'waiting','queue':q,'total':q.length,
      'processed':0,'found':0,'withoutPhotos':0,'notFound':0,'failed':0,'skipped':skipped,
      'current':'','message':q.isEmpty?'No hay paquetes pendientes.':'En cola · esperando conexión.',
      'startedAt':DateTime.now().toIso8601String()
    };
    await _save(st);
    if(q.isNotEmpty) await _schedule(token,0,0,base,key);
    return status();
  }

  static Future<Map<String,dynamic>> cancel() async {
    final st=await status();
    if(isActive(st)) await _save({...st,'status':'cancelled','current':'','message':'Búsqueda cancelada.'});
    try { await Workmanager().cancelByTag(_tag); } catch(_){}
    return status();
  }

  static Future<void> _advance(Map<String,dynamic> st,String token,int index,String base,String key,
      {int found=0,int without=0,int notFound=0,int failed=0}) async {
    if(!await _same(token)) return;
    final total=(st['total'] as num?)?.toInt()??0, next=index+1;
    final out=<String,dynamic>{
      ...st,'status':next>=total?'completed':'waiting','processed':next.clamp(0,total),
      'found':((st['found'] as num?)?.toInt()??0)+found,
      'withoutPhotos':((st['withoutPhotos'] as num?)?.toInt()??0)+without,
      'notFound':((st['notFound'] as num?)?.toInt()??0)+notFound,
      'failed':((st['failed'] as num?)?.toInt()??0)+failed,
      'current':'','message':next>=total?'Búsqueda terminada.':'En cola · esperando conexión.',
      if(next>=total) 'completedAt':DateTime.now().toIso8601String(),
    };
    await _save(out);
    if(next<total && await _same(token)) await _schedule(token,next,0,base,key,delay:const Duration(seconds:2));
  }

  @pragma('vm:entry-point')
  static Future<bool> execute(Map<String,dynamic>? input) async {
    final d=input??const <String,dynamic>{};
    final token='${d['token'] ?? ''}', base='${d['base'] ?? ''}', key='${d['key'] ?? ''}';
    final index=(d['index'] as num?)?.toInt()??0, attempt=(d['attempt'] as num?)?.toInt()??0;
    var st=await status();
    if(token.isEmpty || '${st['token'] ?? ''}'!=token || !isActive(st)) return true;
    final q=dynList(st['queue']).whereType<Map>().map((e)=>Map<String,dynamic>.from(e)).toList();
    if(index<0 || index>=q.length){ await _save({...st,'status':'completed','processed':q.length,'message':'Búsqueda terminada.'}); return true; }
    final item=q[index], id='${item['id'] ?? ''}', tracking='${item['tracking'] ?? ''}', clientId='${item['clientId'] ?? ''}', order='${item['order'] ?? ''}';
    st={...st,'status':'running','current':tracking,'message':'Buscando $tracking en Gmail…'}; await _save(st);
    try {
      final snap=await GmailBackgroundSearch._serverJobSnapshot(
        baseUrl:base,apiKey:key,orderNumber:order,tracking:tracking,
        token:'bulk_${token}_$id',clientId:clientId,
      );
      if(!await _same(token)) return true;
      final ss='${snap['status'] ?? ''}'.toLowerCase();
      if(ss=='queued' || ss=='running'){
        if(attempt>=_maxAttempts){ await _advance(st,token,index,base,key,failed:1); return true; }
        await _save({...st,'status':'waiting','message':'Gmail sigue procesando $tracking…'});
        await _schedule(token,index,attempt+1,base,key,delay:const Duration(seconds:6));
        return true;
      }
      if(ss=='failed'){ await _advance(st,token,index,base,key,failed:1); return true; }
      if(ss!='completed') throw Exception('Estado inesperado: $ss');
      final raw=snap['result']; if(raw is! Map) throw Exception('Resultado inválido.');
      final result=Map<String,dynamic>.from(raw);
      if(result['found']!=true){ await _advance(st,token,index,base,key,notFound:1); return true; }
      if(!await _same(token)) return true;
      final processed=await GmailBackgroundSearch._processPackagePhotosInBackground(
        result:result,baseUrl:base,apiKey:key,packageId:id,tracking:tracking,
      );
      Store.clearListCache('packages');
      final n=(processed['_backgroundPhotoCount'] as num?)?.toInt() ??
          dynList(processed['emailPhotoUrls']).length+dynList(processed['emailAttachmentImages']).length;
      await _advance(st,token,index,base,key,found:n>0?1:0,without:n>0?0:1);
      return true;
    } catch(_){
      if(!await _same(token)) return true;
      if(attempt>=_maxAttempts){ await _advance(st,token,index,base,key,failed:1); return true; }
      await _save({...st,'status':'waiting','message':'Pausada · esperando Internet para continuar.'});
      await _schedule(token,index,attempt+1,base,key,delay:const Duration(seconds:10));
      return true;
    }
  }
}

'''
if 'class GmailBulkPackageScan {' not in s:
    s=r1(s,'class NotificationService {\n',bulk+'class NotificationService {\n','bulk class')
bg.write_text(s)

p=Path('app/lib/packages.dart'); s=p.read_text()
s=r1(s,
'''class _PackagesPageState extends State<PackagesPage> {
  List<Map<String, dynamic>> rows = [], clients = [];
  final search = TextEditingController();
  String q = '';
  @override
  void initState() {
    super.initState();
    _restoreSearch();
    load();
  }

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  Future<void> _restoreSearch() async {
    final saved = await readPersistentSearch('packages');
    if (!mounted) return;
    search.text = saved;
    setState(() => q = saved);
  }
  Future<void> load() async {
    final r = await Future.wait([Store.list('packages'), Store.list('clients')]);
''',
'''class _PackagesPageState extends State<PackagesPage> {
  List<Map<String, dynamic>> rows = [], clients = [];
  final search = TextEditingController();
  String q = '';
  Map<String,dynamic> bulk={'status':'idle'};
  Timer? _bulkTimer;
  String _bulkStamp='';

  @override
  void initState() {
    super.initState();
    _restoreSearch();
    load(forceRefresh:true);
    _refreshBulk();
    _bulkTimer=Timer.periodic(const Duration(seconds:2),(_)=>_refreshBulk());
  }

  @override
  void dispose() {
    _bulkTimer?.cancel();
    search.dispose();
    super.dispose();
  }

  Future<void> _restoreSearch() async {
    final saved = await readPersistentSearch('packages');
    if (!mounted) return;
    search.text = saved;
    setState(() => q = saved);
  }

  Future<void> load({bool forceRefresh=false}) async {
    final r = await Future.wait([
      Store.list('packages',forceRefresh:forceRefresh),
      Store.list('clients',forceRefresh:forceRefresh),
    ]);
''','packages fields')

s=r1(s,
'''    if (!mounted) return;
    setState(() { rows = active(r[0]); clients = active(r[1]); });
  }

  @override
  Widget build(BuildContext context) {
''',
r'''    if (!mounted) return;
    setState(() { rows = active(r[0]); clients = active(r[1]); });
  }

  Future<void> _refreshBulk() async {
    final st=await GmailBulkPackageScan.status();
    if(!mounted) return;
    final stamp='${st['updatedAt'] ?? ''}';
    if(stamp!=_bulkStamp){
      _bulkStamp=stamp;
      setState(()=>bulk=st);
      await load(forceRefresh:true);
    }
  }

  Future<void> _startBulk() async {
    try {
      final st=await GmailBulkPackageScan.start();
      if(!mounted) return;
      _bulkStamp='${st['updatedAt'] ?? ''}'; setState(()=>bulk=st);
      final n=(st['total'] as num?)?.toInt()??0, sk=(st['skipped'] as num?)?.toInt()??0;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text(
        n==0?'No hay paquetes pendientes. $sk ya tienen Gmail y fotos.':
        'Búsqueda Gmail iniciada: $n paquete(s). $sk omitido(s) con Gmail y fotos.'
      )));
    } catch(e){
      if(mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text('$e'.replaceFirst('Exception: ',''))));
    }
  }

  Future<void> _cancelBulk() async {
    final st=await GmailBulkPackageScan.cancel();
    if(!mounted) return;
    _bulkStamp='${st['updatedAt'] ?? ''}'; setState(()=>bulk=st);
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Búsqueda Gmail cancelada.')));
  }

  Future<void> _bulkControls() async {
    final st=await GmailBulkPackageScan.status(); if(!mounted) return;
    final total=(st['total'] as num?)?.toInt()??0, done=(st['processed'] as num?)?.toInt()??0;
    final found=(st['found'] as num?)?.toInt()??0, without=(st['withoutPhotos'] as num?)?.toInt()??0;
    final nf=(st['notFound'] as num?)?.toInt()??0, failed=(st['failed'] as num?)?.toInt()??0, sk=(st['skipped'] as num?)?.toInt()??0;
    final running=GmailBulkPackageScan.isActive(st);
    await showModalBottomSheet<void>(context:context,showDragHandle:true,builder:(ctx)=>SafeArea(
      child:Padding(padding:const EdgeInsets.fromLTRB(20,4,20,20),child:Column(mainAxisSize:MainAxisSize.min,crossAxisAlignment:CrossAxisAlignment.stretch,children:[
        Text('Búsqueda masiva de Gmail',style:Theme.of(ctx).textTheme.titleLarge),
        const SizedBox(height:12),
        LinearProgressIndicator(value:total<=0?0:(done/total).clamp(0.0,1.0)),
        const SizedBox(height:8), Text('$done de $total revisados'),
        Text('Con fotos: $found · Gmail sin foto: $without · Sin correo: $nf · Errores: $failed'),
        if(sk>0) Text('Omitidos: $sk (ya tenían Gmail + fotos).'),
        if('${st['current'] ?? ''}'.isNotEmpty) Text('Ahora: ${st['current']}'),
        const SizedBox(height:6), Text('${st['message'] ?? ''}'), const SizedBox(height:14),
        if(running) OutlinedButton.icon(onPressed:() async {Navigator.pop(ctx); await _cancelBulk();},icon:const Icon(Icons.stop_circle_outlined),label:const Text('Cancelar')),
        const SizedBox(height:8),
        FilledButton.icon(onPressed:() async {Navigator.pop(ctx); await _startBulk();},icon:const Icon(Icons.restart_alt),label:const Text('Reiniciar')),
      ]))
    ));
  }

  Widget _bulkButton(){
    final on=GmailBulkPackageScan.isActive(bulk);
    final total=(bulk['total'] as num?)?.toInt()??0, done=(bulk['processed'] as num?)?.toInt()??0;
    return IconButton(
      tooltip:on?'Búsqueda Gmail $done/$total · tocar para controles':'Buscar todos los paquetes en Gmail',
      onPressed:on?_bulkControls:_startBulk,
      icon:SizedBox(width:28,height:28,child:Stack(alignment:Alignment.center,children:[
        Icon(on?Icons.mark_email_unread_outlined:Icons.manage_search),
        if(on) SizedBox(width:28,height:28,child:CircularProgressIndicator(strokeWidth:2,value:total<=0?null:(done/total).clamp(0.0,1.0))),
      ])),
    );
  }

  @override
  Widget build(BuildContext context) {
''','packages helpers')

s=r1(s,
'''        actions: [
          IconButton(
            tooltip: 'Escanear código',
''',
'''        actions: [
          _bulkButton(),
          IconButton(
            tooltip: 'Escanear código',
''','button')
p.write_text(s)
print('Gmail v23 bulk package scan applied.')
