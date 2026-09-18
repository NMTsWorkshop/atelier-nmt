package fr.nmt.atelier;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Réveil périodique : interroge les imprimantes, recale les alarmes de fin,
 * puis se replanifie. Le travail tient dans le budget d'un receiver — les
 * relèves sont menées en parallèle et bornées à neuf secondes.
 */
public class SyncReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        final Context app = context.getApplicationContext();
        final PendingResult pending = goAsync();

        new Thread(new Runnable() {
            public void run() {
                try {
                    Sync.runOnce(app, 9);
                } catch (Throwable ignored) {
                } finally {
                    if (Sync.hasPrinters(app)) Sync.schedule(app);
                    pending.finish();
                }
            }
        }).start();
    }
}
