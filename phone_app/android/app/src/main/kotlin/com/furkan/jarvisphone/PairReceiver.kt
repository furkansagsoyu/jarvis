package com.furkan.jarvisphone

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import com.google.firebase.messaging.FirebaseMessaging

/**
 * Eşleştirme (bilgisayar -> telefon), yalnızca ADB kabuğundan (manifestte DUMP izni şartı):
 *   TOKEN: FCM belirtecini logcat'e yazar (bilgisayar okur).
 *   PAIR : gizli anahtarı (64 hane hex) kaydeder.
 */
class PairReceiver : BroadcastReceiver() {
    @Suppress("DEPRECATION")
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            "com.furkan.jarvisphone.TOKEN" -> {
                val pending = goAsync()
                FirebaseMessaging.getInstance().token.addOnCompleteListener { t ->
                    if (t.isSuccessful && !t.result.isNullOrEmpty()) {
                        Prefs.setToken(context, t.result)
                        Log.i("JarvisPhone", "TOKEN=${t.result}")
                    } else {
                        Log.i("JarvisPhone", "TOKEN_HATA=${t.exception?.javaClass?.simpleName}")
                    }
                    pending.finish()
                }
            }
            "com.furkan.jarvisphone.PAIR" -> {
                val s = intent.getStringExtra("secret") ?: ""
                if (Regex("^[0-9a-f]{64}$").matches(s)) {
                    Prefs.setSecret(context, s)
                    Prefs.log(context, "eşleştirildi")
                    Log.i("JarvisPhone", "PAIRED_OK")
                } else {
                    Log.i("JarvisPhone", "PAIRED_HATA")
                }
            }
        }
    }
}
