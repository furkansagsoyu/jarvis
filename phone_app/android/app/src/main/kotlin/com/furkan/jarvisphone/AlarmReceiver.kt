package com.furkan.jarvisphone

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class AlarmReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getStringExtra("id") ?: "jarvis"
        Commands.showAlarm(context, id, intent.getStringExtra("title") ?: "Jarvis", intent.getStringExtra("body") ?: "")
        Prefs.removeAlarm(context, id)
        Prefs.log(context, "alarm çaldı")
    }
}
