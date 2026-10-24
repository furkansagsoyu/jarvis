package com.furkan.jarvisphone

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.drawable.Icon
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
import android.media.RingtoneManager
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.VibrationEffect
import android.os.Vibrator

/** Alarmı gerçek bir saat uygulaması gibi çalar: alarm ses kanalı, döngü, titreşim; Kapat / 5 dk ertele düğmeleri. */
class AlarmService : Service() {
    private var player: MediaPlayer? = null
    private var vibrator: Vibrator? = null
    private var wake: PowerManager.WakeLock? = null
    private var focus: AudioFocusRequest? = null
    private val handler = Handler(Looper.getMainLooper())
    private val autoStop = Runnable { stopSelf() }
    private var curId = "jarvis"
    private var curTitle = "Jarvis"
    private var curBody = ""

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> { stopSelf(); return START_NOT_STICKY }
            ACTION_SNOOZE -> {
                val at = System.currentTimeMillis() + 5 * 60_000L
                val sid = curId.removeSuffix("z") + "z"
                Prefs.putAlarm(this, sid, at, curTitle, curBody)
                Commands.schedule(this, sid, at, curTitle, curBody)
                Prefs.log(this, "alarm 5 dk ertelendi")
                stopSelf()
                return START_NOT_STICKY
            }
        }
        curId = intent?.getStringExtra("id") ?: "jarvis"
        curTitle = (intent?.getStringExtra("title") ?: "Jarvis").ifBlank { "Jarvis" }
        curBody = intent?.getStringExtra("body") ?: ""
        Commands.ensureChannels(this)
        val notification = buildNotification()
        if (android.os.Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        } else {
            startForeground(NOTIF_ID, notification)
        }
        startSound()
        startVibration()
        wake?.takeIf { it.isHeld }?.release()
        wake = getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "jarvis:alarm").apply { acquire(130_000L) }
        handler.removeCallbacks(autoStop)
        handler.postDelayed(autoStop, 120_000L)
        Prefs.log(this, "alarm çalıyor")
        return START_NOT_STICKY
    }

    private fun action(label: String, icon: Int, act: String, req: Int): Notification.Action {
        val pi = PendingIntent.getService(
            this, req, Intent(this, AlarmService::class.java).setAction(act),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return Notification.Action.Builder(Icon.createWithResource(this, icon), label, pi).build()
    }

    private fun buildNotification(): Notification =
        Notification.Builder(this, Commands.CH_QUIET)
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(curTitle)
            .setContentText(curBody)
            .setCategory(Notification.CATEGORY_ALARM)
            .setOngoing(true)
            .setContentIntent(Commands.appIntent(this, stopAlarm = true))
            .addAction(action("Kapat", android.R.drawable.ic_menu_close_clear_cancel, ACTION_STOP, 10))
            .addAction(action("5 dk ertele", android.R.drawable.ic_menu_recent_history, ACTION_SNOOZE, 11))
            .build()

    private fun startSound() {
        stopSound()
        val attrs = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_ALARM)
            .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
            .build()
        val am = getSystemService(AudioManager::class.java)
        focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
            .setAudioAttributes(attrs)
            .setOnAudioFocusChangeListener { }
            .build()
        am.requestAudioFocus(focus!!)
        val uri = RingtoneManager.getActualDefaultRingtoneUri(this, RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ?: RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
        try {
            player = MediaPlayer().apply {
                setAudioAttributes(attrs)
                setDataSource(this@AlarmService, uri)
                isLooping = true
                prepare()
                start()
            }
        } catch (e: Exception) {
            Prefs.log(this, "alarm sesi çalınamadı (${e.javaClass.simpleName})")
        }
    }

    private fun stopSound() {
        try { player?.stop() } catch (e: Exception) { }
        player?.release()
        player = null
    }

    @Suppress("DEPRECATION")
    private fun startVibration() {
        vibrator = getSystemService(Vibrator::class.java)
        vibrator?.vibrate(VibrationEffect.createWaveform(longArrayOf(0, 600, 300, 600, 300, 600, 1500), 0))
    }

    override fun onDestroy() {
        handler.removeCallbacks(autoStop)
        stopSound()
        vibrator?.cancel()
        focus?.let { getSystemService(AudioManager::class.java).abandonAudioFocusRequest(it) }
        wake?.takeIf { it.isHeld }?.release()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    companion object {
        const val ACTION_STOP = "com.furkan.jarvisphone.ALARM_STOP"
        const val ACTION_SNOOZE = "com.furkan.jarvisphone.ALARM_SNOOZE"
        const val NOTIF_ID = 4242
    }
}
