package fr.nmt.atelier;

/**
 * Vérifie la décision d'une alarme de fin d'impression.
 *
 *   javac -d /tmp/fins app/src/main/java/fr/nmt/atelier/Fins.java \
 *         test/java/fr/nmt/atelier/TestFins.java
 *   java -cp /tmp/fins fr.nmt.atelier.TestFins
 *
 * Rien d'Android ici : c'est tout l'intérêt de l'avoir isolée.
 */
public class TestFins {

    private static int passes = 0;
    private static int ratees = 0;

    private static void verifie(String titre, boolean condition, String detail) {
        if (condition) {
            passes++;
            System.out.println("  ok   " + titre);
        } else {
            ratees++;
            System.out.println("  ECHEC " + titre + " — " + detail);
        }
    }

    public static void main(String[] args) {
        long m = 60000L;

        // --- la machine imprime encore : on se taît et on repousse ---
        long d = Fins.delaiAvantDeSonner("printing", 7);
        verifie("une machine qui imprime encore repousse l'alarme de ce qu'il reste",
                d == 7 * m, String.valueOf(d));

        d = Fins.delaiAvantDeSonner("printing", 1);
        verifie("mais jamais moins de deux minutes, pour ne pas sonner en boucle",
                d == Fins.REPOS_MIN, String.valueOf(d));

        d = Fins.delaiAvantDeSonner("printing", 0);
        verifie("zero minute restante et toujours en cours : deux minutes aussi",
                d == Fins.REPOS_MIN, String.valueOf(d));

        d = Fins.delaiAvantDeSonner("printing", -1);
        verifie("un restant inconnu ne fait pas notifier a tort",
                d == Fins.REPOS_MIN, String.valueOf(d));

        d = Fins.delaiAvantDeSonner("printing", 60 * 24 * 7);
        verifie("une lecture farfelue est plafonnee a six heures",
                d == Fins.REPOS_MAX, String.valueOf(d));

        // --- une pause n'est pas une fin ---
        d = Fins.delaiAvantDeSonner("paused", 12);
        verifie("un changement de filament au milieu d'un plateau n'est pas une fin",
                d == 12 * m, String.valueOf(d));

        // --- la machine a fini : on notifie ---
        verifie("une machine qui a fini fait sonner l'alarme",
                Fins.delaiAvantDeSonner("finished", 0) == 0, "");
        verifie("une machine a l'arret aussi",
                Fins.delaiAvantDeSonner("idle", -1) == 0, "");
        verifie("et une machine en erreur, surtout",
                Fins.delaiAvantDeSonner("failed", 30) == 0, "");

        // --- personne n'a repondu : on notifie comme avant ---
        verifie("sans lecture, on notifie plutot que de se taire",
                Fins.delaiAvantDeSonner(null, -1) == 0, "");
        verifie("une phase vide compte comme pas de lecture",
                Fins.delaiAvantDeSonner("", 20) == 0, "");

        System.out.println();
        System.out.println("==============================");
        if (ratees == 0) {
            System.out.println("Tout est passé (" + passes + " vérifications).");
        } else {
            System.out.println(ratees + " échec(s) sur " + (passes + ratees) + ".");
            System.exit(1);
        }
    }
}
