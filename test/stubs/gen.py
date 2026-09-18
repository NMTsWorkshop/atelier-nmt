#!/usr/bin/env python3
"""Génère des bouchons minimalistes du SDK Android pour vérifier que le code Java
de la coque compile (syntaxe, imports, noms de variables). Les bouchons ne
remplacent pas un vrai build : ils attrapent les fautes de frappe, pas les
erreurs de signature côté Android."""

import os, shutil

ROOT = os.path.join(os.path.dirname(__file__), 'src')
if os.path.isdir(ROOT):
    shutil.rmtree(ROOT)

FILES = {

'android/Manifest.java': '''
package android;
public class Manifest {
  public static class permission {
    public static final String POST_NOTIFICATIONS = "a";
    public static final String INTERNET = "b";
  }
}
''',

'android/annotation/SuppressLint.java': '''
package android.annotation;
public @interface SuppressLint { String[] value(); }
''',

'android/graphics/Color.java': '''
package android.graphics;
public class Color { public static int parseColor(String s){ return 0; } }
''',

'android/net/Uri.java': '''
package android.net;
public class Uri { public static Uri parse(String s){ return null; } }
''',

'android/os/Bundle.java': 'package android.os;\npublic class Bundle {}\n',

'android/os/Build.java': '''
package android.os;
public class Build { public static class VERSION { public static int SDK_INT; } }
''',

'android/os/Environment.java': '''
package android.os;
public class Environment {
  public static final String DIRECTORY_DOWNLOADS = "Download";
  public static final String DIRECTORY_DOCUMENTS = "Documents";
}
''',

'android/os/Vibrator.java': '''
package android.os;
public class Vibrator {
  public boolean hasVibrator(){ return true; }
  public void vibrate(VibrationEffect e){}
  public void vibrate(long[] pattern, int repeat){}
}
''',

'android/os/VibrationEffect.java': '''
package android.os;
public class VibrationEffect {
  public static VibrationEffect createWaveform(long[] timings, int repeat){ return null; }
}
''',

'android/view/View.java': '''
package android.view;
public class View {
  public static final int OVER_SCROLL_NEVER = 2;
  public Object getParent(){ return null; }
  public void setOverScrollMode(int m){}
  public void setBackgroundColor(int c){}
  public boolean post(Runnable r){ return true; }
}
''',

'android/view/ViewGroup.java': '''
package android.view;
public class ViewGroup extends View { public void removeView(View v){} }
''',

'android/content/Context.java': '''
package android.content;
import android.content.pm.PackageManager;
public class Context {
  public static final String NOTIFICATION_SERVICE = "notification";
  public static final String ALARM_SERVICE = "alarm";
  public static final String VIBRATOR_SERVICE = "vibrator";
  public static final int MODE_PRIVATE = 0;
  public Object getSystemService(String name){ return null; }
  public SharedPreferences getSharedPreferences(String n, int m){ return null; }
  public String getPackageName(){ return ""; }
  public ContentResolver getContentResolver(){ return null; }
  public java.io.File getExternalFilesDir(String type){ return null; }
  public java.io.File getFilesDir(){ return null; }
  public int checkSelfPermission(String p){ return 0; }
  public void startActivity(Intent i){}
}
''',

'android/content/ContentResolver.java': '''
package android.content;
import android.net.Uri;
import java.io.OutputStream;
public class ContentResolver {
  public Uri insert(Uri url, ContentValues values){ return null; }
  public OutputStream openOutputStream(Uri uri){ return null; }
}
''',

'android/content/ContentValues.java': '''
package android.content;
public class ContentValues { public void put(String k, String v){} }
''',

'android/content/Intent.java': '''
package android.content;
public class Intent {
  public static final String ACTION_BOOT_COMPLETED = "boot";
  public static final String ACTION_MY_PACKAGE_REPLACED = "replaced";
  public static final int FLAG_ACTIVITY_NEW_TASK = 1;
  public static final int FLAG_ACTIVITY_CLEAR_TOP = 2;
  public Intent(){}
  public Intent(String action){}
  public Intent(String action, android.net.Uri uri){}
  public Intent(Context c, Class<?> cls){}
  public String getAction(){ return null; }
  public String getStringExtra(String k){ return null; }
  public Intent setAction(String a){ return this; }
  public Intent putExtra(String k, String v){ return this; }
  public Intent setFlags(int f){ return this; }
  public Intent addFlags(int f){ return this; }
}
''',

'android/content/BroadcastReceiver.java': '''
package android.content;
public abstract class BroadcastReceiver {
  public abstract void onReceive(Context context, Intent intent);
}
''',

'android/content/SharedPreferences.java': '''
package android.content;
public interface SharedPreferences {
  String getString(String k, String def);
  Editor edit();
  interface Editor { Editor putString(String k, String v); void apply(); }
}
''',

'android/content/pm/PackageManager.java': '''
package android.content.pm;
public class PackageManager { public static final int PERMISSION_GRANTED = 0; }
''',

'android/media/AudioAttributes.java': '''
package android.media;
public class AudioAttributes {
  public static final int USAGE_NOTIFICATION = 5;
  public static final int CONTENT_TYPE_SONIFICATION = 4;
  public static class Builder {
    public Builder setUsage(int u){ return this; }
    public Builder setContentType(int t){ return this; }
    public AudioAttributes build(){ return null; }
  }
}
''',

'android/media/RingtoneManager.java': '''
package android.media;
import android.net.Uri;
public class RingtoneManager {
  public static final int TYPE_NOTIFICATION = 2;
  public static Uri getDefaultUri(int type){ return null; }
}
''',

'android/provider/MediaStore.java': '''
package android.provider;
import android.net.Uri;
public class MediaStore {
  public static class Downloads {
    public static final Uri EXTERNAL_CONTENT_URI = null;
    public static final String DISPLAY_NAME = "n";
    public static final String MIME_TYPE = "m";
    public static final String RELATIVE_PATH = "p";
  }
}
''',

'android/provider/Settings.java': '''
package android.provider;
public class Settings {
  public static final String ACTION_REQUEST_SCHEDULE_EXACT_ALARM = "a";
  public static final String ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS = "b";
  public static final String ACTION_APPLICATION_DETAILS_SETTINGS = "c";
  public static final String ACTION_APP_NOTIFICATION_SETTINGS = "d";
  public static final String EXTRA_APP_PACKAGE = "e";
}
''',

'android/app/Activity.java': '''
package android.app;
import android.content.Context;
import android.os.Bundle;
import android.view.View;
public class Activity extends Context {
  protected void onCreate(Bundle b){}
  protected void onResume(){}
  protected void onDestroy(){}
  public void onBackPressed(){}
  public void setContentView(View v){}
  public void runOnUiThread(Runnable r){}
  public void requestPermissions(String[] perms, int code){}
}
''',

'android/app/AlarmManager.java': '''
package android.app;
public class AlarmManager {
  public static final int RTC_WAKEUP = 0;
  public static class AlarmClockInfo {
    public AlarmClockInfo(long triggerTime, PendingIntent show){}
  }
  public boolean canScheduleExactAlarms(){ return true; }
  public void setAlarmClock(AlarmClockInfo info, PendingIntent operation){}
  public void setAndAllowWhileIdle(int type, long at, PendingIntent op){}
  public void cancel(PendingIntent op){}
}
''',

'android/app/PendingIntent.java': '''
package android.app;
import android.content.Context;
import android.content.Intent;
public class PendingIntent {
  public static final int FLAG_UPDATE_CURRENT = 1;
  public static final int FLAG_IMMUTABLE = 2;
  public static PendingIntent getBroadcast(Context c, int rc, Intent i, int flags){ return null; }
  public static PendingIntent getActivity(Context c, int rc, Intent i, int flags){ return null; }
}
''',

'android/app/Notification.java': '''
package android.app;
import android.content.Context;
public class Notification {
  public static final int VISIBILITY_PUBLIC = 1;
  public static final String CATEGORY_ALARM = "alarm";
  public static class BigTextStyle {
    public BigTextStyle bigText(CharSequence t){ return this; }
  }
  public static class Builder {
    public Builder(Context c, String channelId){}
    public Builder setSmallIcon(int icon){ return this; }
    public Builder setContentTitle(CharSequence t){ return this; }
    public Builder setContentText(CharSequence t){ return this; }
    public Builder setStyle(Object s){ return this; }
    public Builder setCategory(String c){ return this; }
    public Builder setAutoCancel(boolean b){ return this; }
    public Builder setShowWhen(boolean b){ return this; }
    public Builder setContentIntent(PendingIntent pi){ return this; }
    public Notification build(){ return null; }
  }
}
''',

'android/app/NotificationChannel.java': '''
package android.app;
import android.media.AudioAttributes;
import android.net.Uri;
public class NotificationChannel {
  public NotificationChannel(String id, CharSequence name, int importance){}
  public void setDescription(String d){}
  public void enableVibration(boolean b){}
  public void setVibrationPattern(long[] p){}
  public void setLockscreenVisibility(int v){}
  public void setSound(Uri sound, AudioAttributes attrs){}
}
''',

'android/app/NotificationManager.java': '''
package android.app;
public class NotificationManager {
  public static final int IMPORTANCE_HIGH = 4;
  public NotificationChannel getNotificationChannel(String id){ return null; }
  public void createNotificationChannel(NotificationChannel ch){}
  public void notify(int id, Notification n){}
  public void cancel(int id){}
  public boolean areNotificationsEnabled(){ return true; }
}
''',

'android/webkit/JavascriptInterface.java': '''
package android.webkit;
import java.lang.annotation.*;
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.METHOD})
public @interface JavascriptInterface {}
''',

'android/webkit/ValueCallback.java': '''
package android.webkit;
public interface ValueCallback<T> { void onReceiveValue(T value); }
''',

'android/webkit/WebSettings.java': '''
package android.webkit;
public class WebSettings {
  public void setJavaScriptEnabled(boolean b){}
  public void setDomStorageEnabled(boolean b){}
  public void setAllowFileAccess(boolean b){}
  public void setLoadWithOverviewMode(boolean b){}
  public void setUseWideViewPort(boolean b){}
  public void setTextZoom(int z){}
  public void setMediaPlaybackRequiresUserGesture(boolean b){}
}
''',

'android/webkit/WebViewClient.java': 'package android.webkit;\npublic class WebViewClient {}\n',
'android/webkit/WebChromeClient.java': 'package android.webkit;\npublic class WebChromeClient {}\n',

'android/webkit/WebView.java': '''
package android.webkit;
import android.content.Context;
import android.view.ViewGroup;
public class WebView extends ViewGroup {
  public WebView(Context c){}
  public WebSettings getSettings(){ return null; }
  public void setWebViewClient(WebViewClient c){}
  public void setWebChromeClient(WebChromeClient c){}
  public void addJavascriptInterface(Object obj, String name){}
  public void removeJavascriptInterface(String name){}
  public void loadUrl(String url){}
  public void evaluateJavascript(String script, ValueCallback<String> cb){}
  public void destroy(){}
}
''',

'org/json/JSONObject.java': '''
package org.json;
import java.util.Iterator;
public class JSONObject {
  public JSONObject(){}
  public JSONObject(String s) throws Exception {}
  public JSONObject put(String k, Object v) throws Exception { return this; }
  public JSONObject put(String k, boolean v) throws Exception { return this; }
  public JSONObject put(String k, int v) throws Exception { return this; }
  public JSONObject put(String k, long v) throws Exception { return this; }
  public Object remove(String k){ return null; }
  public Iterator<String> keys(){ return null; }
  public JSONObject optJSONObject(String k){ return null; }
  public String optString(String k){ return ""; }
  public String optString(String k, String def){ return def; }
  public long optLong(String k, long def){ return def; }
  public String toString(){ return ""; }
  public static String quote(String s){ return ""; }
}
''',

'fr/nmt/atelier/R.java': '''
package fr.nmt.atelier;
public final class R {
  public static final class drawable { public static final int ic_stat = 1; }
  public static final class string { public static final int app_name = 2; }
}
''',
}

for rel, body in FILES.items():
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(body.lstrip())

print('bouchons générés :', len(FILES))
