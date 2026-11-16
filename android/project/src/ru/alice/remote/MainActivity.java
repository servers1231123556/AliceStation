package ru.alice.remote;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

public class MainActivity extends Activity {

    private static final String PREFS = "alice_remote";
    private static final String KEY_URL = "url";
    private static final String DEFAULT_URL = "http://192.168.0.91:8099/";

    private WebView web;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        Window w = getWindow();
        w.setFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS, WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        w.setStatusBarColor(Color.parseColor("#0e1014"));
        w.setNavigationBarColor(Color.parseColor("#0e1014"));

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#0e1014"));

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        web.setBackgroundColor(Color.parseColor("#0e1014"));
        web.setWebViewClient(new WebViewClient());
        web.setWebChromeClient(new WebChromeClient());

        final TextView hint = new TextView(this);
        hint.setText("Не удалось подключиться.\nДолгий тап — сменить адрес панели.");
        hint.setTextColor(Color.parseColor("#8b93a3"));
        hint.setTextSize(14);
        hint.setPadding(48, 48, 48, 48);
        hint.setVisibility(View.GONE);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                hint.setVisibility(View.GONE);
            }

            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                hint.setVisibility(View.VISIBLE);
            }
        });

        web.setOnLongClickListener(new View.OnLongClickListener() {
            @Override
            public boolean onLongClick(View v) {
                showUrlDialog();
                return true;
            }
        });

        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        root.addView(hint, new FrameLayout.LayoutParams(-1, -2));
        setContentView(root);

        web.loadUrl(bustCache(getUrl()));
    }

    private static String bustCache(String url) {
        return url + (url.contains("?") ? "&" : "?") + "t=" + System.currentTimeMillis();
    }

    private String getUrl() {
        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        return p.getString(KEY_URL, DEFAULT_URL);
    }

    private void showUrlDialog() {
        final EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(getUrl());
        LinearLayout box = new LinearLayout(this);
        box.setPadding(40, 20, 40, 0);
        box.addView(input, new LinearLayout.LayoutParams(-1, -2));

        new AlertDialog.Builder(this)
                .setTitle("Адрес панели")
                .setView(box)
                .setPositiveButton("Сохранить", new android.content.DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(android.content.DialogInterface d, int which) {
                        String url = input.getText().toString().trim();
                        if (!url.startsWith("http")) {
                            url = "http://" + url;
                        }
                        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(KEY_URL, url).apply();
                        web.loadUrl(url);
                    }
                })
                .setNegativeButton("Отмена", null)
                .show();
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
