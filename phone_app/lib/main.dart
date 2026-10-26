import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

// Telefon tarafının asıl işi Kotlin'de (Firebase mesajı -> arama/alarm). Bu ekran yalnızca durum ve kurulum içindir.
const _ch = MethodChannel('jarvis/native');

void main() => runApp(const JarvisApp());

class JarvisApp extends StatelessWidget {
  const JarvisApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Jarvis Telefon',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.cyan, brightness: Brightness.dark),
      ),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver {
  Map<String, dynamic> st = {};
  String tokenMsg = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _refresh();
    _loadToken();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();
  }

  Future<void> _refresh() async {
    try {
      final m = await _ch.invokeMapMethod<String, dynamic>('status');
      if (mounted) setState(() => st = m ?? {});
    } catch (e) {
      if (mounted) setState(() => tokenMsg = 'Durum okunamadı: $e');
    }
  }

  Future<void> _loadToken() async {
    try {
      final t = await _ch.invokeMethod<String>('token');
      if (!mounted) return;
      setState(() => tokenMsg = (t ?? '').startsWith('HATA') ? t! : '');
      _refresh();
    } catch (e) {
      if (mounted) setState(() => tokenMsg = 'Belirteç alınamadı: $e');
    }
  }

  Future<void> _call(String m) async {
    await _ch.invokeMethod(m);
    await Future.delayed(const Duration(milliseconds: 800));
    _refresh();
  }

  bool _b(String k) => st[k] == true;

  Widget _row(String title, bool ok, {String? hint, String? action, VoidCallback? onTap}) {
    return ListTile(
      leading: Icon(ok ? Icons.check_circle : Icons.error_outline, color: ok ? Colors.greenAccent : Colors.orangeAccent),
      title: Text(title),
      subtitle: hint == null || ok ? null : Text(hint),
      trailing: (!ok && action != null) ? FilledButton.tonal(onPressed: onTap, child: Text(action)) : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    final token = (st['token'] ?? '') as String;
    final log = ((st['log'] ?? <dynamic>[]) as List).cast<String>();
    return Scaffold(
      appBar: AppBar(title: const Text('Jarvis Telefon')),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: [
            _row('Bilgisayarla eşleşti', _b('paired'),
                hint: 'Bilgisayarda: python tools/phone_check.py --app-pair (telefon USB ya da kablosuz ADB ile bağlı olmalı)'),
            _row('Firebase belirteci alındı', token.isNotEmpty,
                hint: tokenMsg.isEmpty ? 'İnternet ve Google Play hizmetleri gerekir' : tokenMsg,
                action: 'Yenile', onTap: _loadToken),
            const Divider(),
            _row('Arama izni', _b('call'), hint: 'Jarvis\'in rehberdeki kişileri aramasını sağlar', action: 'İzin ver', onTap: () => _call('requestPermissions')),
            _row('Rehber izni', _b('contacts'), hint: 'Kişi adından numarayı telefonun kendisi bulur; numara dışarı çıkmaz', action: 'İzin ver', onTap: () => _call('requestPermissions')),
            _row('Aramayı kapatma izni', _b('answer'), action: 'İzin ver', onTap: () => _call('requestPermissions')),
            _row('Bildirim izni', _b('notify'), hint: 'Alarm ve bilgi bildirimleri için', action: 'İzin ver', onTap: () => _call('requestPermissions')),
            _row('Pil kısıtlaması kapalı', _b('battery'),
                hint: 'Xiaomi, arka plandaki uygulamaları kapatır; mesajlar gecikmesin diye kapat', action: 'Kapat', onTap: () => _call('openBattery')),
            ListTile(
              leading: const Icon(Icons.rocket_launch_outlined),
              title: const Text('Otomatik başlatma (Xiaomi)'),
              subtitle: const Text('Açık olmalı; yoksa telefon yeniden başlayınca ya da uygulama kapatılınca mesaj gelmeyebilir'),
              trailing: FilledButton.tonal(onPressed: () => _call('openAutostart'), child: const Text('Aç')),
            ),
            const Divider(),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              children: [
                OutlinedButton.icon(onPressed: () => _call('testAlarm'), icon: const Icon(Icons.alarm), label: const Text('Alarmı dene')),
                OutlinedButton.icon(onPressed: () => _call('stopAlarm'), icon: const Icon(Icons.alarm_off), label: const Text('Alarmı sustur')),
                OutlinedButton.icon(
                  onPressed: token.isEmpty
                      ? null
                      : () async {
                          await Clipboard.setData(ClipboardData(text: token));
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Belirteç kopyalandı')));
                          }
                        },
                  icon: const Icon(Icons.copy),
                  label: const Text('Belirteci kopyala'),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text('Son olaylar', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            if (log.isEmpty) const Text('Henüz yok.', style: TextStyle(color: Colors.grey)),
            for (final l in log) Padding(padding: const EdgeInsets.symmetric(vertical: 2), child: Text(l, style: const TextStyle(fontSize: 12, fontFamily: 'monospace'))),
          ],
        ),
      ),
    );
  }
}
