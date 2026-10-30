package fr.nmt.atelier;

/**
 * La décision qu'une alarme de fin d'impression prend quand elle sonne :
 * notifier, ou se taire et redemander plus tard.
 *
 * Elle est isolée ici, sans rien d'Android autour, pour être vérifiable
 * d'un simple `java` — sans téléphone, sans réseau, sans machine. C'est le
 * genre d'erreur qui ne se voit qu'à l'usage, et qui coûte soit une
 * notification en avance, soit une notification jamais.
 */
final class Fins {

    /** Jamais moins de deux minutes : une machine bloquée à 100 % ferait
        sinon sonner l'alarme en boucle. */
    static final long REPOS_MIN = 2 * 60 * 1000L;

    /** Et jamais plus de six heures : une lecture farfelue ne doit pas
        repousser la notification à la semaine prochaine. */
    static final long REPOS_MAX = 6 * 60 * 60 * 1000L;

    private Fins() {
    }

    /**
     * @param phase ce que la machine dit de son état, ou null quand
     *              personne n'a répondu
     * @param reste les minutes restantes qu'elle annonce, -1 si inconnu
     * @return 0 pour notifier maintenant, sinon le délai en millisecondes
     *         avant de lui redemander
     */
    static long delaiAvantDeSonner(String phase, long reste) {
        /* Aucune lecture : on notifie, comme avant d'avoir cette
           vérification. Une notification un peu tôt vaut mieux qu'une
           notification jamais. */
        if (phase == null || phase.length() == 0) return 0;

        /* « paused » compte comme en cours : un changement de filament au
           milieu d'un plateau n'est pas une fin d'impression. */
        if (!"printing".equals(phase) && !"paused".equals(phase)) return 0;

        long dans = reste > 0 ? reste * 60000L : 0;
        if (dans < REPOS_MIN) dans = REPOS_MIN;
        if (dans > REPOS_MAX) dans = REPOS_MAX;
        return dans;
    }
}
