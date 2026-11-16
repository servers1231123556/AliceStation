package ru.alice.remote;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class AliceWidgetProvider extends AppWidgetProvider {

    static final String ACTION_TOGGLE = "ru.alice.remote.WIDGET_TOGGLE";
    static final String ACTION_NEXT = "ru.alice.remote.WIDGET_NEXT";
    static final String ACTION_PREV = "ru.alice.remote.WIDGET_PREV";
    static final String BASE = "http://192.168.0.91:8099";

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] ids) {
        refresh(context);
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        String a = intent.getAction();
        if (a == null) return;
        if (ACTION_TOGGLE.equals(a) || ACTION_NEXT.equals(a) || ACTION_PREV.equals(a)) {
            final String action = ACTION_TOGGLE.equals(a) ? "toggle" : (ACTION_NEXT.equals(a) ? "next" : "previous");
            new Thread(new Runnable() {
                @Override
                public void run() {
                    post("/api/player", "{\"action\":\"" + action + "\"}");
                }
            }).start();
        }
    }

    static void refresh(final Context context) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                RemoteViews rv = new RemoteViews(context.getPackageName(), R.layout.widget);
                String title = "Нет связи";
                String sub = "проверь Wi-Fi";
                boolean playing = false;
                try {
                    JSONObject o = new JSONObject(get("/api/state"));
                    JSONObject p = o.optJSONObject("player");
                    if (p != null) {
                        title = p.optString("title", "Ничего не играет");
                        String artists = p.optString("artists", "");
                        String st = p.optString("status", "");
                        playing = "playing".equals(st) || "buffering".equals(st);
                        sub = artists.isEmpty() ? st : artists + " · " + st;
                    }
                } catch (Exception ignored) {
                }
                if (title.isEmpty()) title = "Ничего не играет";
                rv.setTextViewText(R.id.widget_title, title);
                rv.setTextViewText(R.id.widget_sub, sub);
                rv.setTextViewText(R.id.widget_toggle, playing ? "II" : "▶");

                rv.setOnClickPendingIntent(R.id.widget_toggle, pi(context, ACTION_TOGGLE, 1));
                rv.setOnClickPendingIntent(R.id.widget_next, pi(context, ACTION_NEXT, 2));
                rv.setOnClickPendingIntent(R.id.widget_prev, pi(context, ACTION_PREV, 3));

                AppWidgetManager mgr = AppWidgetManager.getInstance(context);
                int[] ids = mgr.getAppWidgetIds(new ComponentName(context, AliceWidgetProvider.class));
                mgr.updateAppWidget(ids, rv);
            }
        }).start();
    }

    static PendingIntent pi(Context c, String action, int code) {
        Intent i = new Intent(c, AliceWidgetProvider.class);
        i.setAction(action);
        return PendingIntent.getBroadcast(c, code, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static String get(String path) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(BASE + path).openConnection();
        c.setConnectTimeout(4000);
        c.setReadTimeout(6000);
        BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), "UTF-8"));
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = r.readLine()) != null) sb.append(line);
        r.close();
        c.disconnect();
        return sb.toString();
    }

    static void post(String path, String body) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(BASE + path).openConnection();
            c.setConnectTimeout(4000);
            c.setReadTimeout(15000);
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            OutputStream os = c.getOutputStream();
            os.write(body.getBytes("UTF-8"));
            os.close();
            c.getResponseCode();
            c.disconnect();
        } catch (Exception ignored) {
        }
    }
}
