from pathlib import Path

p = Path('app/lib/extras.dart')
s = p.read_text()

s = s.replace(
    "  bool loaded=false;\n  bool syncing=false;",
    "  bool loaded=false;\n  bool syncing=false;\n  bool apiKeyLoaded=false;\n  String settingsLoadMessage='';",
    1,
)

old_load = """  Future<void>load()async{
    final settings=await Store.settings();
    rate.text='${settings['ratePerLb']}';
    commission.text='${settings['purchaseCommissionPct']}';
    weightRule='${settings['weightRule']}';
    whatsBotSyncEnabled=settings['whatsBotSyncEnabled']!=false;
    whatsBotUrl.text='${settings['whatsBotBackendUrl']??'https://wasbot-backend-production.up.railway.app'}';
    whatsBotKey.text=await WhatsBotPurchaseSyncService.apiKey();
    if(mounted)setState(()=>loaded=true);
  }
"""

new_load = """  Future<void>load()async{
    Map<String,dynamic> settings;
    try{
      settings=await Store.settings().timeout(const Duration(seconds:4));
    }catch(_){
      settings=<String,dynamic>{
        'ratePerLb':5.0,
        'purchaseCommissionPct':0.0,
        'weightRule':'manual',
        'whatsBotSyncEnabled':true,
        'whatsBotBackendUrl':'https://wasbot-backend-production.up.railway.app',
      };
      settingsLoadMessage='La configuración local tardó demasiado. Se muestran valores seguros para que la pantalla no quede bloqueada.';
    }
    if(!mounted)return;
    rate.text='${settings['ratePerLb']??5.0}';
    commission.text='${settings['purchaseCommissionPct']??0.0}';
    weightRule='${settings['weightRule']??'manual'}';
    whatsBotSyncEnabled=settings['whatsBotSyncEnabled']!=false;
    whatsBotUrl.text='${settings['whatsBotBackendUrl']??'https://wasbot-backend-production.up.railway.app'}';
    setState(()=>loaded=true);

    // FlutterSecureStorage can occasionally block while Android is returning
    // from another app/share flow. Never keep the whole Settings screen waiting
    // for it. Load the key separately and preserve the existing key on failure.
    try{
      final key=await WhatsBotPurchaseSyncService.apiKey()
          .timeout(const Duration(seconds:4));
      if(!mounted)return;
      whatsBotKey.text=key;
      setState((){
        apiKeyLoaded=true;
        settingsLoadMessage='';
      });
    }catch(_){
      if(mounted){
        setState(()=>settingsLoadMessage=
          'No pude leer la APP_API_KEY ahora mismo. La clave guardada se conservará y no se borrará.');
      }
    }
  }
"""

if old_load not in s:
    raise SystemExit('SettingsPage.load block not found')
s = s.replace(old_load, new_load, 1)

old_save = """  Future<void>save()async{
    final settings=await Store.settings();
    settings['ratePerLb']=number(rate.text);
    settings['purchaseCommissionPct']=number(commission.text);
    settings['weightRule']=weightRule;
    await Store.saveSettings(settings);
    await WhatsBotPurchaseSyncService.configure(
      enabled:whatsBotSyncEnabled,
      url:whatsBotUrl.text,
      key:whatsBotKey.text,
    );
    if(mounted){
"""

new_save = """  Future<void>save()async{
    final settings=await Store.settings();
    settings['ratePerLb']=number(rate.text);
    settings['purchaseCommissionPct']=number(commission.text);
    settings['weightRule']=weightRule;
    settings['whatsBotSyncEnabled']=whatsBotSyncEnabled;
    final cleanUrl=whatsBotUrl.text.trim().replaceAll(RegExp(r'/$'),'');
    settings['whatsBotBackendUrl']=cleanUrl.isEmpty
      ? 'https://wasbot-backend-production.up.railway.app'
      : cleanUrl;
    await Store.saveSettings(settings);
    // If secure storage did not answer during load, never overwrite/delete the
    // existing API key with an empty field.
    if(apiKeyLoaded){
      await WhatsBotPurchaseSyncService.saveApiKey(whatsBotKey.text);
    }
    if(mounted){
"""

if old_save not in s:
    raise SystemExit('SettingsPage.save block not found')
s = s.replace(old_save, new_save, 1)

s = s.replace(
    "    if(!loaded)return const Scaffold(body:Center(child:CircularProgressIndicator()));",
    "    if(!loaded)return Scaffold(appBar:AppBar(title:const Text('Configuración del negocio')),body:const Center(child:CircularProgressIndicator()));",
    1,
)

needle = """          const SizedBox(height:12),
          OutlinedButton.icon(
            onPressed:syncing?null:syncNow,
"""
insert = """          const SizedBox(height:8),
          if(settingsLoadMessage.isNotEmpty)
            Card(
              child:Padding(
                padding:const EdgeInsets.all(12),
                child:Row(
                  crossAxisAlignment:CrossAxisAlignment.start,
                  children:[
                    const Icon(Icons.info_outline),
                    const SizedBox(width:10),
                    Expanded(child:Text(settingsLoadMessage)),
                    IconButton(
                      tooltip:'Reintentar',
                      onPressed:load,
                      icon:const Icon(Icons.refresh),
                    ),
                  ],
                ),
              ),
            ),
          const SizedBox(height:12),
          OutlinedButton.icon(
            onPressed:syncing?null:syncNow,
"""
if needle not in s:
    raise SystemExit('Settings sync button marker not found')
s = s.replace(needle, insert, 1)

p.write_text(s)
