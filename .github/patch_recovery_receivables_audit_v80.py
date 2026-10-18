from pathlib import Path

# v80: The home "Por cobrar" previously added the entire clientTotal of a
# multi-client purchase to the primary customer, and included not-yet-bought
# orders, cancellations, and pending refunds. Use *one* chargeable allocation
# rule for home, client list/detail, finance snapshot and drill-down. Existing
# purchases/payments are READ ONLY; never auto-settle, edit or delete them.

main=Path('app/lib/main.dart')
s=main.read_text()

a=s.index('double clientDue(String clientId,')
b=s.index('\n}',a)+2
old=s[a:b]
assert 'purchaseAmountForClient' in old, 'v80: multi-client support missing'
replacement=r'''// Only purchased/completed work is currently receivable. A not-yet-bought
// order is not a charge, and canceled/refund-in-progress purchases are not
// new money owed by a client. "Cerrado" is still chargeable if no payment was
// recorded: closing an order is not proof that a customer paid it.
bool purchaseHasCollectibleCharge(Map<String, dynamic> purchase) {
  if (purchase['deleted'] == true) return false;
  final status=(purchase['status'] ?? '').toString()
      .trim().toLowerCase();
  return status != 'pendiente de comprar' &&
      status != 'cancelado' &&
      status != 'reembolso pendiente' &&
      status != 'pending purchase' &&
      status != 'cancelled' &&
      status != 'canceled' &&
      status != 'refund pending';
}

double purchaseCollectibleForClient(
  Map<String, dynamic> purchase, String clientId,
) {
  if (!purchaseHasCollectibleCharge(purchase)) return 0;
  return purchaseAmountForClient(purchase, clientId);
}

double clientDue(
  String clientId,
  List<Map<String, dynamic>> purchases,
  List<Map<String, dynamic>> payments,
) {
  final owed = purchases.fold<double>(0,
    (total, purchase) =>
        total + purchaseCollectibleForClient(purchase, clientId));
  final paid = payments.where((payment) =>
      payment['deleted'] != true &&
      (payment['clientId'] ?? '').toString() == clientId)
    .fold<double>(0,(total,payment)=>total+number(payment['amount']));
  // Signed value deliberately preserves customer credit (overpayments).
  return owed-paid;
}

// Receivables are sums of POSITIVE customer balances; another customer's
// overpayment does not cancel a debt from a different customer.
double totalClientReceivables(
  List<Map<String, dynamic>> clients,
  List<Map<String, dynamic>> purchases,
  List<Map<String, dynamic>> payments,
) {
  return clients.where((client)=>client['deleted']!=true)
      .fold<double>(0,(total,client){
    final balance=clientDue((client['id'] ?? '').toString(),
      purchases,payments);
    return total+(balance>0.005?balance:0);
  });
}'''
s=s[:a]+replacement+s[b:]

old="    final due = clients.fold<double>(0, (a, c) => a + clientDue('"
assert s.count(old)==1, 'v80: dashboard total expression changed'
line=next(line for line in s.splitlines() if line.startswith(old))
s=s.replace(line,"    final due = totalClientReceivables(clients, purchases, payments);",1)

needle="              _stat('Por cobrar', money(due), Icons.payments),"
assert s.count(needle)==1,'v80: receivables card changed'
s=s.replace(needle,
"""              _stat('Por cobrar', money(due), Icons.payments,
                  onTap: _showReceivablesDetails),""",1)

a=s.index('  Widget _stat(String label, String value, IconData icon)')
b=s.index('  Widget _tripSummary(',a)
old=s[a:b]
assert 'Card(' in old and "Text(label)" in old
new=r'''  Widget _stat(
    String label,String value,IconData icon,{VoidCallback? onTap}
  ) => Card(
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap:onTap,
      child:Padding(
        padding:const EdgeInsets.all(12),
        child:Column(
          crossAxisAlignment:CrossAxisAlignment.start,
          children:[
            Icon(icon),
            const Spacer(),
            Text(value,style:const TextStyle(
              fontSize:20,fontWeight:FontWeight.bold)),
            Row(children:[
              Expanded(child:Text(label)),
              if(onTap!=null)const Icon(Icons.info_outline,size:17),
            ]),
          ],
        ),
      ),
    ),
  );

  Future<void> _showReceivablesDetails() async {
    try {
      // Read the most recent local records to avoid a misleading snapshot.
      final source=await Future.wait([
        Store.list('clients',forceRefresh:true),
        Store.list('purchases',forceRefresh:true),
        Store.list('payments',forceRefresh:true),
      ]);
      if(!mounted)return;
      final allClients=active(source[0]);
      final allPurchases=active(source[1]);
      final allPayments=active(source[2]);
      final outstanding=<Map<String,dynamic>>[];
      for(final client in allClients){
        final id=(client['id'] ?? '').toString();
        final billable=allPurchases.where((p)=>
            purchaseCollectibleForClient(p,id)>0).toList();
        final charged=billable.fold<double>(0,(total,p)=>
            total+purchaseCollectibleForClient(p,id));
        final paymentsForClient=allPayments.where((p)=>
            (p['clientId'] ?? '').toString()==id).toList();
        final paid=paymentsForClient.fold<double>(0,(total,p)=>
            total+number(p['amount']));
        final balance=charged-paid;
        if(balance<=0.005)continue;
        outstanding.add({
          'name':(client['name'] ?? '').toString(),
          'charged':charged,
          'paid':paid,
          'balance':balance,
          'purchases':billable,
          'payments':paymentsForClient,
          'id':id,
        });
      }
      outstanding.sort((a,b)=>
          (b['balance'] as double).compareTo(a['balance'] as double));
      final total=outstanding.fold<double>(0,(amount,row)=>
          amount+number(row['balance']));
      if(!mounted)return;
      await showModalBottomSheet<void>(
        context:context,
        isScrollControlled:true,
        showDragHandle:true,
        builder:(sheetContext)=>SafeArea(
          child:FractionallySizedBox(
            heightFactor:.82,
            child:ListView(
              padding:const EdgeInsets.all(16),
              children:[
                Text('Desglose de dinero por cobrar',
                  style:Theme.of(sheetContext).textTheme.titleLarge),
                const SizedBox(height:8),
                Text(money(total),style:
                  Theme.of(sheetContext).textTheme.headlineMedium),
                const SizedBox(height:8),
                const Text('Se incluyen compras realizadas y cerradas. '
                  'No se cuentan pedidos por comprar, cancelados ni '
                  'reembolsos pendientes. Los pagos registrados se descuentan '
                  'del cliente correspondiente.'),
                const SizedBox(height:12),
                if(outstanding.isEmpty)
                  const ListTile(title:Text(
                    'No hay importes positivos pendientes de cobro.')),
                for(final row in outstanding)
                  Card(child:ExpansionTile(
                    title:Text((row['name'] ?? '').toString()),
                    subtitle:Text('Cargos: '+money(number(row['charged']))+
                      ' · Pagos: '+money(number(row['paid']))),
                    trailing:Text(money(number(row['balance'])),
                      style:const TextStyle(fontWeight:FontWeight.bold)),
                    children:[
                      for(final p in
                        (row['purchases'] as List<Map<String,dynamic>>))
                        ListTile(
                          dense:true,
                          title:Text((p['store'] ?? 'Compra').toString()),
                          subtitle:Text(
                            (p['orderNumber'] ?? p['description'] ?? '')
                              .toString()+
                            ' · '+(p['status'] ?? '').toString()),
                          trailing:Text(money(
                            purchaseCollectibleForClient(p,
                              (row['id'] ?? '').toString()))),
                        ),
                      for(final payment in
                        (row['payments'] as List<Map<String,dynamic>>))
                        ListTile(
                          dense:true,
                          leading:const Icon(Icons.payments_outlined,size:18),
                          title:Text('Pago registrado'),
                          subtitle:Text((payment['date'] ?? '').toString()),
                          trailing:Text('−'+money(number(payment['amount']))),
                        ),
                    ],
                  )),
                const SizedBox(height:14),
                const Text('Si una compra aparece como pendiente aunque '
                  'ya se pagó, verifica que el pago esté registrado '
                  'en el cliente correcto.'),
              ],
            ),
          ),
        ),
      );
    } catch(error) {
      if(!mounted)return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content:Text('No se pudo leer el desglose: '+error.toString()),
      ));
    }
  }

'''
s=s[:a]+new+s[b:]
assert "Por cobrar', money(due), Icons.payments" in s
assert 'totalClientReceivables(clients, purchases, payments)' in s
main.write_text(s)

# Match all client balances with the same collectible-purchase policy.
p=Path('app/lib/clients.dart')
s=p.read_text()
a=s.index('class _ClientDetailPageState extends State<ClientDetailPage> {')
b=s.index('    final clientEmail =',a)
part=s[a:b]
needle='    final due = purchases.fold<double>('
assert part.count(needle)==1,'v80: client detail balance moved'
start=part.index(needle)
part=part[:start]+"    final due = clientDue(widget.clientId,purchases,payments);\n"
s=s[:a]+part+s[b:]
p.write_text(s)

# Finance snapshot must match dashboard; keep customer credits in the signed
# 'balance' field but sum only positive balances for receivables.
p=Path('app/lib/extras.dart')
s=p.read_text()
old='final owed = purchases.fold<double>(0, (sum, p) => sum + purchaseAmountForClient(p, id));'
assert s.count(old)==1,'v80: finance balance policy changed'
s=s.replace(old,
'final owed = purchases.fold<double>(0, (sum, p) => sum + purchaseCollectibleForClient(p, id));',1)
p.write_text(s)

print('v80: receivables now use allocated bought-order charges less actual payments; dashboard and finance agree, with itemized audit.')
