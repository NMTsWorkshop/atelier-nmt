package fr.nmt.atelier;

import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttCallback;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.json.JSONObject;

import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * Lecture de l'état d'une imprimante Bambu en MQTT local.
 *
 * On se connecte au broker embarqué (port 8883, utilisateur « bblp »,
 * mot de passe = code d'accès LAN), on demande un état complet avec
 * « pushall », on prend la première réponse utile et on se déconnecte.
 * Aucune commande n'est envoyée à la machine : lecture seule.
 */
public class BambuClient {

    static JSONObject fetch(String host, String serial, String code, int timeoutSec)
            throws Exception {

        String uri = "ssl://" + host + ":8883";
        MqttClient client = new MqttClient(uri, "nmt-atelier-" + System.currentTimeMillis(),
                new MemoryPersistence());

        MqttConnectOptions opts = new MqttConnectOptions();
        opts.setUserName("bblp");
        opts.setPassword(code.toCharArray());
        opts.setSocketFactory(trustAll());
        opts.setConnectionTimeout(10);
        opts.setKeepAliveInterval(30);
        opts.setCleanSession(true);
        opts.setAutomaticReconnect(false);

        final JSONObject[] result = new JSONObject[1];
        final CountDownLatch latch = new CountDownLatch(1);

        client.setCallback(new MqttCallback() {
            @Override
            public void connectionLost(Throwable cause) {
                latch.countDown();
            }

            @Override
            public void messageArrived(String topic, MqttMessage message) {
                try {
                    JSONObject d = new JSONObject(new String(message.getPayload(), "UTF-8"));
                    JSONObject p = d.optJSONObject("print");
                    /* les rapports partiels arrivent en continu ; on attend
                       celui qui porte réellement l'état d'impression */
                    if (p != null && (p.has("gcode_state") || p.has("mc_percent"))) {
                        result[0] = p;
                        latch.countDown();
                    }
                } catch (Exception ignored) {
                }
            }

            @Override
            public void deliveryComplete(IMqttDeliveryToken token) {
            }
        });

        try {
            client.connect(opts);
            client.subscribe("device/" + serial + "/report", 0);
            client.publish("device/" + serial + "/request",
                    "{\"pushing\":{\"sequence_id\":\"1\",\"command\":\"pushall\"}}"
                            .getBytes("UTF-8"), 0, false);
            latch.await(timeoutSec, TimeUnit.SECONDS);
        } finally {
            try {
                if (client.isConnected()) client.disconnect(2000);
            } catch (Exception ignored) {
            }
            try {
                client.close();
            } catch (Exception ignored) {
            }
        }

        if (result[0] == null) {
            throw new Exception("aucune donnée reçue en " + timeoutSec + " s");
        }
        return result[0];
    }

    /** Le certificat de l'imprimante est auto-signé : on ne le valide pas. */
    private static SSLSocketFactory trustAll() throws Exception {
        TrustManager[] tm = new TrustManager[]{
                new X509TrustManager() {
                    @Override
                    public void checkClientTrusted(X509Certificate[] chain, String authType) {
                    }

                    @Override
                    public void checkServerTrusted(X509Certificate[] chain, String authType) {
                    }

                    @Override
                    public X509Certificate[] getAcceptedIssuers() {
                        return new X509Certificate[0];
                    }
                }
        };
        SSLContext ctx = SSLContext.getInstance("TLS");
        ctx.init(null, tm, new SecureRandom());
        return ctx.getSocketFactory();
    }
}
