package com.furkan.jarvisphone

import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Bilgisayardan gelen komutun imzası. Bilgisayar tarafı (phonelink.py) AYNI biçimi üretir:
 * HMAC-SHA256(secret, "cmd|name|title|body|at|id|ts|nonce") küçük harf hex.
 */
object Verifier {
    val FIELDS = listOf("cmd", "name", "title", "body", "at", "id", "ts", "nonce")

    fun sign(secret: String, data: Map<String, String>): String {
        val text = FIELDS.joinToString("|") { data[it] ?: "" }
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }

    fun equalsConstantTime(a: String, b: String): Boolean =
        MessageDigest.isEqual(a.toByteArray(Charsets.UTF_8), b.toByteArray(Charsets.UTF_8))
}
