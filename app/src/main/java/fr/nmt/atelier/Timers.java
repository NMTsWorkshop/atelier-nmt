package fr.nmt.atelier;

import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.os.Build;

import org.json.JSONObject;

import java.util.Iterator;

/**
 * Planification des fins d'impression.
 *
 * On passe par AlarmManager.setAlarmClock() : c'est le seul mode de réveil
 * qu'Android ne repousse pas en Doze, donc la notification tombe à l'heure
 * même si le téléphone dort depuis des heures.
 */
public class Timers {

    static final String CHANNEL = "prints";
    private static final String PREFS = "nmt_timers";
    private static final String KEY = "map";

    /* ---------- canal de notification ---------- */

    static void ensureChannel(Context c) {
        NotificationManager nm =
                (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (nm.getNotificationChannel(CHANNEL) != null) return;

        NotificationChannel ch = new NotificationChannel(
                CHANNEL, "Fin d'impression", NotificationManager.IMPORTANCE_HIGH);
        ch.setDescription("Alerte quand le timer d'une machine arrive à son terme");
        ch.enableVibration(true);
        ch.setVibrationPattern(new long[]{0, 400, 200, 400});
        ch.setLockscreenVisibility(android.app.Notification.VISIBILITY_PUBLIC);
        AudioAttributes attrs = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build();
        ch.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION), attrs);
        nm.createNotificationChannel(ch);
    }

    /* ---------- planification ---------- */

    private static PendingIntent alarmIntent(Context c, String id, String title, String text) {
        Intent i = new Intent(c, AlarmReceiver.class);
        i.setAction("fr.nmt.atelier.FIRE." + id);
        i.putExtra("id", id);
        i.putExtra("title", title);
        i.putExtra("text", text);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE;
        return PendingIntent.getBroadcast(c, id.hashCode(), i, flags);
    }

    private static PendingIntent openAppIntent(Context c) {
        Intent i = new Intent(c, MainActivity.class);
        i.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return PendingIntent.getActivity(c, 0, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static void schedule(Context c, String id, String title, String text, long at) {
        ensureChannel(c);
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am == null) return;

        PendingIntent fire = alarmIntent(c, id, title, text);

        boolean exact = true;
        if (Build.VERSION.SDK_INT >= 31) {
            exact = am.canScheduleExactAlarms();
        }

        if (exact) {
            am.setAlarmClock(new AlarmManager.AlarmClockInfo(at, openAppIntent(c)), fire);
        } else {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, fire);
        }
        remember(c, id, title, text, at);
    }

    static void cancel(Context c, String id) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am != null) am.cancel(alarmIntent(c, id, "", ""));
        forget(c, id);
        NotificationManager nm =
                (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm != null) nm.cancel(id.hashCode());
    }

    /* ---------- mémoire des alarmes, pour survivre à un redémarrage ---------- */

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static JSONObject all(Context c) {
        try {
            return new JSONObject(prefs(c).getString(KEY, "{}"));
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    private static void remember(Context c, String id, String title, String text, long at) {
        try {
            JSONObject map = all(c);
            JSONObject one = new JSONObject();
            one.put("title", title);
            one.put("text", text);
            one.put("at", at);
            map.put(id, one);
            prefs(c).edit().putString(KEY, map.toString()).apply();
        } catch (Exception ignored) {
        }
    }

    static void forget(Context c, String id) {
        try {
            JSONObject map = all(c);
            map.remove(id);
            prefs(c).edit().putString(KEY, map.toString()).apply();
        } catch (Exception ignored) {
        }
    }

    /** Rappelée au démarrage du téléphone : les alarmes sont perdues, on les repose. */
    static void rescheduleAll(Context c) {
        JSONObject map = all(c);
        long now = System.currentTimeMillis();
        Iterator<String> it = map.keys();
        while (it.hasNext()) {
            String id = it.next();
            JSONObject one = map.optJSONObject(id);
            if (one == null) continue;
            long at = one.optLong("at", 0);
            if (at > now) {
                schedule(c, id, one.optString("title", "Impression terminée"),
                        one.optString("text", ""), at);
            }
        }
    }
}
