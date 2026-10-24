package com.furkan.jarvisphone

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Telefon yeniden başlayınca bekleyen alarmları tekrar kurar (AlarmManager kayıtları açılışta silinir). */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val all = Prefs.alarms(context)
        val now = System.currentTimeMillis()
        val keys = all.keys().asSequence().toList()
        for (id in keys) {
            val o = all.getJSONObject(id)
            val at = o.optLong("at")
            if (at > now) Commands.schedule(context, id, at, o.optString("title"), o.optString("body"))
            else Prefs.removeAlarm(context, id)
        }
    }
}
