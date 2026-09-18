#!/usr/bin/env python3
"""Complète les bouchons de gen.py : bibliothèques tierces et méthodes
ajoutées au fil des versions. À lancer après gen.py.

    python3 test/stubs/gen.py && python3 test/stubs/extras.py
    javac -d /tmp/out -sourcepath "test/stubs/src:app/src/main/java" \\
        $(find app/src/main/java -name '*.java')
"""

import os

ROOT = os.path.join(os.path.dirname(__file__), 'src')

NEW = {

'org/json/JSONArray.java': '''
package org.json;
public class JSONArray {
  public JSONArray(){}
  public JSONArray(String s) throws Exception {}
  public int length(){ return 0; }
  public JSONObject getJSONObject(int i) throws Exception { return null; }
  public JSONObject optJSONObject(int i){ return null; }
  public JSONArray optJSONArray(int i){ return null; }
  public void put(Object o){}
  public String toString(){ return "[]"; }
}
''',

'androidx/core/content/FileProvider.java': '''
package androidx.core.content;
import android.content.Context;
import android.net.Uri;
import java.io.File;
public class FileProvider {
  public static Uri getUriForFile(Context c, String authority, File f){ return null; }
}
''',

'android/content/pm/PackageInfo.java':
'package android.content.pm;\npublic class PackageInfo { public String versionName; }\n',

'android/content/ClipboardManager.java':
'package android.content;\npublic class ClipboardManager { public void setPrimaryClip(ClipData c){} }\n',

'android/content/ClipData.java':
'package android.content;\npublic class ClipData {\n'
'  public static ClipData newPlainText(CharSequence l, CharSequence t){ return null; }\n}\n',

'org/eclipse/paho/client/mqttv3/MqttClient.java': '''
package org.eclipse.paho.client.mqttv3;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
public class MqttClient {
  public MqttClient(String uri, String id, MemoryPersistence p) throws Exception {}
  public void setCallback(MqttCallback cb){}
  public void connect(MqttConnectOptions o) throws Exception {}
  public void subscribe(String topic) throws Exception {}
  public void subscribe(String topic, int qos) throws Exception {}
  public void publish(String topic, byte[] payload, int qos, boolean retained) throws Exception {}
  public void disconnect() throws Exception {}
  public void disconnect(long quiesce) throws Exception {}
  public void close() throws Exception {}
  public boolean isConnected(){ return false; }
}
''',

'org/eclipse/paho/client/mqttv3/MqttCallback.java': '''
package org.eclipse.paho.client.mqttv3;
public interface MqttCallback {
  void connectionLost(Throwable cause);
  void messageArrived(String topic, MqttMessage message) throws Exception;
  void deliveryComplete(IMqttDeliveryToken token);
}
''',

'org/eclipse/paho/client/mqttv3/MqttMessage.java':
'package org.eclipse.paho.client.mqttv3;\n'
'public class MqttMessage { public byte[] getPayload(){ return new byte[0]; } }\n',

'org/eclipse/paho/client/mqttv3/IMqttDeliveryToken.java':
'package org.eclipse.paho.client.mqttv3;\npublic interface IMqttDeliveryToken {}\n',

'org/eclipse/paho/client/mqttv3/MqttConnectOptions.java': '''
package org.eclipse.paho.client.mqttv3;
import javax.net.SocketFactory;
public class MqttConnectOptions {
  public void setUserName(String u){}
  public void setPassword(char[] p){}
  public void setSocketFactory(SocketFactory f){}
  public void setConnectionTimeout(int s){}
  public void setKeepAliveInterval(int s){}
  public void setCleanSession(boolean b){}
  public void setAutomaticReconnect(boolean b){}
}
''',

'org/eclipse/paho/client/mqttv3/persist/MemoryPersistence.java':
'package org.eclipse.paho.client.mqttv3.persist;\npublic class MemoryPersistence {}\n',

'android/content/BroadcastReceiver.java': '''
package android.content;
public abstract class BroadcastReceiver {
  public abstract void onReceive(Context context, Intent intent);
  public PendingResult goAsync(){ return null; }
  public static class PendingResult { public void finish(){} }
}
''',

'android/content/pm/PackageManager.java': '''
package android.content.pm;
public class PackageManager {
  public static final int PERMISSION_GRANTED = 0;
  public PackageInfo getPackageInfo(String name, int flags) throws Exception { return null; }
  public boolean canRequestPackageInstalls(){ return true; }
}
''',
}

PATCHES = [
    ('android/content/Context.java',
     'public ContentResolver getContentResolver(){ return null; }',
     'public ContentResolver getContentResolver(){ return null; }\n'
     '  public android.content.pm.PackageManager getPackageManager(){ return null; }\n'
     '  public java.io.File getCacheDir(){ return null; }\n'
     '  public Context getApplicationContext(){ return this; }'),

    ('android/content/Context.java',
     'public static final String VIBRATOR_SERVICE = "vibrator";',
     'public static final String VIBRATOR_SERVICE = "vibrator";\n'
     '  public static final String CLIPBOARD_SERVICE = "clipboard";'),

    ('android/content/Intent.java',
     'public static final int FLAG_ACTIVITY_CLEAR_TOP = 2;',
     'public static final int FLAG_ACTIVITY_CLEAR_TOP = 2;\n'
     '  public static final int FLAG_GRANT_READ_URI_PERMISSION = 4;\n'
     '  public static final String ACTION_VIEW = "view";\n'
     '  public Intent setDataAndType(android.net.Uri u, String t){ return this; }'),

    ('android/provider/Settings.java',
     'public static final String EXTRA_APP_PACKAGE = "e";',
     'public static final String EXTRA_APP_PACKAGE = "e";\n'
     '  public static final String ACTION_MANAGE_UNKNOWN_APP_SOURCES = "f";'),

    ('android/app/AlarmManager.java',
     'public void cancel(PendingIntent op){}',
     'public void cancel(PendingIntent op){}\n'
     '  public void set(int type, long at, PendingIntent op){}'),

    ('org/json/JSONObject.java',
     'public String optString(String k){ return ""; }',
     'public String optString(String k){ return ""; }\n'
     '  public String getString(String k) throws Exception { return ""; }\n'
     '  public JSONObject getJSONObject(String k) throws Exception { return null; }\n'
     '  public JSONArray optJSONArray(String k){ return null; }\n'
     '  public boolean has(String k){ return false; }\n'
     '  public boolean optBoolean(String k, boolean d){ return d; }\n'
     '  public int optInt(String k){ return 0; }\n'
     '  public int optInt(String k, int d){ return d; }\n'
     '  public double optDouble(String k, double d){ return d; }'),
]

for rel, body in NEW.items():
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(body.lstrip())

for rel, old, new in PATCHES:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        continue
    s = open(path).read()
    # déjà appliqué ? on teste la dernière ligne ajoutée, la seule
    # qui soit à coup sûr absente du bouchon d'origine
    if new.rstrip().split('\n')[-1].strip() in s:
        continue
    if old in s:
        open(path, 'w').write(s.replace(old, new, 1))

print('bouchons complétés :', len(NEW), 'fichiers,', len(PATCHES), 'retouches')
