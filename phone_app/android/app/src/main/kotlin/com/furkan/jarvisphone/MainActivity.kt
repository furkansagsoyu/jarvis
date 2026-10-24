package com.furkan.jarvisphone

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import com.google.firebase.messaging.FirebaseMessaging
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private fun stopAlarmIfAsked(i: Intent?) {
        if (i?.getBooleanExtra("stop_alarm", false) == true) stopService(Intent(this, AlarmService::class.java))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        stopAlarmIfAsked(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        stopAlarmIfAsked(intent)
    }

    private fun granted(p: String) = checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED

    @Suppress("DEPRECATION")
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        Commands.ensureChannels(this)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "jarvis/native").setMethodCallHandler { call, result ->
            when (call.method) {
                "status" -> {
                    val pm = getSystemService(PowerManager::class.java)
                    result.success(
                        mapOf(
                            "paired" to Prefs.secret(this).isNotEmpty(),
                            "token" to Prefs.token(this),
                            "call" to granted(Manifest.permission.CALL_PHONE),
                            "contacts" to granted(Manifest.permission.READ_CONTACTS),
                            "answer" to granted(Manifest.permission.ANSWER_PHONE_CALLS),
                            "notify" to (android.os.Build.VERSION.SDK_INT < 33 || granted(Manifest.permission.POST_NOTIFICATIONS)),
                            "battery" to pm.isIgnoringBatteryOptimizations(packageName),
                            "log" to Prefs.logLines(this)
                        )
                    )
                }
                "requestPermissions" -> {
                    val list = mutableListOf(
                        Manifest.permission.CALL_PHONE,
                        Manifest.permission.READ_CONTACTS,
                        Manifest.permission.ANSWER_PHONE_CALLS
                    )
                    if (android.os.Build.VERSION.SDK_INT >= 33) list.add(Manifest.permission.POST_NOTIFICATIONS)
                    requestPermissions(list.toTypedArray(), 1)
                    result.success(null)
                }
                "token" -> {
                    FirebaseMessaging.getInstance().token.addOnCompleteListener { t ->
                        if (t.isSuccessful && !t.result.isNullOrEmpty()) {
                            Prefs.setToken(this, t.result)
                            android.util.Log.i("JarvisPhone", "TOKEN=${t.result}")
                            result.success(t.result)
                        } else {
                            result.success("HATA: ${t.exception?.message ?: "belirteç alınamadı (Google Play hizmetleri / internet?)"}")
                        }
                    }
                }
                "openBattery" -> {
                    try {
                        startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
                    } catch (e: Exception) {
                        startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    }
                    result.success(null)
                }
                "openAutostart" -> {
                    try {
                        startActivity(
                            Intent().setComponent(
                                ComponentName("com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity")
                            )
                        )
                    } catch (e: Exception) {
                        startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
                    }
                    result.success(null)
                }
                "openAppSettings" -> {
                    startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
                    result.success(null)
                }
                "stopAlarm" -> {
                    stopService(Intent(this, AlarmService::class.java))
                    result.success(null)
                }
                "testAlarm" -> {
                    Commands.showAlarm(this, "test", "Jarvis testi", "Telefon böyle çalacak. Kapatmak için dokun.")
                    Prefs.log(this, "test alarmı")
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }
}
