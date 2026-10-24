package com.furkan.jarvisphone

import android.Manifest
import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.net.Uri
import android.os.Bundle
import android.provider.ContactsContract
import android.telecom.TelecomManager

/** Bilgisayardan gelen doğrulanmış komutları yürütür: ara, kapat, çal (alarm), iptal. */
object Commands {
    const val CH_ALARM = "jarvis_alarm"
    const val CH_INFO = "jarvis_info"
    private const val MAX_SKEW_S = 120L

    fun ensureChannels(c: Context) {
        val nm = c.getSystemService(NotificationManager::class.java)
        val alarm = NotificationChannel(CH_ALARM, "Jarvis alarmı", NotificationManager.IMPORTANCE_HIGH).apply {
            description = "Toplantı ve hatırlatmalarda yüksek sesle çalar"
            setSound(
                RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM),
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build()
            )
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 600, 300, 600, 300, 600)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            setBypassDnd(true)
        }
        val info = NotificationChannel(CH_INFO, "Jarvis bilgi", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "Jarvis'in yaptığı işlemler"
        }
        nm.createNotificationChannel(alarm)
        nm.createNotificationChannel(info)
    }

    private fun appIntent(c: Context): PendingIntent =
        PendingIntent.getActivity(
            c, 0, Intent(c, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

    private fun canNotify(c: Context): Boolean =
        android.os.Build.VERSION.SDK_INT < 33 ||
            c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    /** Sesli, titreşimli, kapatılana dek tekrar eden bildirim (toplantı alarmı). */
    fun showAlarm(c: Context, id: String, title: String, body: String) {
        ensureChannels(c)
        if (!canNotify(c)) { Prefs.log(c, "bildirim izni yok, alarm gösterilemedi"); return }
        val n = Notification.Builder(c, CH_ALARM)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(title.ifBlank { "Jarvis" })
            .setContentText(body)
            .setCategory(Notification.CATEGORY_ALARM)
            .setAutoCancel(true)
            .setContentIntent(appIntent(c))
            .build()
        n.flags = n.flags or Notification.FLAG_INSISTENT
        c.getSystemService(NotificationManager::class.java).notify(id.hashCode(), n)
    }

    fun showInfo(c: Context, title: String, body: String, tap: PendingIntent? = null) {
        ensureChannels(c)
        if (!canNotify(c)) return
        val b = Notification.Builder(c, CH_INFO)
            .setSmallIcon(android.R.drawable.ic_menu_call)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setContentIntent(tap ?: appIntent(c))
        c.getSystemService(NotificationManager::class.java).notify(("info" + System.nanoTime()).hashCode(), b.build())
    }

    // ------------------------------------------------------------ rehber
    private fun cleanNumber(raw: String): String = raw.filter { it.isDigit() || it == '+' }

    /** Önce tam ad eşleşmesi; yoksa içeren tek bir kişi varsa o. Belirsizse null (yanlış kişiyi aramaktansa aramaz). */
    fun findNumber(c: Context, name: String): String? {
        if (c.checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) return null
        val proj = arrayOf(
            ContactsContract.CommonDataKinds.Phone.NUMBER,
            ContactsContract.CommonDataKinds.Phone.TYPE,
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME
        )
        fun query(sel: String, arg: String): List<Triple<String, Int, String>> {
            val out = mutableListOf<Triple<String, Int, String>>()
            c.contentResolver.query(ContactsContract.CommonDataKinds.Phone.CONTENT_URI, proj, sel, arrayOf(arg), null)?.use { cur ->
                while (cur.moveToNext()) out.add(Triple(cleanNumber(cur.getString(0) ?: ""), cur.getInt(1), cur.getString(2) ?: ""))
            }
            return out.filter { it.first.isNotEmpty() }
        }
        val dn = ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME
        var rows = query("$dn = ? COLLATE NOCASE", name)
        if (rows.isEmpty()) rows = query("$dn LIKE ? ESCAPE '\\'", "%" + name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        if (rows.isEmpty()) return null
        if (rows.map { it.third.lowercase() }.distinct().size > 1) return null
        val mobile = rows.firstOrNull { it.second == ContactsContract.CommonDataKinds.Phone.TYPE_MOBILE }
        return (mobile ?: rows.first()).first
    }

    // ------------------------------------------------------------ komutlar
    @Suppress("DEPRECATION")
    fun call(c: Context, name: String): String {
        val num = findNumber(c, name) ?: return "kişi bulunamadı ya da belirsiz"
        val uri = Uri.fromParts("tel", num, null)
        val dial = PendingIntent.getActivity(
            c, 1, Intent(Intent.ACTION_DIAL, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        if (c.checkSelfPermission(Manifest.permission.CALL_PHONE) != PackageManager.PERMISSION_GRANTED) {
            showInfo(c, "Jarvis arama istedi", "$name – arama izni yok. Dokun, arama ekranı açılsın.", dial)
            return "arama izni yok"
        }
        return try {
            c.getSystemService(TelecomManager::class.java).placeCall(uri, Bundle())
            showInfo(c, "Jarvis aranıyor", name, dial)
            "arama başlatıldı"
        } catch (e: Exception) {
            showInfo(c, "Jarvis arama istedi", "$name – otomatik arama engellendi. Dokun, arama ekranı açılsın.", dial)
            "arama engellendi: ${e.javaClass.simpleName}"
        }
    }

    @Suppress("DEPRECATION")
    fun hangup(c: Context): String {
        if (c.checkSelfPermission(Manifest.permission.ANSWER_PHONE_CALLS) != PackageManager.PERMISSION_GRANTED) return "kapatma izni yok"
        return try {
            if (c.getSystemService(TelecomManager::class.java).endCall()) "arama kapatıldı" else "açık arama yok"
        } catch (e: Exception) {
            "kapatılamadı: ${e.javaClass.simpleName}"
        }
    }

    private fun alarmPending(c: Context, id: String, title: String, body: String): PendingIntent =
        PendingIntent.getBroadcast(
            c, id.hashCode(),
            Intent(c, AlarmReceiver::class.java).putExtra("id", id).putExtra("title", title).putExtra("body", body),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

    /** at (epoch ms) gelecekteyse o ana kurar (telefon uykudayken de çalar); değilse hemen çalar. */
    fun schedule(c: Context, id: String, at: Long, title: String, body: String) {
        val am = c.getSystemService(AlarmManager::class.java)
        am.setAlarmClock(AlarmManager.AlarmClockInfo(at, appIntent(c)), alarmPending(c, id, title, body))
    }

    fun ring(c: Context, id: String, atMs: Long, title: String, body: String): String {
        if (atMs > System.currentTimeMillis() + 2000) {
            Prefs.putAlarm(c, id, atMs, title, body)
            schedule(c, id, atMs, title, body)
            return "alarm kuruldu"
        }
        showAlarm(c, id, title, body)
        return "alarm çalıyor"
    }

    fun cancel(c: Context, id: String): String {
        c.getSystemService(AlarmManager::class.java).cancel(alarmPending(c, id, "", ""))
        Prefs.removeAlarm(c, id)
        c.getSystemService(NotificationManager::class.java).cancel(id.hashCode())
        return "alarm iptal edildi"
    }

    // ------------------------------------------------------------ doğrulama + dağıtım
    /** FCM veri mesajını doğrular ve yürütür. Dönen metin ekrandaki günlüğe yazılır. */
    fun handleSigned(c: Context, d: Map<String, String>): String {
        val secret = Prefs.secret(c)
        if (secret.isEmpty()) return "REDDEDİLDİ: telefon henüz eşleştirilmemiş"
        val sig = d["sig"] ?: return "REDDEDİLDİ: imza yok"
        if (!Verifier.equalsConstantTime(Verifier.sign(secret, d), sig)) return "REDDEDİLDİ: imza geçersiz"
        val ts = d["ts"]?.toLongOrNull() ?: return "REDDEDİLDİ: zaman damgası yok"
        if (kotlin.math.abs(System.currentTimeMillis() / 1000 - ts) > MAX_SKEW_S) return "REDDEDİLDİ: mesaj eski (saat farkı?)"
        val nonce = d["nonce"] ?: return "REDDEDİLDİ: nonce yok"
        if (Prefs.seenNonce(c, nonce)) return "REDDEDİLDİ: tekrar edilen mesaj"
        val id = d["id"].orEmpty().ifBlank { "jarvis" }
        return when (d["cmd"]) {
            "call" -> "call: " + call(c, d["name"].orEmpty())
            "hangup" -> "hangup: " + hangup(c)
            "ring" -> "ring: " + ring(c, id, (d["at"]?.toLongOrNull() ?: 0L), d["title"].orEmpty(), d["body"].orEmpty())
            "cancel" -> "cancel: " + cancel(c, id)
            "ping" -> { showInfo(c, "Jarvis", "Bağlantı tamam"); "ping: tamam" }
            else -> "bilinmeyen komut"
        }
    }
}
