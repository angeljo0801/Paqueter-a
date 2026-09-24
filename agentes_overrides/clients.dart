part of 'main.dart';

String _normalizeClientPhone(String value) =>
    value.replaceAll(RegExp(r'[^0-9+]'), '').replaceFirst(RegExp(r'^00'), '+');

String _contactPhone(Contact contact) {
  if (contact.phones.isEmpty) return '';
  for (final phone in contact.phones) {
    if (phone.isPrimary == true) return phone.number.trim();
  }
  return contact.phones.first.number.trim();
}

String _contactEmail(Contact contact) {
  if (contact.emails.isEmpty) return '';
  for (final email in contact.emails) {
    if (email.isPrimary == true) return email.address.trim();
  }
  return contact.emails.first.address.trim();
}

class ContactImportPage extends StatefulWidget {
  final List<Contact> contacts;
  const ContactImportPage({super.key, required this.contacts});
  @override State<ContactImportPage> createState()=>_ContactImportPageState();
}

class _ContactImportPageState extends State<ContactImportPage> {
  final selected=<String>{}; String q='';
  String _key(Contact c,int index)=>c.id??'${c.displayName??''}|${_contactPhone(c)}|$index';
  @override Widget build(BuildContext context){
    final query=q.trim().toLowerCase();
    final filtered=widget.contacts.where((c)=>'${c.displayName??''} ${_contactPhone(c)} ${_contactEmail(c)}'.toLowerCase().contains(query)).toList();
    return Scaffold(
      appBar:AppBar(title:const Text('Importar contactos'),actions:[TextButton(onPressed:filtered.isEmpty?null:(){setState((){final visible=<String>{};for(var i=0;i<widget.contacts.length;i++){final c=widget.contacts[i];if(filtered.contains(c))visible.add(_key(c,i));}final all=visible.isNotEmpty&&visible.every(selected.contains);if(all){selected.removeAll(visible);}else{selected.addAll(visible);}});},child:const Text('Todos'))]),
      body:Column(children:[
        Padding(padding:const EdgeInsets.all(12),child:TextField(onChanged:(v)=>setState(()=>q=v),decoration:const InputDecoration(prefixIcon:Icon(Icons.search),hintText:'Buscar en tus contactos'))),
        Expanded(child:filtered.isEmpty?const Center(child:Text('No hay contactos que mostrar.')):ListView.builder(itemCount:filtered.length,itemBuilder:(_,index){final c=filtered[index];final original=widget.contacts.indexOf(c);final key=_key(c,original);final phone=_contactPhone(c),email=_contactEmail(c);final subtitle=[if(phone.isNotEmpty)phone,if(email.isNotEmpty)email].join('\n');return CheckboxListTile(value:selected.contains(key),onChanged:(v)=>setState((){if(v==true){selected.add(key);}else{selected.remove(key);}}),secondary:const CircleAvatar(child:Icon(Icons.person_outline)),title:Text((c.displayName??'').trim().isEmpty?'Sin nombre':c.displayName!.trim()),subtitle:subtitle.isEmpty?null:Text(subtitle));})),
      ]),
      floatingActionButton:FloatingActionButton.extended(onPressed:selected.isEmpty?null:(){final chosen=<Contact>[];for(var i=0;i<widget.contacts.length;i++){final c=widget.contacts[i];if(selected.contains(_key(c,i)))chosen.add(c);}Navigator.pop(context,chosen);},icon:const Icon(Icons.person_add_alt_1),label:Text('Crear ${selected.length} cliente(s)')),
    );
  }
}

class ClientsPage extends StatefulWidget { const ClientsPage({super.key}); @override State<ClientsPage> createState()=>_ClientsPageState(); }
class _ClientsPageState extends State<ClientsPage> {
  List<Map<String,dynamic>> rows=[]; String q=''; bool importing=false;
  @override void initState(){super.initState();load();}
  Future<void> load() async { rows=active(await Store.list('clients')); if(mounted)setState((){}); }

  Future<void> importFromContacts() async {
    if(importing)return;setState(()=>importing=true);
    try{
      final status=await FlutterContacts.permissions.request(PermissionType.read);
      final allowed=status==PermissionStatus.granted||status==PermissionStatus.limited;
      if(!allowed){
        if(!mounted)return;
        final openSettings=await showDialog<bool>(context:context,builder:(_)=>AlertDialog(title:const Text('Permiso de contactos'),content:const Text('Agentes necesita permiso para leer tus contactos solo cuando quieras importar clientes.'),actions:[TextButton(onPressed:()=>Navigator.pop(context,false),child:const Text('Cancelar')),FilledButton(onPressed:()=>Navigator.pop(context,true),child:const Text('Abrir ajustes'))]));
        if(openSettings==true)await FlutterContacts.permissions.openSettings();
        return;
      }
      final contacts=await FlutterContacts.getAll(properties:{ContactProperty.name,ContactProperty.phone,ContactProperty.email});
      contacts.sort((a,b)=>(a.displayName??'').toLowerCase().compareTo((b.displayName??'').toLowerCase()));
      if(!mounted)return;
      final chosen=await Navigator.push<List<Contact>>(context,MaterialPageRoute(builder:(_)=>ContactImportPage(contacts:contacts)));
      if(chosen==null||chosen.isEmpty)return;
      final allRows=await Store.list('clients');final live=active(allRows);
      final phones=live.map((e)=>_normalizeClientPhone('${e['phone']??''}')).where((e)=>e.isNotEmpty).toSet();
      final emails=live.map((e)=>'${e['email']??''}'.trim().toLowerCase()).where((e)=>e.isNotEmpty).toSet();
      var created=0,duplicates=0,withoutName=0;
      for(final c in chosen){
        final n=(c.displayName??'').trim();if(n.isEmpty){withoutName++;continue;}
        final p=_contactPhone(c),em=_contactEmail(c),np=_normalizeClientPhone(p),ne=em.trim().toLowerCase();
        final duplicate=(np.isNotEmpty&&phones.contains(np))||(ne.isNotEmpty&&emails.contains(ne));if(duplicate){duplicates++;continue;}
        allRows.add({'id':newId(),'name':n,'phone':p,'email':em,'notes':'Importado desde contactos','recipientName':'','recipientPhone':'','recipientAddress':'','deleted':false});
        if(np.isNotEmpty)phones.add(np);if(ne.isNotEmpty)emails.add(ne);created++;
      }
      if(created>0){await Store.saveList('clients',allRows);await load();}
      if(!mounted)return;final details=<String>['$created cliente(s) creado(s)',if(duplicates>0)'$duplicates duplicado(s) omitido(s)',if(withoutName>0)'$withoutName sin nombre omitido(s)'];ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text(details.join(' · '))));
    }finally{if(mounted)setState(()=>importing=false);}
  }

  @override Widget build(BuildContext context){ final f=rows.where((e)=>'${e['name']} ${e['phone']} ${e['email']??''} ${e['recipientName']}'.toLowerCase().contains(q.toLowerCase())).toList(); return Scaffold(
    appBar:AppBar(title:const Text('Mis clientes'),actions:[IconButton(tooltip:'Crear clientes desde contactos',onPressed:importing?null:importFromContacts,icon:importing?const SizedBox(width:20,height:20,child:CircularProgressIndicator(strokeWidth:2)):const Icon(Icons.contacts_outlined))]),
    body:Column(children:[Padding(padding:const EdgeInsets.all(12),child:TextField(onChanged:(v)=>setState(()=>q=v),decoration:const InputDecoration(prefixIcon:Icon(Icons.search),hintText:'Nombre, teléfono, correo o destinatario'))),Expanded(child:f.isEmpty?const Center(child:Text('No hay clientes.')):ListView.builder(itemCount:f.length,itemBuilder:(_,i){final c=f[i];final phone='${c['phone']??''}'.trim(),email='${c['email']??''}'.trim();final contact=[if(phone.isNotEmpty)phone,if(email.isNotEmpty)email].join(' · ');return ListTile(leading:const CircleAvatar(child:Icon(Icons.person)),title:Text('${c['name']}'),subtitle:Text('${contact.isEmpty?'Sin teléfono':contact}\nCuba: ${c['recipientName']??''}'),isThreeLine:true,onTap:()async{await Navigator.push(context,MaterialPageRoute(builder:(_)=>ClientEditPage(existing:c)));load();},trailing:IconButton(icon:const Icon(Icons.delete_outline),onPressed:()async{if(await confirmDelete(context,'este cliente')){await softDelete('clients','${c['id']}');load();}}));}))]),
    floatingActionButton:FloatingActionButton.extended(onPressed:()async{await Navigator.push(context,MaterialPageRoute(builder:(_)=>const ClientEditPage()));load();},icon:const Icon(Icons.add),label:const Text('Cliente')),
  );}
}

class ClientEditPage extends StatefulWidget { final Map<String,dynamic>? existing; const ClientEditPage({super.key,this.existing}); @override State<ClientEditPage> createState()=>_ClientEditPageState(); }
class _ClientEditPageState extends State<ClientEditPage>{
  final name=TextEditingController(),phone=TextEditingController(),email=TextEditingController(),notes=TextEditingController(),recipient=TextEditingController(),recipientPhone=TextEditingController(),address=TextEditingController();
  @override void initState(){super.initState();final e=widget.existing;name.text='${e?['name']??''}';phone.text='${e?['phone']??''}';email.text='${e?['email']??''}';notes.text='${e?['notes']??''}';recipient.text='${e?['recipientName']??''}';recipientPhone.text='${e?['recipientPhone']??''}';address.text='${e?['recipientAddress']??''}';}
  Future<void> save() async { if(name.text.trim().isEmpty)return; await upsert('clients',{'id':widget.existing?['id']??newId(),'name':name.text.trim(),'phone':phone.text.trim(),'email':email.text.trim(),'notes':notes.text.trim(),'recipientName':recipient.text.trim(),'recipientPhone':recipientPhone.text.trim(),'recipientAddress':address.text.trim(),'deleted':false}); if(mounted)Navigator.pop(context); }
  @override Widget build(BuildContext context)=>Scaffold(appBar:AppBar(title:Text(widget.existing==null?'Nuevo cliente':'Editar cliente')),body:ListView(padding:const EdgeInsets.all(16),children:[TextField(controller:name,decoration:const InputDecoration(labelText:'Nombre *')),const SizedBox(height:10),TextField(controller:phone,keyboardType:TextInputType.phone,decoration:const InputDecoration(labelText:'Teléfono / WhatsApp')),const SizedBox(height:10),TextField(controller:email,keyboardType:TextInputType.emailAddress,decoration:const InputDecoration(labelText:'Correo')),const SizedBox(height:18),Text('Destinatario en Cuba',style:Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight:FontWeight.bold)),const SizedBox(height:10),TextField(controller:recipient,decoration:const InputDecoration(labelText:'Nombre del destinatario')),const SizedBox(height:10),TextField(controller:recipientPhone,keyboardType:TextInputType.phone,decoration:const InputDecoration(labelText:'Teléfono en Cuba')),const SizedBox(height:10),TextField(controller:address,maxLines:2,decoration:const InputDecoration(labelText:'Dirección')),const SizedBox(height:10),TextField(controller:notes,maxLines:3,decoration:const InputDecoration(labelText:'Notas')),const SizedBox(height:18),FilledButton.icon(onPressed:save,icon:const Icon(Icons.save),label:const Text('Guardar cliente'))]));
}
