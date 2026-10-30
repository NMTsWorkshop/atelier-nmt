package fr.nmt.atelier;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

import org.json.JSONObject;

/**
 * Déclenché à l'heure prévue : affiche la notification de fin d'impression.
 *
 * Sauf qu'une heure prévue n'est pas une fin. L'alarme a été posée sur
 * l'estimation que la machine donnait il y a un quart d'heure, et une
 * estimation se trompe — une machine qui ralentit sur les dernières
 * couches, une pause, un changement de filament. La notification tombait
 * alors qu'il restait des minutes à tourner.
 *
 * Donc quand l'alarme porte un nom de machine, on lui redemande d'abord où
 * elle en est. Si elle imprime encore, on repousse l'alarme et on ne dit
 * rien. Si elle a fini, ou si personne ne répond, on notifie : une
 * notification un peu tôt vaut mieux qu'une notification jamais.
 */
public class AlarmReceiver extends BroadcastReceiver {

    /**
     * Au-delà, on renonce à vérifier et on notifie.
     *
     * Douze secondes parce qu'interroger une Bambu ouvre une session MQTT
     * et que son client s'accorde déjà huit secondes d'écoute. Un budget
     * plus court renoncerait avant même qu'elle ait répondu, et la
     * vérification ne servirait à rien sur la moitié du parc. Une alarme
     * réveille le téléphone, donc le réseau est là.
     */
    private static final long BUDGET_MS = 12000L;

    @Override
    public void onReceive(Context context, Intent intent) {
        String recu = intent.getStringExtra("id");
        final String id = recu == null ? "timer" : recu;
        final String title = intent.getStringExtra("title");
        final String text = intent.getStringExtra("text");
        final String verifier = intent.getStringExtra("verifier");
        final Context app = context.getApplicationContext();

        Timers.forget(app, id);

        /* un minuteur réglé à la main ne décrit aucune machine : rien à
           vérifier, il sonne à l'heure qu'on lui a donnée */
        if (verifier == null || verifier.length() == 0) {
            Notifier.show(app, id, title, text);
            return;
        }

        final PendingResult attente = goAsync();
        new Thread(new Runnable() {
            public void run() {
                try {
                    if (!repousse(app, id, title, text, verifier)) {
                        Notifier.show(app, id, title, text);
                    }
                } catch (Throwable t) {
                    Notifier.show(app, id, title, text);
                } finally {
                    attente.finish();
                }
            }
        }).start();
    }

    /**
     * Vrai quand la machine imprime encore et que l'alarme a été repoussée.
     *
     * La lecture se fait dans un fil à part, avec un budget : interroger une
     * Bambu ouvre une session MQTT, et un réseau qui traîne ne doit pas
     * retenir le système. Passé le délai, on renonce à vérifier et on
     * notifie — c'est le comportement d'avant, pas une régression.
     */
    private static boolean repousse(final Context app, String id, String title,
                                    String text, final String machineId) {
        final JSONObject[] lu = new JSONObject[1];
        Thread lecture = new Thread(new Runnable() {
            public void run() {
                try {
                    lu[0] = Sync.relire(app, machineId);
                } catch (Throwable ignored) {
                }
            }
        });
        lecture.start();
        try {
            lecture.join(BUDGET_MS);
        } catch (InterruptedException ignored) {
        }

        JSONObject st = lu[0];
        long dans = Fins.delaiAvantDeSonner(st == null ? null : st.optString("state", ""),
                                            st == null ? -1 : st.optLong("remaining", -1));
        if (dans <= 0) return false;

        Timers.schedule(app, id, title, text, System.currentTimeMillis() + dans,
                machineId);
        return true;
    }
}
