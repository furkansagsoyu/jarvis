package com.furkan.jarvisphone

import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class JarvisMessagingService : FirebaseMessagingService() {
    @Suppress("OVERRIDE_DEPRECATION")
    override fun onNewToken(token: String) {
        Prefs.setToken(this, token)
        Log.i("JarvisPhone", "TOKEN=$token")
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val result = try {
            Commands.handleSigned(this, message.data)
        } catch (e: Exception) {
            "HATA: ${e.javaClass.simpleName}"
        }
        Prefs.log(this, result)
        Log.i("JarvisPhone", result)
    }
}
