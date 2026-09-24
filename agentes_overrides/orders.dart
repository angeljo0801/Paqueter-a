part of 'main.dart';

List<String> orderPhotoPaths(Map<String,dynamic> order){
  final out=<String>[];final raw=order['photoPaths'];
  if(raw is List){for(final v in raw){final p='$v'.trim();if(p.isNotEmpty&&!out.contains(p))out.add(p);}}
  final legacy='${order['photoPath']??''}'.trim();if(legacy.isNotEmpty&&!out.contains(legacy))out.add(legacy);
  final receipt='${order['receiptPath']??''}'.trim();if(out.isEmpty&&receipt.isNotEmpty)out.add(receipt);
  return out;
}

class OrdersPage extends StatefulWidget { const OrdersPage({super.key}); @override State<OrdersPage> createState()=>_OrdersPageState(); }
class _OrdersPageState extends State<OrdersPage>{
  List<Map<String,dynamic>> rows=[],clients=[]; String q='';
  @override void initState(){super.initState();load();}
  Future<void>load()async{final r=await Future.wait([Store.list('orders'),Store.list('clients')]);if(!mounted)return;setState((){rows=active(r[0] as List<Map<String,dynamic>>);clients=active(r[1] as List<Map<String,dynamic>>);});}
  bool isUnassigned(Map<String,dynamic> e)=>orderIsUnassigned(e);

  Future<void>assignClient(Map<String,dynamic> order)async{
    if(clients.isEmpty){ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Primero crea un cliente para poder asociar el pedido.')));return;}
    final selected=await showModalBottomSheet<String>(context:context,builder:(_)=>SafeArea(child:ListView(shrinkWrap:true,children:[const ListTile(leading:Icon(Icons.person_add_alt_1),title:Text('Asociar pedido a un cliente'),subtitle:Text('Selecciona un cliente ya creado')),const Divider(height:1),for(final c in clients)ListTile(leading:const CircleAvatar(child:Icon(Icons.person)),title:Text('${c['name']}'),subtitle:'${c['phone']??''}'.trim().isEmpty?null:Text('${c['phone']}'),onTap:()=>Navigator.pop(context,'${c['id']}'))])));
    if(selected==null||selected.isEmpty)return;
    final all=await Store.list('orders');final i=all.indexWhere((e)=>'${e['id']}'=='${order['id']}');if(i<0)return;
    all[i]={...all[i],'clientId':selected,'unassigned':false};await Store.saveList('orders',all);if(!mounted)return;await load();ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text('Pedido asociado a ${clientName(clients,selected)}.')));
  }

  @override Widget build(BuildContext context){
    final f=rows.where((e)=>'${e['store']} ${e['orderNumber']} ${clientName(clients,'${e['clientId']}')} ${e['status']}'.toLowerCase().contains(q.toLowerCase())).toList();
    final total=f.fold<double>(0,(a,e)=>a+orderClientTotal(e));
    return Scaffold(appBar:AppBar(title:const Text('Pedidos y compras')),body:Column(children:[
      Padding(padding:const EdgeInsets.all(12),child:TextField(onChanged:(v)=>setState(()=>q=v),decoration:const InputDecoration(prefixIcon:Icon(Icons.search),hintText:'Cliente, tienda o número de pedido'))),
      Padding(padding:const EdgeInsets.symmetric(horizontal:12),child:_sectionCard(context,'Total visible asignado',Icons.calculate,[Text(money(total),style:Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight:FontWeight.bold))])),
      Expanded(child:f.isEmpty?const Center(child:Text('No hay pedidos.')):ListView.builder(itemCount:f.length,itemBuilder:(_,i){final e=f[i];final photos=orderPhotoPaths(e);final unassigned=isUnassigned(e);return ListTile(leading:photos.isNotEmpty&&File(photos.first).existsSync()?ClipRRect(borderRadius:BorderRadius.circular(8),child:Image.file(File(photos.first),width:52,height:52,fit:BoxFit.cover)):const SizedBox(width:52,height:52,child:Icon(Icons.shopping_bag)),title:Text('${e['store']} · ${money(orderSavedClientTotal(e))}'),subtitle:Text(unassigned?'Sin cliente · Toca el icono de persona para asociarlo\n${e['status']} · Costo real: ${money(orderStoreCost(e))}':'${clientName(clients,'${e['clientId']}')} · ${e['status']}\nCosto real: ${money(orderStoreCost(e))}'),isThreeLine:true,onTap:()async{await Navigator.push(context,MaterialPageRoute(builder:(_)=>OrderEditPage(existing:e)));load();},trailing:Wrap(mainAxisSize:MainAxisSize.min,children:[if(unassigned)IconButton(tooltip:'Asociar cliente',icon:const Icon(Icons.person_add_alt_1),onPressed:()=>assignClient(e)),IconButton(icon:const Icon(Icons.delete_outline),onPressed:()async{if(await confirmDelete(context,'este pedido')){await softDelete('orders','${e['id']}');load();}})]));}))
    ]),floatingActionButton:FloatingActionButton.extended(onPressed:()async{await Navigator.push(context,MaterialPageRoute(builder:(_)=>const OrderEditPage()));load();},icon:const Icon(Icons.add),label:const Text('Pedido')));
  }
}

class OrderEditPage extends StatefulWidget{final Map<String,dynamic>?existing;const OrderEditPage({super.key,this.existing});@override State<OrderEditPage> createState()=>_OrderEditPageState();}
class _OrderEditPageState extends State<OrderEditPage>{
  final store=TextEditingController(),orderNo=TextEditingController(),description=TextEditingController(),storeCost=TextEditingController(),clientTotal=TextEditingController(),date=TextEditingController(),notes=TextEditingController();
  List<Map<String,dynamic>>clients=[];String?clientId;String status='Pendiente';List<String>photoPaths=[];bool loaded=false;
  @override void initState(){super.initState();init();}
  Future<void>init()async{clients=active(await Store.list('clients'));final e=widget.existing;store.text='${e?['store']??''}';orderNo.text='${e?['orderNumber']??''}';description.text='${e?['description']??''}';storeCost.text='${e==null?'':orderStoreCost(e)}';clientTotal.text='${e==null?'':orderSavedClientTotal(e)}';date.text='${e?['date']??today()}';notes.text='${e?['notes']??''}';final raw='${e?['clientId']??''}'.trim();clientId=raw.isEmpty?null:raw;status='${e?['status']??'Pendiente'}';photoPaths=e==null?<String>[]:orderPhotoPaths(e);if(mounted)setState(()=>loaded=true);}

  Future<void>pickPhotos()async{
    final action=await showModalBottomSheet<String>(context:context,builder:(_)=>SafeArea(child:Wrap(children:[ListTile(leading:const Icon(Icons.camera_alt),title:const Text('Tomar foto'),onTap:()=>Navigator.pop(context,'camera')),ListTile(leading:const Icon(Icons.collections),title:const Text('Elegir una o varias imágenes'),onTap:()=>Navigator.pop(context,'gallery'))])));
    if(action==null)return;final picker=ImagePicker();
    if(action=='camera'){final x=await picker.pickImage(source:ImageSource.camera,imageQuality:88);if(x!=null&&mounted)setState((){if(!photoPaths.contains(x.path))photoPaths.add(x.path);});}
    else{final xs=await picker.pickMultiImage(imageQuality:88);if(xs.isNotEmpty&&mounted)setState((){for(final x in xs){if(!photoPaths.contains(x.path))photoPaths.add(x.path);}});}
  }
  Future<void>openPhoto(String path)async{if(!File(path).existsSync())return;await showDialog(context:context,builder:(_)=>Dialog(child:InteractiveViewer(child:Image.file(File(path),fit:BoxFit.contain))));}

  Future<void>save()async{
    if(store.text.trim().isEmpty){ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('La tienda es obligatoria.')));return;}
    final cost=number(storeCost.text);final unassigned=clientId==null||clientId!.trim().isEmpty;
    await upsert('orders',{'id':widget.existing?['id']??newId(),'clientId':unassigned?'':clientId,'unassigned':unassigned,'store':store.text.trim(),'orderNumber':orderNo.text.trim(),'description':description.text.trim(),'storeCost':cost,'ownerDue':cost,'clientTotal':number(clientTotal.text),'date':date.text.trim().isEmpty?today():date.text.trim(),'status':status,'notes':notes.text.trim(),'photoPaths':photoPaths,'photoPath':photoPaths.isEmpty?'':photoPaths.first,'receiptPath':photoPaths.isEmpty?null:photoPaths.first,'deleted':false});
    if(!mounted)return;if(unassigned)ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Pedido guardado sin cliente. Puedes asociarlo más adelante.')));Navigator.pop(context);
  }
  @override Widget build(BuildContext context){if(!loaded)return const Scaffold(body:Center(child:CircularProgressIndicator()));final assigned=clientId!=null&&clientId!.trim().isNotEmpty;final profit=assigned?number(clientTotal.text)-number(storeCost.text):0.0;return Scaffold(appBar:AppBar(title:Text(widget.existing==null?'Nuevo pedido':'Editar pedido')),body:ListView(padding:const EdgeInsets.all(16),children:[
    _drop('Cliente (opcional)',clientId,clients.map((c)=>DropdownMenuItem(value:'${c['id']}',child:Text('${c['name']}'))).toList(),(v)=>setState(()=>clientId=v)),const SizedBox(height:6),const Text('Puedes guardar el pedido sin cliente y asociarlo después desde Pedidos y compras.',style:TextStyle(fontSize:12)),const SizedBox(height:10),
    TextField(controller:store,decoration:const InputDecoration(labelText:'Tienda *')),const SizedBox(height:10),TextField(controller:orderNo,decoration:const InputDecoration(labelText:'Número de pedido')),const SizedBox(height:10),TextField(controller:description,maxLines:2,decoration:const InputDecoration(labelText:'Descripción / artículos')),const SizedBox(height:10),
    TextField(controller:storeCost,onChanged:(_)=>setState((){}),keyboardType:const TextInputType.numberWithOptions(decimal:true),decoration:const InputDecoration(labelText:'Costo real de compra (pagado por Alas Cargo)')),const SizedBox(height:10),
    TextField(controller:clientTotal,onChanged:(_)=>setState((){}),keyboardType:const TextInputType.numberWithOptions(decimal:true),decoration:InputDecoration(labelText:assigned?'Total que paga el cliente':'Total previsto al asociar cliente')),const SizedBox(height:10),
    TextField(controller:date,decoration:const InputDecoration(labelText:'Fecha YYYY-MM-DD')),const SizedBox(height:10),_drop('Estado',status,['Pendiente','Comprado','En preparación','Completado','Cancelado'].map((x)=>DropdownMenuItem(value:x,child:Text(x))).toList(),(v)=>setState(()=>status=v??status)),const SizedBox(height:10),TextField(controller:notes,maxLines:3,decoration:const InputDecoration(labelText:'Notas')),const SizedBox(height:14),
    Row(children:[Expanded(child:Text('Fotos del pedido / compra',style:Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight:FontWeight.bold))),if(photoPaths.isNotEmpty)Text('${photoPaths.length} foto${photoPaths.length==1?'':'s'}')]),const SizedBox(height:6),const Text('Opcional. Puedes guardar todas las fotos, screenshots o tickets que necesites.'),const SizedBox(height:10),
    if(photoPaths.isNotEmpty)...[GridView.builder(shrinkWrap:true,physics:const NeverScrollableScrollPhysics(),itemCount:photoPaths.length,gridDelegate:const SliverGridDelegateWithFixedCrossAxisCount(crossAxisCount:3,crossAxisSpacing:8,mainAxisSpacing:8),itemBuilder:(_,index){final path=photoPaths[index];return Stack(fit:StackFit.expand,children:[InkWell(onTap:()=>openPhoto(path),child:ClipRRect(borderRadius:BorderRadius.circular(10),child:File(path).existsSync()?Image.file(File(path),fit:BoxFit.cover):Container(color:Theme.of(context).colorScheme.surfaceContainerHighest,child:const Icon(Icons.broken_image_outlined)))),Positioned(right:2,top:2,child:IconButton.filled(visualDensity:VisualDensity.compact,tooltip:'Quitar esta foto',onPressed:()=>setState(()=>photoPaths.removeAt(index)),icon:const Icon(Icons.close,size:18))),Positioned(left:5,bottom:4,child:Container(padding:const EdgeInsets.symmetric(horizontal:6,vertical:2),decoration:BoxDecoration(color:Colors.black54,borderRadius:BorderRadius.circular(6)),child:Text('${index+1}',style:const TextStyle(color:Colors.white))))]);}),const SizedBox(height:10)],
    FilledButton.tonalIcon(onPressed:pickPhotos,icon:const Icon(Icons.add_photo_alternate_outlined),label:Text(photoPaths.isEmpty?'Añadir fotos':'Añadir más fotos')),const SizedBox(height:14),
    _sectionCard(context,'Resultado de la compra',Icons.trending_up,[Text('Costo real: ${money(number(storeCost.text))}'),Text(assigned?'Cobrado al cliente: ${money(number(clientTotal.text))}':'Cobro al cliente pendiente de asociación'),Text(assigned?'Margen del agente: ${money(profit)}':'Margen del agente: pendiente',style:const TextStyle(fontWeight:FontWeight.bold)),const Text('El costo real pertenece a Alas Cargo y se liquida aparte; no se descuenta dos veces de tu margen.')]),const SizedBox(height:14),FilledButton.icon(onPressed:save,icon:const Icon(Icons.save),label:const Text('Guardar pedido'))
  ]));}
}
