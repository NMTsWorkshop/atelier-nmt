package fr.nmt.atelier;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Déclenché à l'heure prévue : affiche la notification de fin d'impression. */
public class AlarmReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context context, Intent intent) {
        String id = intent.getStringExtra("id");
        String title = intent.getStringExtra("title");
        String text = intent.getStringExtra("text");
        if (id == null) id = "timer";

        Timers.forget(context, id);
        Notifier.show(context, id, title, text);
    }
}
