package com.furkan.jarvisphone

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Küçük yerel depo. Gizli anahtar (secret) yalnızca bu telefonda ve bilgisayarda durur. */
object Prefs {
    private fun sp(c: Context) = c.getSharedPreferences("jarvis", Context.MODE_PRIVATE)

    fun secret(c: Context): String = sp(c).getString("secret", "") ?: ""
    fun setSecret(c: Context, v: String) = sp(c).edit().putString("secret", v).apply()

    fun token(c: Context): String = sp(c).getString("token", "") ?: ""
    fun setToken(c: Context, v: String) = sp(c).edit().putString("token", v).apply()

    /** Aynı mesaj ikinci kez gelirse (tekrar saldırısı) reddetmek için son nonce'lar. */
    @Synchronized
    fun seenNonce(c: Context, nonce: String): Boolean {
        val list = (sp(c).getString("nonces", "") ?: "").split(",").filter { it.isNotEmpty() }.toMutableList()
        if (list.contains(nonce)) return true
        list.add(nonce)
        while (list.size > 64) list.removeAt(0)
        sp(c).edit().putString("nonces", list.joinToString(",")).apply()
        return false
    }

    /** Ekranda gösterilen son olaylar (kişisel veri içermez: komut türü ve sonuç). */
    @Synchronized
    fun log(c: Context, line: String) {
        val arr = try { JSONArray(sp(c).getString("log", "[]")) } catch (e: Exception) { JSONArray() }
        val out = JSONArray()
        val stamp = java.text.SimpleDateFormat("dd.MM HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())
        out.put("$stamp  $line")
        for (i in 0 until minOf(arr.length(), 29)) out.put(arr.getString(i))
        sp(c).edit().putString("log", out.toString()).apply()
    }

    fun logLines(c: Context): List<String> {
        val arr = try { JSONArray(sp(c).getString("log", "[]")) } catch (e: Exception) { JSONArray() }
        return (0 until arr.length()).map { arr.getString(it) }
    }

    // Zamanlanmış alarmlar: id -> {at, title, body}. Yeniden başlatmadan sonra tekrar kurulur.
    @Synchronized
    fun alarms(c: Context): JSONObject = try { JSONObject(sp(c).getString("alarms", "{}")) } catch (e: Exception) { JSONObject() }

    @Synchronized
    fun putAlarm(c: Context, id: String, at: Long, title: String, body: String) {
        val o = alarms(c)
        o.put(id, JSONObject().put("at", at).put("title", title).put("body", body))
        sp(c).edit().putString("alarms", o.toString()).apply()
    }

    @Synchronized
    fun removeAlarm(c: Context, id: String) {
        val o = alarms(c)
        o.remove(id)
        sp(c).edit().putString("alarms", o.toString()).apply()
    }
}
