package fr.nmt.atelier;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * Relève périodique des imprimantes.
 *
 * On ne maintient aucun service en avant-plan : un réveil toutes les quinze
 * minutes suffit à recaler l'heure de fin, et c'est l'alarme précise déjà
 * en place (Timers.setAlarmClock) qui déclenche la notification à la seconde.
 * Résultat : pas de notification permanente, pas de batterie grignotée.
 */
public class Sync {

    private static final long PERIOD = 15 * 60 * 1000L;
    private static final String ACTION = "fr.nmt.atelier.SYNC";

    /* ---------- planification du réveil périodique ---------- */

    private static PendingIntent tick(Context c) {
        Intent i = new Intent(c, SyncReceiver.class).setAction(ACTION);
        return PendingIntent.getBroadcast(c, 4242, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static void schedule(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am == null) return;
        long at = System.currentTimeMillis() + PERIOD;
        if (Build.VERSION.SDK_INT >= 23) {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, tick(c));
        } else {
            am.set(AlarmManager.RTC_WAKEUP, at, tick(c));
        }
    }

    static void cancel(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am != null) am.cancel(tick(c));
    }

    static boolean hasPrinters(Context c) {
        return Printers.config(c).length() > 0;
    }

    /* ---------- une relève ---------- */

    /**
     * Interroge toutes les machines configurées, en parallèle, sous contrainte
     * de temps. Met à jour l'état stocké, recale les alarmes de fin et notifie
     * les impressions qui viennent de se terminer.
     */
    static void runOnce(final Context c, int budgetSec) {
        final JSONArray conf = Printers.config(c);
        if (conf.length() == 0) return;

        final JSONObject before = Printers.states(c);
        List<Runnable> jobs = new ArrayList<>();
        final JSONObject[] results = new JSONObject[conf.length()];

        for (int i = 0; i < conf.length(); i++) {
            final int idx = i;
            jobs.add(new Runnable() {
                public void run() {
                    JSONObject one = conf.optJSONObject(idx);
                    if (one == null) return;
                    results[idx] = Printers.poll(one);
                }
            });
        }

        ExecutorService pool = Executors.newFixedThreadPool(Math.min(4, jobs.size()));
        for (Runnable r : jobs) pool.execute(r);
        pool.shutdown();
        try {
            pool.awaitTermination(budgetSec, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
        }
        pool.shutdownNow();

        for (int i = 0; i < conf.length(); i++) {
            JSONObject one = conf.optJSONObject(i);
            JSONObject st = results[i];
            if (one == null || st == null) continue;
            String id = one.optString("machineId", "m" + i);
            String name = one.optString("name", "Machine");
            Printers.putState(c, id, st);
            if (st.optBoolean("ok", false)) {
                react(c, id, name, before.optJSONObject(id), st);
            }
        }
    }

    /** Compare l'état d'avant et celui d'après, et agit en conséquence. */
    private static void react(Context c, String id, String name,
                              JSONObject prev, JSONObject now) {
        String was = prev == null ? "" : prev.optString("state", "");
        String is = now.optString("state", "");
        String file = now.optString("file", "");
        String alarmId = "p-" + id;

        if ("printing".equals(is)) {
            long remaining = now.optLong("remaining", -1);
            if (remaining >= 0) {
                long endAt = System.currentTimeMillis() + remaining * 60000L;
                long known = prev == null ? 0 : prev.optLong("endAt", 0);
                /* on ne replanifie que si l'estimation a bougé d'au moins
                   deux minutes : inutile de harceler AlarmManager */
                if (Math.abs(endAt - known) > 120000L) {
                    Timers.schedule(c, alarmId, name + " — impression terminée",
                            file.length() > 0 ? file : "La machine a fini.", endAt);
                }
                try {
                    now.put("endAt", Math.abs(endAt - known) > 120000L ? endAt : known);
                } catch (Exception ignored) {
                }
                Printers.putState(c, id, now);
            }
            return;
        }

        /* la machine n'imprime plus : si elle imprimait au tour précédent,
           c'est maintenant qu'il faut prévenir */
        if ("printing".equals(was)) {
            Timers.cancel(c, alarmId);
            if ("failed".equals(is)) {
                Notifier.show(c, alarmId, name + " — impression interrompue",
                        file.length() > 0 ? file : "La machine signale une erreur.");
            } else {
                Notifier.show(c, alarmId, name + " — impression terminée",
                        file.length() > 0 ? file : "La machine a fini.");
            }
        }
    }
}
