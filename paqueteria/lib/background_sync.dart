part of 'main.dart';

const String courierBackgroundTask = 'courierBackgroundSync';
const String courierPeriodicWork = 'paqueteria-courier-periodic';
const String gmailBackgroundTask = 'gmailBackgroundReconstruct';

@pragma('vm:entry-point')
void courierCallbackDispatcher() {
  WidgetsFlutterBinding.ensureInitialized();
  Workmanager().executeTask((taskName, inputData) async {
    if (taskName == gmailBackgroundTask) {
      return GmailBackgroundSearch.execute(inputData);
    }
    if (taskName != courierBackgroundTask) return true;
    try {
      await NotificationService.initialize(requestPermission: false);
      await EasyPostService.syncAll();
      await NotificationService.publishPendingCourierChanges();
      await FlightService.syncIfDue();
      await NotificationService.publishPendingFlightChanges();
      await WhatsBotPurchaseSyncService.syncSilently();
      return true;
    } catch (_) {
      return false;
    }
  });
}

class BackgroundCourierSync {
  static Future<void> initializeAndSchedule() async {
    await Workmanager().initialize(courierCallbackDispatcher);
    await schedule();
  }

  static Future<void> schedule() async {
    await Workmanager().registerPeriodicTask(
      courierPeriodicWork,
      courierBackgroundTask,
      frequency: const Duration(minutes: 15),
      constraints: Constraints(networkType: NetworkType.connected),
      existingWorkPolicy: ExistingPeriodicWorkPolicy.update,
      tag: 'courier-sync',
    );
  }

  static Future<void> runSoon() async {
    await Workmanager().registerOneOffTask(
      'paqueteria-courier-now',
      courierBackgroundTask,
      constraints: Constraints(networkType: NetworkType.connected),
      existingWorkPolicy: ExistingWorkPolicy.replace,
      tag: 'courier-sync-now',
    );
  }
}

class GmailBackgroundSearch {
  static String _slot(String orderNumber, String tracking) {
    final raw = tracking.trim().isNotEmpty
        ? 'tracking:${tracking.trim().toLowerCase()}'
        : 'order:${orderNumber.trim().toLowerCase()}';
    var hash = 2166136261;
    for (final code in raw.codeUnits) {
      hash ^= code;
      hash = (hash * 16777619) & 0x7fffffff;
    }
    return hash.toRadixString(16);
  }

  static String _pendingKey(String slot) => 'gmailBackgroundPending_$slot';
  static String _resultKey(String slot) => 'gmailBackgroundResult_$slot';
  static String _errorKey(String slot) => 'gmailBackgroundError_$slot';

  static Future<Map<String, dynamic>> _request({
    required String baseUrl,
    required String apiKey,
    required String orderNumber,
    required String tracking,
  }) async {
    final base = baseUrl.trim().replaceAll(RegExp(r'/$'), '');
    if (base.isEmpty) throw Exception('Falta la URL del servidor de WhatsBot.');
    if (apiKey.trim().isEmpty) {
      throw Exception('Falta la APP_API_KEY de WhatsBot en Configuración.');
    }
    final order = orderNumber.trim();
    final track = tracking.trim();
    if (order.isEmpty && track.isEmpty) {
      throw Exception('Escribe un tracking o número de orden primero.');
    }
    final uri = Uri.parse('$base/api/gmail/reconstruct').replace(
      queryParameters: track.isNotEmpty
          ? {'tracking': track}
          : {'order_number': order},
    );
    final response = await http.get(
      uri,
      headers: {'x-api-key': apiKey.trim()},
    ).timeout(const Duration(seconds: 90));
    if (response.statusCode != 200) {
      String detail = response.body;
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map && decoded['detail'] != null) {
          detail = '${decoded['detail']}';
        }
      } catch (_) {}
      throw Exception(detail);
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map) throw Exception('Respuesta inválida del servidor.');
    return Map<String, dynamic>.from(decoded);
  }

  static Future<Map<String, dynamic>?> _readFinished(
    SharedPreferences prefs,
    String slot,
    String token,
  ) async {
    await prefs.reload();
    final resultRaw = prefs.getString(_resultKey(slot));
    if (resultRaw != null && resultRaw.isNotEmpty) {
      try {
        final wrapped = jsonDecode(resultRaw);
        if (wrapped is Map && '${wrapped['token'] ?? ''}' == token) {
          final data = wrapped['data'];
          if (data is Map) {
            await prefs.remove(_pendingKey(slot));
            await prefs.remove(_resultKey(slot));
            await prefs.remove(_errorKey(slot));
            return Map<String, dynamic>.from(data);
          }
        }
      } catch (_) {}
    }
    final errorRaw = prefs.getString(_errorKey(slot));
    if (errorRaw != null && errorRaw.isNotEmpty) {
      try {
        final wrapped = jsonDecode(errorRaw);
        if (wrapped is Map && '${wrapped['token'] ?? ''}' == token) {
          final message = '${wrapped['error'] ?? 'No se pudo buscar en Gmail.'}';
          await prefs.remove(_pendingKey(slot));
          await prefs.remove(_resultKey(slot));
          await prefs.remove(_errorKey(slot));
          throw Exception(message);
        }
      } catch (e) {
        if (e is Exception) rethrow;
      }
    }
    return null;
  }

  static Future<Map<String, dynamic>> reconstruct({
    String baseUrl = '',
    String apiKey = '',
    String orderNumber = '',
    String tracking = '',
  }) async {
    var base = baseUrl.trim();
    var key = apiKey.trim();
    if (base.isEmpty) base = (await WhatsBotPurchaseSyncService.backendUrl()).trim();
    if (key.isEmpty) key = (await WhatsBotPurchaseSyncService.apiKey()).trim();
    final order = orderNumber.trim();
    final track = tracking.trim();
    if (order.isEmpty && track.isEmpty) {
      throw Exception('Escribe un tracking o número de orden primero.');
    }

    final prefs = await SharedPreferences.getInstance();
    final slot = _slot(order, track);
    final pendingKey = _pendingKey(slot);
    await prefs.reload();

    String token = '';
    final pendingRaw = prefs.getString(pendingKey);
    if (pendingRaw != null && pendingRaw.isNotEmpty) {
      try {
        final pending = jsonDecode(pendingRaw);
        if (pending is Map) token = '${pending['token'] ?? ''}';
      } catch (_) {}
    }

    if (token.isNotEmpty) {
      final recovered = await _readFinished(prefs, slot, token);
      if (recovered != null) return recovered;
    } else {
      token = '${DateTime.now().microsecondsSinceEpoch}';
      await prefs.setString(
        pendingKey,
        jsonEncode({
          'token': token,
          'startedAt': DateTime.now().toIso8601String(),
          'orderNumber': order,
          'tracking': track,
        }),
      );
      await prefs.remove(_resultKey(slot));
      await prefs.remove(_errorKey(slot));
      await Workmanager().registerOneOffTask(
        'paqueteria-gmail-$slot-$token',
        gmailBackgroundTask,
        inputData: {
          'slot': slot,
          'token': token,
          'baseUrl': base,
          'apiKey': key,
          'orderNumber': order,
          'tracking': track,
        },
        constraints: Constraints(networkType: NetworkType.connected),
        existingWorkPolicy: ExistingWorkPolicy.keep,
        tag: 'gmail-background-search',
      );
    }

    // Keep the current screen fast by doing the request immediately too. The
    // WorkManager copy is the safety net: if Android suspends/kills the UI while
    // the user minimizes Paquetería, it continues and saves the result locally.
    try {
      final data = await _request(
        baseUrl: base,
        apiKey: key,
        orderNumber: order,
        tracking: track,
      );
      await prefs.reload();
      final latest = prefs.getString(pendingKey) ?? '';
      if (latest.contains('"token":"$token"')) {
        await prefs.remove(pendingKey);
        await prefs.remove(_resultKey(slot));
        await prefs.remove(_errorKey(slot));
      }
      return data;
    } catch (directError) {
      // Give the background worker a short chance to finish before surfacing an
      // error. If it is still running, its pending record remains recoverable.
      for (var i = 0; i < 12; i++) {
        await Future<void>.delayed(const Duration(seconds: 1));
        final recovered = await _readFinished(prefs, slot, token);
        if (recovered != null) return recovered;
      }
      throw Exception('$directError · La búsqueda seguirá intentando en segundo plano.');
    }
  }

  @pragma('vm:entry-point')
  static Future<bool> execute(Map<String, dynamic>? inputData) async {
    final data = inputData ?? const <String, dynamic>{};
    final slot = '${data['slot'] ?? ''}'.trim();
    final token = '${data['token'] ?? ''}'.trim();
    if (slot.isEmpty || token.isEmpty) return true;
    final prefs = await SharedPreferences.getInstance();
    try {
      final result = await _request(
        baseUrl: '${data['baseUrl'] ?? ''}',
        apiKey: '${data['apiKey'] ?? ''}',
        orderNumber: '${data['orderNumber'] ?? ''}',
        tracking: '${data['tracking'] ?? ''}',
      );
      await prefs.reload();
      final pendingRaw = prefs.getString(_pendingKey(slot)) ?? '';
      if (!pendingRaw.contains('"token":"$token"')) return true;
      await prefs.setString(
        _resultKey(slot),
        jsonEncode({
          'token': token,
          'completedAt': DateTime.now().toIso8601String(),
          'data': result,
        }),
      );
      return true;
    } catch (e) {
      await prefs.reload();
      final pendingRaw = prefs.getString(_pendingKey(slot)) ?? '';
      if (!pendingRaw.contains('"token":"$token"')) return true;
      await prefs.setString(
        _errorKey(slot),
        jsonEncode({
          'token': token,
          'completedAt': DateTime.now().toIso8601String(),
          'error': '$e',
        }),
      );
      return true;
    }
  }
}

class NotificationService {
  static final FlutterLocalNotificationsPlugin _plugin = FlutterLocalNotificationsPlugin();
  static bool _initialized = false;

  static Future<void> initialize({bool requestPermission = false}) async {
    if (!_initialized) {
      const android = AndroidInitializationSettings('@mipmap/ic_launcher');
      const settings = InitializationSettings(android: android);
      await _plugin.initialize(settings: settings);
      _initialized = true;
    }
    if (requestPermission) {
      await _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()?.requestNotificationsPermission();
    }
  }

  static Future<void> publishPendingCourierChanges() async {
    final notices = await Store.list('courierNotifications');
    final clients = active(await Store.list('clients'));
    var dirty = false;
    for (final n in notices) {
      if (n['deleted'] == true || n['notificationSent'] == true) continue;
      final client = clientName(clients, '${n['clientId'] ?? ''}');
      final tracking = '${n['tracking'] ?? ''}';
      final state = '${n['newStatusEs'] ?? 'Actualización de tracking'}';
      final id = (number(n['id']) % 2147483647).toInt();
      const android = AndroidNotificationDetails(
        'courier_updates',
        'Actualizaciones de paquetes',
        channelDescription: 'Cambios de estado de UPS, USPS, FedEx y otros couriers',
        importance: Importance.high,
        priority: Priority.high,
      );
      const details = NotificationDetails(android: android);
      await _plugin.show(
        id: id,
        title: '📦 $client · $state',
        body: tracking.isEmpty ? 'El courier reportó un cambio.' : 'Tracking: $tracking',
        notificationDetails: details,
        payload: '${n['packageId'] ?? ''}',
      );
      n['notificationSent'] = true;
      n['notificationSentAt'] = DateTime.now().toIso8601String();
      dirty = true;
    }
    if (dirty) await Store.saveList('courierNotifications', notices);
  }

  static Future<void> publishPendingFlightChanges() async {
    final notices = await Store.list('flightNotifications');
    var dirty = false;
    for (final n in notices) {
      if (n['deleted'] == true || n['notificationSent'] == true) continue;
      final id = (number(n['id']) % 2147483647).toInt();
      const android = AndroidNotificationDetails(
        'flight_price_updates',
        'Alertas de vuelos baratos',
        channelDescription: 'Avisos cuando una ruta vigilada baja del precio objetivo',
        importance: Importance.high,
        priority: Priority.high,
      );
      const details = NotificationDetails(android: android);
      final route = '${n['origin']} → ${n['destination']}';
      final price = money(number(n['price']));
      final date = '${n['date'] ?? ''}';
      final airline = '${n['airline'] ?? ''}';
      await _plugin.show(
        id: id,
        title: '✈️ Vuelo barato: $route · $price',
        body: '$date${airline.isNotEmpty ? ' · $airline' : ''}',
        notificationDetails: details,
        payload: 'flight:${n['watchId'] ?? ''}',
      );
      n['notificationSent'] = true;
      n['notificationSentAt'] = DateTime.now().toIso8601String();
      dirty = true;
    }
    if (dirty) await Store.saveList('flightNotifications', notices);
  }
}
