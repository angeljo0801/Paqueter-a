from pathlib import Path

# v81: barcode scanning remains unchanged. Add ON-DEVICE OCR of the
# recipient/customer name on a package shipping label. Match registered
# clients only after explicit selection; retain unmatched printed names.

p=Path('app/lib/packages.dart')
s=p.read_text()
anchor='class ScannerPage extends StatefulWidget {'
assert s.count(anchor)==1,'v81: ScannerPage declaration changed'

utils=r'''
class PackageLabelScan {
  final String tracking;
  final String? clientId;
  final String printedName;
  const PackageLabelScan({
    this.tracking='',
    this.clientId,
    this.printedName='',
  });
}

PackageLabelScan? normalizePackageLabelScan(Object? value) {
  if(value is PackageLabelScan)return value;
  if(value is String && value.trim().isNotEmpty){
    return PackageLabelScan(tracking:value.trim());
  }
  return null;
}

String normalizePackageName(String input) => input.toLowerCase()
  .replaceAll(RegExp(r'[áàâä]'),'a')
  .replaceAll(RegExp(r'[éèêë]'),'e')
  .replaceAll(RegExp(r'[íìîï]'),'i')
  .replaceAll(RegExp(r'[óòôö]'),'o')
  .replaceAll(RegExp(r'[úùûü]'),'u')
  .replaceAll('ñ','n')
  .replaceAll(RegExp(r'[^a-z0-9]+'),' ')
  .trim().replaceAll(RegExp(r'\s+'),' ');

String likelyPackageRecipientName(List<String> lines) {
  final header=RegExp(
    r'^(?:ship\s+to|deliver\s+to|recipient|consignee|
    r'destinatario|nombre|attn|enviar\s+a|para)\s*[:\-]?\s*(.*)
  bool valid(String value) {
    final text=value.trim();
    if(text.length<4 || text.length>60 ||
        text.split(RegExp(r'\s+')).length>6 ||
        RegExp(r'[0-9]').hasMatch(text))return false;
    if(RegExp(r'\b(?:street|road|ave|blvd|suite|apt|
       r'tracking|package|postal|usps|fedex|dhl|ups|shipper|'
       r'return|order|delivery|calle|avenida|codigo)\b',
       caseSensitive:false).hasMatch(text)){
      return false;
    }
    return RegExp(r'^[^\d@]+$').hasMatch(text);
  }
  for(var i=0;i<lines.length;i++){
    final m=header.firstMatch(lines[i].trim());
    if(m==null)continue;
    final tail=(m.group(1) ?? '').trim();
    if(valid(tail))return tail;
    if(tail.isEmpty && i+1<lines.length &&
        valid(lines[i+1]))return lines[i+1].trim();
  }
  return '';
}

Future<PackageLabelScan?> scanPrintedNameOnPackage(
  BuildContext context,
) async {
  final source=await showModalBottomSheet<ImageSource>(
    context:context,
    builder:(sheet)=>SafeArea(child:Wrap(children:[
      ListTile(
        leading:const Icon(Icons.camera_alt_outlined),
        title:const Text('Tomar foto de la etiqueta'),
        onTap:()=>Navigator.pop(sheet,ImageSource.camera)),
      ListTile(
        leading:const Icon(Icons.photo_library_outlined),
        title:const Text('Elegir foto de la etiqueta'),
        onTap:()=>Navigator.pop(sheet,ImageSource.gallery)),
    ])),
  );
  if(source==null || !context.mounted)return null;
  final photo=await ImagePicker().pickImage(
    source:source,imageQuality:92,maxWidth:2048);
  if(photo==null || !context.mounted)return null;
  final recognizer=TextRecognizer(script:TextRecognitionScript.latin);
  late final RecognizedText recognized;
  try{
    recognized=await recognizer.processImage(
      InputImage.fromFilePath(photo.path));
  }catch(error){
    if(context.mounted){
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content:Text('Error leyendo la etiqueta: $error')));
    }
    return null;
  }finally{
    await recognizer.close();
  }
  if(!context.mounted)return null;
  final text=recognized.text.trim();
  if(text.isEmpty){
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
      content:Text('No se detectó texto. Acerca la cámara al nombre.')));
    return null;
  }
  final lines=recognized.blocks.expand((b)=>b.lines)
    .map((l)=>l.text.trim()).where((line)=>line.isNotEmpty).toList();
  final guess=likelyPackageRecipientName(lines);
  final tracking=trackingCandidates(text).firstOrNull ?? '';
  final clients=active(await Store.list('clients'));
  if(!context.mounted)return null;
  final padded=' '+normalizePackageName(text)+' ';
  final suggestions=clients.where((c){
    final full=normalizePackageName((c['name'] ?? '').toString());
    return full.length>=4 && padded.contains(' '+full+' ');
  }).toList();

  final nameController=TextEditingController(text:guess);
  final searchController=TextEditingController();
  try{
    return await showModalBottomSheet<PackageLabelScan>(
      context:context,
      isScrollControlled:true,
      showDragHandle:true,
      builder:(sheet)=>StatefulBuilder(
        builder:(sheet,refresh){
          final query=normalizePackageName(searchController.text);
          final matches=query.isNotEmpty
            ? clients.where((c)=>normalizePackageName(
                (c['name'] ?? '').toString()).contains(query)).toList()
            : suggestions;
          return SafeArea(child:Padding(
            padding:EdgeInsets.only(
              bottom:MediaQuery.of(sheet).viewInsets.bottom),
            child:SizedBox(
              height:(MediaQuery.of(sheet).size.height*.75-
                MediaQuery.of(sheet).viewInsets.bottom)
                .clamp(260.0,MediaQuery.of(sheet).size.height*.75)
                .toDouble(),
              child:Column(children:[
                const ListTile(
                  title:Text('Nombre de la etiqueta'),
                  subtitle:Text('Selecciona el cliente correcto. '
                    'No se asignará automáticamente.')),
                Padding(
                  padding:const EdgeInsets.symmetric(horizontal:14),
                  child:TextField(
                    controller:nameController,
                    decoration:const InputDecoration(
                      labelText:'Nombre impreso (editable)',
                      prefixIcon:Icon(Icons.badge_outlined)),
                  ),
                ),
                if(tracking.isNotEmpty)
                  Padding(
                    padding:const EdgeInsets.all(8),
                    child:Text('Tracking: '+tracking)),
                Padding(
                  padding:const EdgeInsets.fromLTRB(14,4,14,8),
                  child:TextField(
                    controller:searchController,
                    onChanged:(_)=>refresh((){}),
                    decoration:const InputDecoration(
                      prefixIcon:Icon(Icons.search),
                      hintText:'Buscar entre tus clientes'),
                  ),
                ),
                Expanded(child:matches.isEmpty
                  ? const Center(child:Text(
                      'No hay coincidencia exacta. '
                      'Busca un cliente o conserva el nombre impreso.',
                      textAlign:TextAlign.center))
                  : ListView.builder(
                      itemCount:matches.length,
                      itemBuilder:(_,i){
                        final c=matches[i];
                        return ListTile(
                          leading:const Icon(Icons.person_outline),
                          title:Text((c['name'] ?? '').toString()),
                          subtitle:const Text('Vincular a este cliente'),
                          onTap:()=>Navigator.pop(sheet,PackageLabelScan(
                            tracking:tracking,
                            clientId:(c['id'] ?? '').toString(),
                            printedName:nameController.text.trim().isNotEmpty
                              ? nameController.text.trim()
                              : (c['name'] ?? '').toString())),
                        );
                      },
                    )),
                ),
                Padding(
                  padding:const EdgeInsets.fromLTRB(14,6,14,16),
                  child:Row(children:[
                    Expanded(child:OutlinedButton(
                      onPressed:()=>Navigator.pop(sheet),
                      child:const Text('Cancelar'))),
                    const SizedBox(width:8),
                    Expanded(child:FilledButton(
                      onPressed:()=>Navigator.pop(sheet,PackageLabelScan(
                        tracking:tracking,
                        printedName:nameController.text.trim())),
                      child:const Text('Guardar sin vincular'))),
                  ]),
                ),
              ]),
            ),
          ));
        },
      ),
    );
  }finally{
    nameController.dispose();
    searchController.dispose();
  }
}

'''
s=s.replace(anchor,utils+anchor,1)

a=s.index('class _ScannerPageState extends State<ScannerPage> {')
b=s.index('\nclass PackageEditPage extends StatefulWidget',a)
fn=s[a:b]
old="  bool done = false;"
assert fn.count(old)==1
fn=fn.replace(old, r'''  bool done = false;
  bool readingName=false;

  Future<void> _scanName() async {
    if(done || readingName)return;
    setState(()=>readingName=true);
    // Hide the live barcode camera before ImagePicker opens its camera.
    await Future<void>.delayed(const Duration(milliseconds:180));
    if(!mounted)return;
    try{
      final result=await scanPrintedNameOnPackage(context);
      if(!mounted)return;
      if(result!=null){
        done=true;
        Navigator.pop(context,result);
      }
    }finally{
      if(mounted && !done)setState(()=>readingName=false);
    }
  }''',1)
fn=fn.replace('child: MobileScanner(onDetect: (capture) {',
"""child: readingName
              ? const Center(child:CircularProgressIndicator())
              : MobileScanner(onDetect: (capture) {""",1)
marker="              const SizedBox(height: 8),\n              SizedBox(\n                width: double.infinity,\n                child: OutlinedButton.icon("
assert fn.count(marker)==1,'v81: scanner secondary button changed'
fn=fn.replace(marker, r'''              const SizedBox(height:8),
              SizedBox(
                width:double.infinity,
                child:FilledButton.tonalIcon(
                  onPressed:readingName?null:_scanName,
                  icon:const Icon(Icons.person_search_outlined),
                  label:const Text('Escanear nombre en la etiqueta'),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(''',1)
s=s[:a]+fn+s[b:]

# New/edit package retains the printed name, including when there is
# no matching client. This is separate from the existing client assignment.
old="  final String? initialClientId;"
assert s.count(old)==1
s=s.replace(old,old+"\n  final String? initialLabelName;",1)
old="    this.initialClientId,"
assert s.count(old)==1
s=s.replace(old,old+"\n    this.initialLabelName,",1)
old="  final gmailStore = TextEditingController()"
assert s.count(old)==1
s=s.replace(old,"  final printedNameController=TextEditingController();\n"+old,1)
old="    notes.text = '$"+"{widget.existing?['notes'] ?? ''}';"
assert s.count(old)==1,'v81: package notes init changed'
s=s.replace(old,old+"\n    printedNameController.text = '$"+"{widget.existing?['labelRecipientName'] ?? widget.initialLabelName ?? ''}';",1)

saveStart=s.index('  Future<void> save() async {',s.index('class _PackageEditPageState'))
saveEnd=s.index('\n  @override\n  Widget build(',saveStart)
save=s[saveStart:saveEnd]
needle="      'deleted': false,"
assert save.count(needle)==1
save=save.replace(needle,"      'labelRecipientName':printedNameController.text.trim(),\n"+needle,1)
s=s[:saveStart]+save+s[saveEnd:]

old="""                final c = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScannerPage()));
                if (c != null) setState(() { tracking.text = c; carrier = inferCarrier(c); });"""
assert s.count(old)==1,'v81: editor scanner callback changed'
s=s.replace(old,r'''                final raw=await Navigator.push<Object?>(context,
                  MaterialPageRoute(builder:(_)=>const ScannerPage()));
                final result=normalizePackageLabelScan(raw);
                if(result!=null && mounted)setState((){
                  if(result.tracking.isNotEmpty){
                    tracking.text=result.tracking;
                    carrier=inferCarrier(result.tracking);
                  }
                  if(result.printedName.isNotEmpty){
                    printedNameController.text=result.printedName;
                  }
                  if(result.clientId!=null && result.clientId!=clientId){
                    clientId=result.clientId;
                    purchaseId=null;
                    selectedPurchaseIds.clear();
                    recipientId=null;
                  }
                });''',1)

# Dedicated name OCR next to tracking controls, without replacing
# the v79 searchable client picker.
needle="""        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: FilledButton.tonalIcon(
            onPressed: gmailLoading ? null : reconstructFromGmail,"""
assert s.count(needle)==1,'v81: tracking form footer changed'
s=s.replace(needle,r'''        const SizedBox(height:8),
        OutlinedButton.icon(
          onPressed:() async {
            final result=await scanPrintedNameOnPackage(context);
            if(result==null || !mounted)return;
            setState((){
              if(result.printedName.isNotEmpty)
                printedNameController.text=result.printedName;
              if(tracking.text.trim().isEmpty &&
                  result.tracking.isNotEmpty){
                tracking.text=result.tracking;
                carrier=inferCarrier(result.tracking);
              }
              if(result.clientId!=null && result.clientId!=clientId){
                clientId=result.clientId;
                purchaseId=null;
                selectedPurchaseIds.clear();
                recipientId=null;
              }
            });
          },
          icon:const Icon(Icons.document_scanner_outlined),
          label:const Text('Escanear nombre del paquete'),
        ),
        TextField(
          controller:printedNameController,
          decoration:const InputDecoration(
            labelText:'Nombre impreso en la etiqueta',
            helperText:'Se conserva aunque no exista cliente registrado',
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: FilledButton.tonalIcon(
            onPressed: gmailLoading ? null : reconstructFromGmail,''',1)

# The v78 package dashboard scanners return either a barcode String or
# the selected label-scan result. Do not create a false tracking from a name.
a=s.index('class _PackagesPageState')
b=s.index('\nString inferCarrier(',a)
page=s[a:b]
old="final code = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScannerPage()));"
assert page.count(old)==1,'v81: packages dashboard scanner changed'
page=page.replace(old,r'''final raw=await Navigator.push<Object?>(context,
                MaterialPageRoute(builder:(_)=>const ScannerPage()));
              final scan=normalizePackageLabelScan(raw);
              final code=scan?.tracking ?? '';''',1)
old="if (code != null && mounted) {"
assert page.count(old)==1,'v81: dashboard scan completion changed'
page=page.replace(old,"if(scan!=null && mounted){",1)
old="PackageEditPage(initialTracking: code)"
assert page.count(old)==1,'v81: saved-new package route changed'
page=page.replace(old,"PackageEditPage(initialTracking:code,\n                    initialClientId:scan.clientId,\n                    initialLabelName:scan.printedName)",1)
s=s[:a]+page+s[b:]

assert "Escanear nombre en la etiqueta" in s
assert "initialLabelName" in s
assert "'labelRecipientName':printedNameController.text.trim()" in s
p.write_text(s)

# Home scanner shortcut also supports a name-only image OCR result.
p=Path('app/lib/main.dart')
s=p.read_text()
old="""              final code = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScannerPage()));
              if (code != null && context.mounted) {
                await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(initialTracking: code)));"""
assert s.count(old)==1,'v81: home scanner shortcut changed'
s=s.replace(old,r'''              final raw=await Navigator.push<Object?>(context,
                MaterialPageRoute(builder:(_)=>const ScannerPage()));
              final scan=normalizePackageLabelScan(raw);
              if(scan!=null && context.mounted){
                await Navigator.push(context,MaterialPageRoute(
                  builder:(_)=>PackageEditPage(
                    initialTracking:scan.tracking,
                    initialClientId:scan.clientId,
                    initialLabelName:scan.printedName,
                  )));''',1)
p.write_text(s)
print('v81: OCR printed names with manual customer confirmation, plus existing barcode tracking preserved.')
,
    caseSensitive:false);
  bool valid(String value) {
    final text=value.trim();
    if(text.length<4 || text.length>60 ||
        text.split(RegExp(r'\s+')).length>6 ||
        RegExp(r'[0-9]').hasMatch(text))return false;
    if(RegExp(r'(?i)\b(?:street|road|ave|blvd|suite|apt|'
       r'tracking|package|postal|usps|fedex|dhl|ups|shipper|'
       r'return|order|delivery|calle|avenida|codigo)\b').hasMatch(text)){
      return false;
    }
    return RegExp(r'^[^\d@]+$').hasMatch(text);
  }
  for(var i=0;i<lines.length;i++){
    final m=header.firstMatch(lines[i].trim());
    if(m==null)continue;
    final tail=(m.group(1) ?? '').trim();
    if(valid(tail))return tail;
    if(tail.isEmpty && i+1<lines.length &&
        valid(lines[i+1]))return lines[i+1].trim();
  }
  return '';
}

Future<PackageLabelScan?> scanPrintedNameOnPackage(
  BuildContext context,
) async {
  final source=await showModalBottomSheet<ImageSource>(
    context:context,
    builder:(sheet)=>SafeArea(child:Wrap(children:[
      ListTile(
        leading:const Icon(Icons.camera_alt_outlined),
        title:const Text('Tomar foto de la etiqueta'),
        onTap:()=>Navigator.pop(sheet,ImageSource.camera)),
      ListTile(
        leading:const Icon(Icons.photo_library_outlined),
        title:const Text('Elegir foto de la etiqueta'),
        onTap:()=>Navigator.pop(sheet,ImageSource.gallery)),
    ])),
  );
  if(source==null || !context.mounted)return null;
  final photo=await ImagePicker().pickImage(
    source:source,imageQuality:92,maxWidth:2048);
  if(photo==null || !context.mounted)return null;
  final recognizer=TextRecognizer(script:TextRecognitionScript.latin);
  late final RecognizedText recognized;
  try{
    recognized=await recognizer.processImage(
      InputImage.fromFilePath(photo.path));
  }catch(error){
    if(context.mounted){
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content:Text('Error leyendo la etiqueta: $error')));
    }
    return null;
  }finally{
    await recognizer.close();
  }
  if(!context.mounted)return null;
  final text=recognized.text.trim();
  if(text.isEmpty){
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
      content:Text('No se detectó texto. Acerca la cámara al nombre.')));
    return null;
  }
  final lines=recognized.blocks.expand((b)=>b.lines)
    .map((l)=>l.text.trim()).where((line)=>line.isNotEmpty).toList();
  final guess=likelyPackageRecipientName(lines);
  final tracking=trackingCandidates(text).firstOrNull ?? '';
  final clients=active(await Store.list('clients'));
  if(!context.mounted)return null;
  final padded=' '+normalizePackageName(text)+' ';
  final suggestions=clients.where((c){
    final full=normalizePackageName((c['name'] ?? '').toString());
    return full.length>=4 && padded.contains(' '+full+' ');
  }).toList();

  final nameController=TextEditingController(text:guess);
  final searchController=TextEditingController();
  try{
    return await showModalBottomSheet<PackageLabelScan>(
      context:context,
      isScrollControlled:true,
      showDragHandle:true,
      builder:(sheet)=>StatefulBuilder(
        builder:(sheet,refresh){
          final query=normalizePackageName(searchController.text);
          final matches=query.isNotEmpty
            ? clients.where((c)=>normalizePackageName(
                (c['name'] ?? '').toString()).contains(query)).toList()
            : suggestions;
          return SafeArea(child:Padding(
            padding:EdgeInsets.only(
              bottom:MediaQuery.of(sheet).viewInsets.bottom),
            child:SizedBox(
              height:(MediaQuery.of(sheet).size.height*.75-
                MediaQuery.of(sheet).viewInsets.bottom)
                .clamp(260.0,MediaQuery.of(sheet).size.height*.75)
                .toDouble(),
              child:Column(children:[
                const ListTile(
                  title:Text('Nombre de la etiqueta'),
                  subtitle:Text('Selecciona el cliente correcto. '
                    'No se asignará automáticamente.')),
                Padding(
                  padding:const EdgeInsets.symmetric(horizontal:14),
                  child:TextField(
                    controller:nameController,
                    decoration:const InputDecoration(
                      labelText:'Nombre impreso (editable)',
                      prefixIcon:Icon(Icons.badge_outlined)),
                  ),
                ),
                if(tracking.isNotEmpty)
                  Padding(
                    padding:const EdgeInsets.all(8),
                    child:Text('Tracking: '+tracking)),
                Padding(
                  padding:const EdgeInsets.fromLTRB(14,4,14,8),
                  child:TextField(
                    controller:searchController,
                    onChanged:(_)=>refresh((){}),
                    decoration:const InputDecoration(
                      prefixIcon:Icon(Icons.search),
                      hintText:'Buscar entre tus clientes'),
                  ),
                ),
                Expanded(child:matches.isEmpty
                  ? const Center(child:Text(
                      'No hay coincidencia exacta. '
                      'Busca un cliente o conserva el nombre impreso.',
                      textAlign:TextAlign.center))
                  : ListView.builder(
                      itemCount:matches.length,
                      itemBuilder:(_,i){
                        final c=matches[i];
                        return ListTile(
                          leading:const Icon(Icons.person_outline),
                          title:Text((c['name'] ?? '').toString()),
                          subtitle:const Text('Vincular a este cliente'),
                          onTap:()=>Navigator.pop(sheet,PackageLabelScan(
                            tracking:tracking,
                            clientId:(c['id'] ?? '').toString(),
                            printedName:nameController.text.trim().isNotEmpty
                              ? nameController.text.trim()
                              : (c['name'] ?? '').toString())),
                        );
                      },
                    )),
                ),
                Padding(
                  padding:const EdgeInsets.fromLTRB(14,6,14,16),
                  child:Row(children:[
                    Expanded(child:OutlinedButton(
                      onPressed:()=>Navigator.pop(sheet),
                      child:const Text('Cancelar'))),
                    const SizedBox(width:8),
                    Expanded(child:FilledButton(
                      onPressed:()=>Navigator.pop(sheet,PackageLabelScan(
                        tracking:tracking,
                        printedName:nameController.text.trim())),
                      child:const Text('Guardar sin vincular'))),
                  ]),
                ),
              ]),
            ),
          ));
        },
      ),
    );
  }finally{
    nameController.dispose();
    searchController.dispose();
  }
}

'''
s=s.replace(anchor,utils+anchor,1)

a=s.index('class _ScannerPageState extends State<ScannerPage> {')
b=s.index('\nclass PackageEditPage extends StatefulWidget',a)
fn=s[a:b]
old="  bool done = false;"
assert fn.count(old)==1
fn=fn.replace(old, r'''  bool done = false;
  bool readingName=false;

  Future<void> _scanName() async {
    if(done || readingName)return;
    setState(()=>readingName=true);
    // Hide the live barcode camera before ImagePicker opens its camera.
    await Future<void>.delayed(const Duration(milliseconds:180));
    if(!mounted)return;
    try{
      final result=await scanPrintedNameOnPackage(context);
      if(!mounted)return;
      if(result!=null){
        done=true;
        Navigator.pop(context,result);
      }
    }finally{
      if(mounted && !done)setState(()=>readingName=false);
    }
  }''',1)
fn=fn.replace('child: MobileScanner(onDetect: (capture) {',
"""child: readingName
              ? const Center(child:CircularProgressIndicator())
              : MobileScanner(onDetect: (capture) {""",1)
marker="              const SizedBox(height: 8),\n              SizedBox(\n                width: double.infinity,\n                child: OutlinedButton.icon("
assert fn.count(marker)==1,'v81: scanner secondary button changed'
fn=fn.replace(marker, r'''              const SizedBox(height:8),
              SizedBox(
                width:double.infinity,
                child:FilledButton.tonalIcon(
                  onPressed:readingName?null:_scanName,
                  icon:const Icon(Icons.person_search_outlined),
                  label:const Text('Escanear nombre en la etiqueta'),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(''',1)
s=s[:a]+fn+s[b:]

# New/edit package retains the printed name, including when there is
# no matching client. This is separate from the existing client assignment.
old="  final String? initialClientId;"
assert s.count(old)==1
s=s.replace(old,old+"\n  final String? initialLabelName;",1)
old="    this.initialClientId,"
assert s.count(old)==1
s=s.replace(old,old+"\n    this.initialLabelName,",1)
old="  final gmailStore = TextEditingController()"
assert s.count(old)==1
s=s.replace(old,"  final printedNameController=TextEditingController();\n"+old,1)
old="    notes.text = '$"+"{widget.existing?['notes'] ?? ''}';"
assert s.count(old)==1,'v81: package notes init changed'
s=s.replace(old,old+"\n    printedNameController.text = '$"+"{widget.existing?['labelRecipientName'] ?? widget.initialLabelName ?? ''}';",1)

saveStart=s.index('  Future<void> save() async {',s.index('class _PackageEditPageState'))
saveEnd=s.index('\n  @override\n  Widget build(',saveStart)
save=s[saveStart:saveEnd]
needle="      'deleted': false,"
assert save.count(needle)==1
save=save.replace(needle,"      'labelRecipientName':printedNameController.text.trim(),\n"+needle,1)
s=s[:saveStart]+save+s[saveEnd:]

old="""                final c = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScannerPage()));
                if (c != null) setState(() { tracking.text = c; carrier = inferCarrier(c); });"""
assert s.count(old)==1,'v81: editor scanner callback changed'
s=s.replace(old,r'''                final raw=await Navigator.push<Object?>(context,
                  MaterialPageRoute(builder:(_)=>const ScannerPage()));
                final result=normalizePackageLabelScan(raw);
                if(result!=null && mounted)setState((){
                  if(result.tracking.isNotEmpty){
                    tracking.text=result.tracking;
                    carrier=inferCarrier(result.tracking);
                  }
                  if(result.printedName.isNotEmpty){
                    printedNameController.text=result.printedName;
                  }
                  if(result.clientId!=null && result.clientId!=clientId){
                    clientId=result.clientId;
                    purchaseId=null;
                    selectedPurchaseIds.clear();
                    recipientId=null;
                  }
                });''',1)

# Dedicated name OCR next to tracking controls, without replacing
# the v79 searchable client picker.
needle="""        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: FilledButton.tonalIcon(
            onPressed: gmailLoading ? null : reconstructFromGmail,"""
assert s.count(needle)==1,'v81: tracking form footer changed'
s=s.replace(needle,r'''        const SizedBox(height:8),
        OutlinedButton.icon(
          onPressed:() async {
            final result=await scanPrintedNameOnPackage(context);
            if(result==null || !mounted)return;
            setState((){
              if(result.printedName.isNotEmpty)
                printedNameController.text=result.printedName;
              if(tracking.text.trim().isEmpty &&
                  result.tracking.isNotEmpty){
                tracking.text=result.tracking;
                carrier=inferCarrier(result.tracking);
              }
              if(result.clientId!=null && result.clientId!=clientId){
                clientId=result.clientId;
                purchaseId=null;
                selectedPurchaseIds.clear();
                recipientId=null;
              }
            });
          },
          icon:const Icon(Icons.document_scanner_outlined),
          label:const Text('Escanear nombre del paquete'),
        ),
        TextField(
          controller:printedNameController,
          decoration:const InputDecoration(
            labelText:'Nombre impreso en la etiqueta',
            helperText:'Se conserva aunque no exista cliente registrado',
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: FilledButton.tonalIcon(
            onPressed: gmailLoading ? null : reconstructFromGmail,''',1)

# The v78 package dashboard scanners return either a barcode String or
# the selected label-scan result. Do not create a false tracking from a name.
a=s.index('class _PackagesPageState')
b=s.index('\nString inferCarrier(',a)
page=s[a:b]
old="final code = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScannerPage()));"
assert page.count(old)==1,'v81: packages dashboard scanner changed'
page=page.replace(old,r'''final raw=await Navigator.push<Object?>(context,
                MaterialPageRoute(builder:(_)=>const ScannerPage()));
              final scan=normalizePackageLabelScan(raw);
              final code=scan?.tracking ?? '';''',1)
old="if (code != null && mounted) {"
assert page.count(old)==1,'v81: dashboard scan completion changed'
page=page.replace(old,"if(scan!=null && mounted){",1)
old="PackageEditPage(initialTracking: code)"
assert page.count(old)==1,'v81: saved-new package route changed'
page=page.replace(old,"PackageEditPage(initialTracking:code,\n                    initialClientId:scan.clientId,\n                    initialLabelName:scan.printedName)",1)
s=s[:a]+page+s[b:]

assert "Escanear nombre en la etiqueta" in s
assert "initialLabelName" in s
assert "'labelRecipientName':printedNameController.text.trim()" in s
p.write_text(s)

# Home scanner shortcut also supports a name-only image OCR result.
p=Path('app/lib/main.dart')
s=p.read_text()
old="""              final code = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const ScannerPage()));
              if (code != null && context.mounted) {
                await Navigator.push(context, MaterialPageRoute(builder: (_) => PackageEditPage(initialTracking: code)));"""
assert s.count(old)==1,'v81: home scanner shortcut changed'
s=s.replace(old,r'''              final raw=await Navigator.push<Object?>(context,
                MaterialPageRoute(builder:(_)=>const ScannerPage()));
              final scan=normalizePackageLabelScan(raw);
              if(scan!=null && context.mounted){
                await Navigator.push(context,MaterialPageRoute(
                  builder:(_)=>PackageEditPage(
                    initialTracking:scan.tracking,
                    initialClientId:scan.clientId,
                    initialLabelName:scan.printedName,
                  )));''',1)
p.write_text(s)
print('v81: OCR printed names with manual customer confirmation, plus existing barcode tracking preserved.')
