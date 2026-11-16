package ru.alice.remote;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.TimePickerDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Switch;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {

    private static final String PREFS = "alice_remote";
    private static final String KEY_URL = "url";
    private static final String DEFAULT_URL = "http://192.168.0.91:8099";

    private static final int BG = 0xFF0F0F14;
    private static final int CARD = 0xFF1C1C24;
    private static final int CARD2 = 0xFF232330;
    private static final int TEXT = 0xFFF2F2F7;
    private static final int MUTED = 0xFF8B8B99;
    private static final int ACCENT = 0xFF7A55FF;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService pool = Executors.newFixedThreadPool(3);

    private FrameLayout content;
    private LinearLayout nav;
    private final List<View> tabViews = new ArrayList<>();
    private int tab = 0;
    private int tick = 0;

    // home
    private TextView homeTitle, homeSub, weatherCity, chipTitle, chipOut, chipBt, devCount;
    private Button homePlay;
    private LinearLayout weatherRow, devList;
    private Button outSpk, outBt;

    // music
    private TextView mTitle, mArtist, mPos, mDur, mStatus;
    private SeekBar mSeek;
    private Button mToggle, favBtn;
    private LinearLayout favList, queueList;
    private TextView favCount, qCount;
    private boolean seeking = false;
    private boolean queueExpanded = false;

    // sound
    private final SeekBar[] bands = new SeekBar[5];
    private final TextView[] bandLabels = new TextView[5];
    private Switch eqSwitch, drcSwitch;
    private Button applyEq;
    private TextView eqStatus;
    private boolean eqBuilding = true;

    // more
    private TextView sysUp, sysCpu, sysTemp, sysMem, sysDisk;
    private LinearLayout alarmList;
    private EditText alarmQuery;
    private int alarmMinutes = 420;

    private String base() {
        SharedPreferences p = getSharedPreferences(PREFS, MODE_PRIVATE);
        return p.getString(KEY_URL, DEFAULT_URL);
    }

    private int dp(float v) {
        return (int) (v * getResources().getDisplayMetrics().density);
    }

    // ---------- small ui helpers ----------

    private TextView text(String s, float sp, int color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        return t;
    }

    private LinearLayout card() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable g = new GradientDrawable();
        g.setColor(CARD);
        g.setCornerRadius(dp(22));
        l.setBackground(g);
        l.setPadding(dp(16), dp(14), dp(16), dp(14));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(12);
        l.setLayoutParams(lp);
        return l;
    }

    private Button button(String s, boolean accent) {
        Button b = new Button(this);
        b.setText(s);
        b.setAllCaps(false);
        b.setTextColor(0xFFFFFFFF);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        GradientDrawable g = new GradientDrawable();
        g.setColor(accent ? ACCENT : CARD2);
        g.setCornerRadius(dp(14));
        b.setBackground(g);
        b.setPadding(dp(10), dp(6), dp(10), dp(6));
        return b;
    }

    private LinearLayout row() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        return l;
    }

    private View spacer() {
        View v = new View(this);
        v.setLayoutParams(new LinearLayout.LayoutParams(0, 1, 1f));
        return v;
    }

    private ScrollView scroll(View child) {
        ScrollView s = new ScrollView(this);
        s.setFillViewport(true);
        s.addView(child, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return s;
    }


    private Drawable seekTrack() {
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xFF2A2A35);
        bg.setCornerRadius(dp(3));
        bg.setSize(0, dp(5));

        GradientDrawable prog = new GradientDrawable();
        prog.setColor(ACCENT);
        prog.setCornerRadius(dp(3));
        prog.setSize(0, dp(5));

        android.graphics.drawable.ClipDrawable clip = new android.graphics.drawable.ClipDrawable(
                prog, Gravity.LEFT, android.graphics.drawable.ClipDrawable.HORIZONTAL);

        android.graphics.drawable.LayerDrawable ld = new android.graphics.drawable.LayerDrawable(
                new android.graphics.drawable.Drawable[]{bg, clip});
        ld.setId(0, android.R.id.background);
        ld.setId(1, android.R.id.progress);
        return ld;
    }

    private Drawable seekThumb() {
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.OVAL);
        g.setColor(ACCENT);
        g.setSize(dp(18), dp(18));
        g.setStroke(dp(3), 0xFF0F0F14);
        return g;
    }


    /** Bipolar progress: fills from the middle to the thumb, like a real EQ band. */
    static class CenterProgress extends Drawable {
        private final Paint bg = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint fg = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final float d;
        private int level = 5000;

        CenterProgress(float density) {
            d = density;
            bg.setColor(0xFF2A2A35);
            fg.setColor(ACCENT);
        }

        @Override
        public void draw(android.graphics.Canvas c) {
            android.graphics.Rect b = getBounds();
            float h = 5 * d;
            float cy = b.centerY();
            c.drawRoundRect(b.left, cy - h / 2, b.right, cy + h / 2, h / 2, h / 2, bg);
            float cx = b.centerX();
            float x = b.left + b.width() * (level / 10000f);
            float left = Math.min(x, cx);
            float right = Math.max(x, cx);
            if (right - left > 1) {
                c.drawRoundRect(left, cy - h / 2, right, cy + h / 2, h / 2, h / 2, fg);
            }
        }

        @Override
        public void setAlpha(int a) { fg.setAlpha(a); }

        @Override
        public void setColorFilter(android.graphics.ColorFilter cf) { fg.setColorFilter(cf); }

        @Override
        public int getOpacity() { return android.graphics.PixelFormat.TRANSLUCENT; }

        @Override
        protected boolean onLevelChange(int l) { level = l; invalidateSelf(); return true; }
    }

    private void styleSeekCentered(SeekBar s) {
        s.setProgressDrawable(new CenterProgress(getResources().getDisplayMetrics().density));
        s.setThumb(seekThumb());
        s.setThumbOffset(dp(9));
        s.setSplitTrack(false);
        s.setPadding(dp(10), 0, dp(10), 0);
    }

    private void styleSeek(SeekBar s) {
        s.setProgressDrawable(seekTrack());
        s.setThumb(seekThumb());
        s.setThumbOffset(dp(9));
        s.setSplitTrack(false);
        s.setPadding(dp(10), 0, dp(10), 0);
    }

    private void tintSwitch(Switch sw) {
        android.content.res.ColorStateList accent = android.content.res.ColorStateList
                .valueOf(ACCENT);
        android.content.res.ColorStateList off = android.content.res.ColorStateList
                .valueOf(0xFF3A3A46);
        sw.setThumbTintList(accent);
        sw.setTrackTintList(sw.isChecked() ? accent : off);
    }

    // ---------- lifecycle ----------


    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout rootLayout = new LinearLayout(this);
        rootLayout.setOrientation(LinearLayout.VERTICAL);
        rootLayout.setBackgroundColor(BG);

        content = new FrameLayout(this);
        LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f);
        rootLayout.addView(content, clp);

        nav = buildNav();
        rootLayout.addView(nav, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(62)));

        setContentView(rootLayout);

        tabViews.add(buildHome());
        tabViews.add(buildSound());
        tabViews.add(buildMusic());
        tabViews.add(buildMore());
        int startTab = getIntent().getIntExtra("tab", 0);
        if (startTab < 0 || startTab > 3) startTab = 0;
        showTab(startTab);
        startPolling();
    }

    private LinearLayout buildNav() {
        LinearLayout n = new LinearLayout(this);
        n.setOrientation(LinearLayout.HORIZONTAL);
        n.setBackgroundColor(0xFF15151C);
        String[] names = {"Дом", "Звук", "Музыка", "Ещё"};
        String[] icons = {"⌂", "⚙", "♪", "☰"};
        for (int i = 0; i < names.length; i++) {
            final int idx = i;
            LinearLayout item = new LinearLayout(this);
            item.setOrientation(LinearLayout.VERTICAL);
            item.setGravity(Gravity.CENTER);
            TextView ic = text(icons[i], 18, TEXT);
            ic.setGravity(Gravity.CENTER);
            TextView nm = text(names[i], 11, MUTED);
            nm.setGravity(Gravity.CENTER);
            item.addView(ic);
            item.addView(nm);
            item.setOnClickListener(v -> showTab(idx));
            n.addView(item, new LinearLayout.LayoutParams(0,
                    ViewGroup.LayoutParams.MATCH_PARENT, 1f));
        }
        return n;
    }

    private void showTab(int i) {
        tab = i;
        content.removeAllViews();
        content.addView(tabViews.get(i));
        for (int k = 0; k < nav.getChildCount(); k++) {
            LinearLayout item = (LinearLayout) nav.getChildAt(k);
            boolean on = k == i;
            ((TextView) item.getChildAt(0)).setTextColor(on ? TEXT : MUTED);
            ((TextView) item.getChildAt(1)).setTextColor(on ? TEXT : MUTED);
        }
        refresh();
    }

    // ---------- HOME ----------

    private View buildHome() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(dp(14), dp(26), dp(14), dp(16));

        TextView h = text("Мой дом", 26, TEXT);
        h.setTypeface(null, android.graphics.Typeface.BOLD);
        h.setOnLongClickListener(v -> {
            editUrl();
            return true;
        });
        col.addView(h);

        LinearLayout hero = card();
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{0xFF3A2A7A, 0xFF1C1A2E});
        g.setCornerRadius(dp(22));
        hero.setBackground(g);

        LinearLayout top = row();
        TextView name = text("Станция Мини new", 17, TEXT);
        name.setTypeface(null, android.graphics.Typeface.BOLD);
        homeSub = text("—", 13, MUTED);
        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        titles.addView(name);
        titles.addView(homeSub);
        top.addView(titles, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        homePlay = button("▶", true);
        homePlay.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        homePlay.setOnClickListener(v -> postJson("/api/player", "{\"action\":\"toggle\"}"));
        top.addView(homePlay, new LinearLayout.LayoutParams(dp(56), dp(56)));
        hero.addView(top);

        LinearLayout chips = row();
        chipTitle = text("—", 13, 0xFFFFFFFF);
        GradientDrawable cg = new GradientDrawable();
        cg.setColor(0x33FFFFFF);
        cg.setCornerRadius(dp(16));
        chipTitle.setBackground(cg);
        chipTitle.setPadding(dp(12), dp(7), dp(12), dp(7));
        chips.addView(chipTitle);
        chipOut = text("Колонка", 13, TEXT);
        GradientDrawable og = new GradientDrawable();
        og.setColor(0x33FFFFFF);
        og.setCornerRadius(dp(16));
        chipOut.setBackground(og);
        chipOut.setPadding(dp(12), dp(7), dp(12), dp(7));
        chipBt = text("Bluetooth", 13, TEXT);
        GradientDrawable bg2 = new GradientDrawable();
        bg2.setColor(0x33FFFFFF);
        bg2.setCornerRadius(dp(16));
        chipBt.setBackground(bg2);
        chipBt.setPadding(dp(12), dp(7), dp(12), dp(7));
        LinearLayout.LayoutParams cop = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        cop.leftMargin = dp(8);
        chips.addView(chipOut, cop);
        LinearLayout.LayoutParams cbp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        cbp.leftMargin = dp(8);
        chips.addView(chipBt, cbp);
        hero.addView(chips, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        col.addView(hero);

        LinearLayout wc = card();
        LinearLayout wr = row();
        wr.addView(text("Погода", 16, TEXT));
        wr.addView(spacer());
        weatherCity = text("—", 13, MUTED);
        wr.addView(weatherCity);
        wc.addView(wr);
        weatherRow = row();
        HorizontalScrollView hs = new HorizontalScrollView(this);
        hs.setHorizontalScrollBarEnabled(false);
        hs.addView(weatherRow);
        wc.addView(hs);
        col.addView(wc);

        LinearLayout dc = card();
        LinearLayout dr = row();
        dr.addView(text("Зал", 16, TEXT));
        dr.addView(spacer());
        devCount = text("—", 13, MUTED);
        dr.addView(devCount);
        dc.addView(dr);
        devList = new LinearLayout(this);
        devList.setOrientation(LinearLayout.VERTICAL);
        dc.addView(devList);
        col.addView(dc);

        LinearLayout oc = card();
        oc.addView(text("Вывод звука", 16, TEXT));
        LinearLayout orow = row();
        outSpk = button("Колонка", true);
        outBt = button("Усилитель", false);
        outSpk.setOnClickListener(v -> postOut("spk"));
        outBt.setOnClickListener(v -> postOut("bt"));
        orow.addView(outSpk, new LinearLayout.LayoutParams(0, dp(48), 1f));
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(0, dp(48), 1f);
        blp.leftMargin = dp(8);
        orow.addView(outBt, blp);
        oc.addView(orow);
        col.addView(oc);

        return scroll(col);
    }

    // ---------- MUSIC ----------

    private View buildMusic() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(dp(14), dp(26), dp(14), dp(16));

        TextView h = text("Музыка", 26, TEXT);
        h.setTypeface(null, android.graphics.Typeface.BOLD);
        col.addView(h);

        LinearLayout c = card();
        mTitle = text("Ничего не играет", 17, TEXT);
        mTitle.setTypeface(null, android.graphics.Typeface.BOLD);
        mTitle.setSingleLine(true);
        mArtist = text("", 13, MUTED);
        c.addView(mTitle);
        c.addView(mArtist);

        mSeek = new SeekBar(this);
        mSeek.setMax(1000);
        styleSeek(mSeek);
        mSeek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar s, int p, boolean fromUser) {
                if (fromUser) seeking = true;
            }
            public void onStartTrackingTouch(SeekBar s) { seeking = true; }
            public void onStopTrackingTouch(SeekBar s) {
                seeking = false;
                postJson("/api/player", "{\"action\":\"seek\",\"value\":0}");
            }
        });
        c.addView(mSeek);

        LinearLayout times = row();
        mPos = text("0:00", 12, MUTED);
        mDur = text("0:00", 12, MUTED);
        times.addView(mPos);
        times.addView(spacer());
        times.addView(mDur);
        c.addView(times);

        LinearLayout ctrl = row();
        Button prev = button("⏮", false);
        mToggle = button("▶", true);
        Button next = button("⏭", false);
        prev.setOnClickListener(v -> postJson("/api/player", "{\"action\":\"previous\"}"));
        next.setOnClickListener(v -> postJson("/api/player", "{\"action\":\"next\"}"));
        mToggle.setOnClickListener(v -> postJson("/api/player", "{\"action\":\"toggle\"}"));
        ctrl.addView(prev, new LinearLayout.LayoutParams(0, dp(52), 1f));
        LinearLayout.LayoutParams mlp = new LinearLayout.LayoutParams(0, dp(52), 1.3f);
        mlp.leftMargin = dp(8); mlp.rightMargin = dp(8);
        ctrl.addView(mToggle, mlp);
        ctrl.addView(next, new LinearLayout.LayoutParams(0, dp(52), 1f));
        c.addView(ctrl);

        LinearLayout seekRow = row();
        for (final int delta : new int[]{-30, -10, 10, 30}) {
            Button b = button((delta > 0 ? "+" : "") + delta, false);
            b.setOnClickListener(v -> postJson("/api/player",
                    "{\"action\":\"seek\",\"value\":" + delta + "}"));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(44), 1f);
            lp.leftMargin = dp(4); lp.rightMargin = dp(4);
            seekRow.addView(b, lp);
        }
        c.addView(seekRow);

        favBtn = button("♡  В избранное", true);
        favBtn.setOnClickListener(v -> postJson("/api/favorites", "{\"action\":\"add_current\"}"));
        LinearLayout.LayoutParams flp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
        flp.topMargin = dp(10);
        c.addView(favBtn, flp);
        mStatus = text("", 12, MUTED);
        c.addView(mStatus);
        col.addView(c);

        LinearLayout fc = card();
        LinearLayout fr = row();
        fr.addView(text("Избранное", 16, TEXT));
        fr.addView(spacer());
        favCount = text("—", 13, MUTED);
        fr.addView(favCount);
        fc.addView(fr);
        favList = new LinearLayout(this);
        favList.setOrientation(LinearLayout.VERTICAL);
        fc.addView(favList);
        col.addView(fc);

        LinearLayout qc = card();
        LinearLayout qr = row();
        qr.addView(text("Очередь", 16, TEXT));
        qr.addView(spacer());
        qCount = text("—", 13, MUTED);
        qr.addView(qCount);
        qc.addView(qr);
        queueList = new LinearLayout(this);
        queueList.setOrientation(LinearLayout.VERTICAL);
        qc.addView(queueList);
        Button more = button("Показать всю очередь", false);
        more.setOnClickListener(v -> { queueExpanded = !queueExpanded; refresh(); });
        qc.addView(more);
        col.addView(qc);

        return scroll(col);
    }

    // ---------- SOUND ----------

    private View buildSound() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(dp(14), dp(26), dp(14), dp(16));

        TextView h = text("Звук", 26, TEXT);
        h.setTypeface(null, android.graphics.Typeface.BOLD);
        col.addView(h);

        LinearLayout c = card();
        LinearLayout r1 = row();
        r1.addView(text("Эквалайзер", 16, TEXT));
        r1.addView(spacer());
        eqSwitch = new Switch(this);
        eqSwitch.setOnCheckedChangeListener((b, checked) ->
                postJson("/api/set", "{\"eq\":" + checked + "}"));
        r1.addView(eqSwitch);
        tintSwitch(eqSwitch);
        c.addView(r1);

        String[] freqs = {"60 Гц", "230 Гц", "910 Гц", "3.6 кГц", "14 кГц"};
        for (int i = 0; i < 5; i++) {
            LinearLayout line = row();
            bandLabels[i] = text(freqs[i], 12, MUTED);
            line.addView(bandLabels[i], new LinearLayout.LayoutParams(dp(56),
                    ViewGroup.LayoutParams.WRAP_CONTENT));
            bands[i] = new SeekBar(this);
            bands[i].setMax(24);
            bands[i].setProgress(12);
            styleSeekCentered(bands[i]);
            final int idx = i;
            bands[i].setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
                public void onProgressChanged(SeekBar s, int p, boolean u) {
                    bandLabels[idx].setText(freqs[idx] + "  " + (p - 12));
                }
                public void onStartTrackingTouch(SeekBar s) {}
                public void onStopTrackingTouch(SeekBar s) {}
            });
            line.addView(bands[i], new LinearLayout.LayoutParams(0, dp(40), 1f));
            c.addView(line);
        }

        LinearLayout presets = new LinearLayout(this);
        presets.setOrientation(LinearLayout.HORIZONTAL);
        String[] names = {"Плоско", "Бас", "Голос", "Рок", "Ночной"};
        int[][] values = {
                {0, 0, 0, 0, 0}, {8, 5, 0, -2, -4}, {0, 3, 5, 3, 0},
                {5, 3, -1, 3, 5}, {4, 2, -3, -4, -6}};
        for (int i = 0; i < names.length; i++) {
            final int[] v = values[i];
            Button b = button(names[i], false);
            b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
            b.setOnClickListener(x -> {
                for (int k = 0; k < 5; k++) bands[k].setProgress(v[k] + 12);
            });
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(44), 1f);
            lp.leftMargin = dp(2); lp.rightMargin = dp(2);
            presets.addView(b, lp);
        }
        c.addView(presets);

        applyEq = button("Применить кривую", true);
        applyEq.setOnClickListener(v -> applyEq());
        LinearLayout.LayoutParams alp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
        alp.topMargin = dp(10);
        c.addView(applyEq, alp);
        eqStatus = text("", 12, MUTED);
        c.addView(eqStatus);
        col.addView(c);

        LinearLayout dc = card();
        LinearLayout dr = row();
        dr.addView(text("DRC", 16, TEXT));
        dr.addView(spacer());
        drcSwitch = new Switch(this);
        drcSwitch.setOnCheckedChangeListener((b, checked) ->
                postJson("/api/set", "{\"drc\":" + checked + "}"));
        dr.addView(drcSwitch);
        tintSwitch(drcSwitch);
        dc.addView(dr);
        col.addView(dc);

        eqBuilding = false;
        return scroll(col);
    }

    // ---------- MORE ----------

    private View buildMore() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(dp(14), dp(26), dp(14), dp(16));

        TextView h = text("Ещё", 26, TEXT);
        h.setTypeface(null, android.graphics.Typeface.BOLD);
        col.addView(h);

        LinearLayout c = card();
        LinearLayout r = row();
        r.addView(text("Станция", 16, TEXT));
        r.addView(spacer());
        sysUp = text("—", 12, MUTED);
        r.addView(sysUp);
        c.addView(r);

        LinearLayout g1 = row();
        sysCpu = text("—", 20, TEXT);
        sysTemp = text("—", 20, TEXT);
        LinearLayout.LayoutParams tp1 = new LinearLayout.LayoutParams(0, dp(70), 1f);
        tp1.rightMargin = dp(5);
        g1.addView(tile("Процессор", sysCpu), tp1);
        g1.addView(tile("Температура", sysTemp), new LinearLayout.LayoutParams(0, dp(70), 1f));
        c.addView(g1);
        LinearLayout g2 = row();
        sysMem = text("—", 18, TEXT);
        sysDisk = text("—", 18, TEXT);
        LinearLayout.LayoutParams tp2 = new LinearLayout.LayoutParams(0, dp(70), 1f);
        tp2.rightMargin = dp(5);
        tp2.topMargin = dp(6);
        g2.addView(tile("Память", sysMem), tp2);
        LinearLayout.LayoutParams tp3 = new LinearLayout.LayoutParams(0, dp(70), 1f);
        tp3.topMargin = dp(6);
        g2.addView(tile("Диск", sysDisk), tp3);
        c.addView(g2);
        col.addView(c);

        LinearLayout qc = card();
        qc.addView(text("Быстрые команды", 16, TEXT));
        LinearLayout qr = row();
        Button pause = button("Пауза", false);
        pause.setOnClickListener(v -> postJson("/api/player", "{\"action\":\"toggle\"}"));
        Button nxt = button("Следующий", false);
        nxt.setOnClickListener(v -> postJson("/api/player", "{\"action\":\"next\"}"));
        Button stop = button("Стоп", false);
        stop.setOnClickListener(v -> postJson("/api/player", "{\"action\":\"stop\"}"));
        qr.addView(pause, new LinearLayout.LayoutParams(0, dp(44), 1f));
        LinearLayout.LayoutParams qlp = new LinearLayout.LayoutParams(0, dp(44), 1f);
        qlp.leftMargin = dp(6);
        qr.addView(nxt, qlp);
        LinearLayout.LayoutParams q2 = new LinearLayout.LayoutParams(0, dp(44), 1f);
        q2.leftMargin = dp(6);
        qr.addView(stop, q2);
        qc.addView(qr);
        col.addView(qc);

        LinearLayout ac = card();
        ac.addView(text("Будильник станции", 16, TEXT));
        LinearLayout ar = row();
        Button pick = button("07:00", false);
        pick.setOnClickListener(v -> {
            Calendar cal = Calendar.getInstance();
            new TimePickerDialog(MainActivity.this, (view, hh, mm) -> {
                alarmMinutes = hh * 60 + mm;
                pick.setText(String.format("%02d:%02d", hh, mm));
            }, cal.get(Calendar.HOUR_OF_DAY), cal.get(Calendar.MINUTE), true).show();
        });
        alarmQuery = new EditText(this);
        alarmQuery.setHint("что включить");
        alarmQuery.setTextColor(TEXT);
        alarmQuery.setHintTextColor(MUTED);
        alarmQuery.setInputType(InputType.TYPE_CLASS_TEXT);
        GradientDrawable ag = new GradientDrawable();
        ag.setColor(CARD2);
        ag.setCornerRadius(dp(14));
        alarmQuery.setBackground(ag);
        ar.addView(pick, new LinearLayout.LayoutParams(dp(110), dp(46)));
        LinearLayout.LayoutParams aqlp = new LinearLayout.LayoutParams(0, dp(46), 1f);
        aqlp.leftMargin = dp(8);
        ar.addView(alarmQuery, aqlp);
        ac.addView(ar);
        Button addAlarm = button("Добавить будильник", true);
        addAlarm.setOnClickListener(v -> {
            int offset = -java.util.TimeZone.getDefault().getOffset(System.currentTimeMillis()) / 60000;
            tmpOffset = offset;
            postJson("/api/alarms", "{\"action\":\"add\",\"minutes\":" + alarmMinutes +
                    ",\"offset\":" + offset + ",\"query\":\"" + alarmQuery.getText().toString().replace("\"", " ") + "\"}");
            alarmQuery.setText("");
        });
        LinearLayout.LayoutParams aal = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(48));
        aal.topMargin = dp(8);
        ac.addView(addAlarm, aal);
        alarmList = new LinearLayout(this);
        alarmList.setOrientation(LinearLayout.VERTICAL);
        ac.addView(alarmList);
        col.addView(ac);

        LinearLayout about = card();
        about.addView(text("О приложении", 16, TEXT));
        about.addView(text("Алиса Дом 2.0 · нативное приложение\nПанель: " + base(), 12, MUTED));
        col.addView(about);

        return scroll(col);
    }

    private int tmpOffset = 0;

    private View tile(String name, TextView value) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        GradientDrawable g = new GradientDrawable();
        g.setColor(CARD2);
        g.setCornerRadius(dp(16));
        l.setBackground(g);
        l.setPadding(dp(12), dp(10), dp(12), dp(10));
        TextView t = text(name, 11, MUTED);
        l.addView(t);
        l.addView(value);
        return l;
    }

    // ---------- http ----------

    private String http(String method, String path, String body) {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(base() + path).openConnection();
            c.setRequestMethod(method);
            c.setConnectTimeout(4000);
            c.setReadTimeout(20000);
            if (body != null) {
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                OutputStream os = c.getOutputStream();
                os.write(body.getBytes("UTF-8"));
                os.close();
            }
            BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), "UTF-8"));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) sb.append(line);
            r.close();
            c.disconnect();
            return sb.toString();
        } catch (Exception e) {
            return null;
        }
    }

    private void getAsync(String path, final Result cb) {
        pool.execute(() -> {
            final String out = http("GET", path, null);
            ui.post(() -> cb.run(out == null ? null : out));
        });
    }

    private void postJson(String path, String body) {
        pool.execute(() -> {
            http("POST", path, body);
            ui.post(this::refresh);
        });
    }

    private void postOut(String target) {
        postJson("/api/out", "{\"target\":\"" + target + "\"}");
    }

    private interface Result { void run(String out); }

    // ---------- refresh ----------

    private void startPolling() {
        ui.postDelayed(new Runnable() {
            public void run() {
                refresh();
                tick++;
                ui.postDelayed(this, 3000);
            }
        }, 500);
    }

    private void refresh() {
        getAsync("/api/state", out -> {
            if (out == null) { homeSub.setText("нет связи"); return; }
            try {
                JSONObject o = new JSONObject(out);
                JSONObject p = o.optJSONObject("player");
                JSONObject s = o.optJSONObject("sound");
                JSONObject eq = o.optJSONObject("eq");
                if (p != null) applyPlayer(p);
                if (s != null) applySound(s);
                if (eq != null) applyEqState(eq);
            } catch (Exception ignored) {}
        });

        if (tab == 0) {
            getAsync("/api/bt", out -> {
                if (out != null) try { applyBt(new JSONObject(out)); } catch (Exception ignored) {}
            });
            if (tick % 40 == 0 || weatherRow.getChildCount() == 0) {
                getAsync("/api/weather", out -> {
                    if (out != null) try { applyWeather(new JSONObject(out)); } catch (Exception ignored) {}
                });
            }
        }
        if (tab == 2) {
            getAsync("/api/favorites", out -> {
                if (out != null) try { applyFavs(new JSONObject(out)); } catch (Exception ignored) {}
            });
            getAsync("/api/queue", out -> {
                if (out != null) try { applyQueue(new JSONObject(out)); } catch (Exception ignored) {}
            });
        }
        if (tab == 3) {
            getAsync("/api/sys", out -> {
                if (out != null) try { applySys(new JSONObject(out)); } catch (Exception ignored) {}
            });
            getAsync("/api/alarms", out -> {
                if (out != null) try { applyAlarms(new JSONObject(out)); } catch (Exception ignored) {}
            });
        }
    }

    private String mmss(long ms) {
        long s = Math.max(0, ms) / 1000;
        return (s / 60) + ":" + String.format("%02d", s % 60);
    }

    private void applyPlayer(JSONObject p) {
        String title = p.optString("title", "");
        String artists = p.optString("artists", "");
        String status = p.optString("status", "");
        boolean playing = status.equals("playing") || status.equals("buffering");
        homeTitle = homeTitle;
        homeSub.setText(title.isEmpty() ? "Готова слушать" : (artists.isEmpty() ? title : artists));
        chipTitle.setText(title.isEmpty() ? "Сейчас играет" : title);
        homePlay.setText(playing ? "II" : "▶");
        mTitle.setText(title.isEmpty() ? "Ничего не играет" : title);
        mArtist.setText((artists + " · " + status).trim());
        mToggle.setText(playing ? "II" : "▶");
        long dur = p.optLong("duration_ms", 0);
        long pos = p.optLong("position_ms", 0);
        mDur.setText(mmss(dur));
        mPos.setText(mmss(pos));
        if (!seeking && dur > 0) mSeek.setProgress((int) (pos * 1000 / dur));
    }

    private void applySound(JSONObject s) {
        eqSwitch.setChecked(s.optBoolean("eq", true));
        drcSwitch.setChecked(s.optBoolean("drc", true));
    }

    private void applyEqState(JSONObject eq) {
        if (eq.optBoolean("applying", false)) {
            eqStatus.setText("Применяю… (~15 с)");
            applyEq.setEnabled(false);
        } else {
            eqStatus.setText("");
            applyEq.setEnabled(true);
            JSONArray g = eq.optJSONArray("gains");
            if (g != null && !seeking && tab == 1) {
                for (int i = 0; i < Math.min(5, g.length()); i++) {
                    int v = g.optInt(i, 0);
                    if (bands[i] != null && bands[i].getProgress() != v + 12) {
                        bands[i].setProgress(v + 12);
                    }
                }
            }
        }
    }

    private void applyBt(JSONObject o) {
        JSONArray arr = o.optJSONArray("devices");
        devList.removeAllViews();
        int n = arr == null ? 0 : arr.length();
        devCount.setText(n + " устр.");
        for (int i = 0; i < n; i++) {
            JSONObject d = arr.optJSONObject(i);
            if (d == null) continue;
            LinearLayout line = row();
            line.setPadding(0, dp(8), 0, dp(8));
            TextView t = text(d.optString("name", "?"), 14, TEXT);
            TextView sub = text(d.optString("mac", ""), 11, MUTED);
            LinearLayout box = new LinearLayout(this);
            box.setOrientation(LinearLayout.VERTICAL);
            box.addView(t);
            box.addView(sub);
            line.addView(box, new LinearLayout.LayoutParams(0,
                    ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            final String mac = d.optString("mac", "");
            final boolean connected = d.optBoolean("connected", false);
            Button b = button(connected ? "Отключить" : "Подключить", false);
            b.setOnClickListener(v -> postJson("/api/bt",
                    "{\"action\":\"" + (connected ? "disconnect" : "pair") + "\",\"mac\":\"" + mac + "\"}"));
            line.addView(b, new LinearLayout.LayoutParams(dp(120), dp(42)));
            devList.addView(line);
        }
        String output = o.optString("output", "spk");
        chipOut.setText(output.equals("bt") ? "Усилитель" : "Колонка");
        outSpk.setEnabled(!output.equals("spk"));
        outBt.setEnabled(!output.equals("bt"));
    }

    private void applyWeather(JSONObject o) {
        weatherCity.setText(o.optString("city", ""));
        JSONArray arr = o.optJSONArray("hours");
        weatherRow.removeAllViews();
        if (arr == null) return;
        java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("HH:mm",
                java.util.Locale.getDefault());
        f.setTimeZone(java.util.TimeZone.getDefault());
        for (int i = 0; i < Math.min(12, arr.length()); i++) {
            JSONObject h = arr.optJSONObject(i);
            if (h == null) continue;
            String time = h.optString("t", "");
            String label = "";
            try {
                java.util.Date d = new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'",
                        java.util.Locale.US).parse(time);
                if (d != null) label = f.format(d);
            } catch (Exception ignored) {}
            int temp = h.optInt("temp", 0);
            double precip = h.optDouble("precip", 0);
            LinearLayout chip = new LinearLayout(this);
            chip.setOrientation(LinearLayout.VERTICAL);
            GradientDrawable g = new GradientDrawable();
            g.setColor(CARD2);
            g.setCornerRadius(dp(14));
            chip.setBackground(g);
            chip.setPadding(dp(10), dp(8), dp(10), dp(8));
            chip.addView(text(label, 10, MUTED));
            chip.addView(text((temp > 0 ? "+" : "") + temp + "°", 15, TEXT));
            chip.addView(text(precip > 0 ? precip + " мм" : " ", 9, MUTED));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(62),
                    ViewGroup.LayoutParams.WRAP_CONTENT);
            lp.rightMargin = dp(6);
            weatherRow.addView(chip, lp);
        }
    }

    private void applyFavs(JSONObject o) {
        JSONArray arr = o.optJSONArray("favorites");
        favList.removeAllViews();
        int n = arr == null ? 0 : arr.length();
        favCount.setText(n + " шт.");
        for (int i = 0; i < n; i++) {
            JSONObject f = arr.optJSONObject(i);
            if (f == null) continue;
            final String id = f.optString("id", "");
            final int idx = i;
            LinearLayout line = row();
            line.setPadding(0, dp(8), 0, dp(8));
            LinearLayout box = new LinearLayout(this);
            box.setOrientation(LinearLayout.VERTICAL);
            box.addView(text(f.optString("title", ""), 14, TEXT));
            box.addView(text(f.optString("artists", ""), 11, MUTED));
            box.setOnClickListener(v -> postJson("/api/favorites",
                    "{\"action\":\"play\",\"index\":" + idx + "}"));
            line.addView(box, new LinearLayout.LayoutParams(0,
                    ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            Button del = button("✕", false);
            del.setOnClickListener(v -> postJson("/api/favorites",
                    "{\"action\":\"remove\",\"id\":\"" + id + "\"}"));
            line.addView(del, new LinearLayout.LayoutParams(dp(56), dp(40)));
            favList.addView(line);
        }
    }

    private void applyQueue(JSONObject o) {
        JSONArray arr = o.optJSONArray("queue");
        queueList.removeAllViews();
        int index = o.optInt("index", 0);
        int n = arr == null ? 0 : arr.length();
        qCount.setText(n > 0 ? (index + 1) + " / " + n : "пусто");
        int limit = queueExpanded ? n : Math.min(5, n);
        for (int i = 0; i < limit; i++) {
            JSONObject t = arr.optJSONObject(i);
            if (t == null) continue;
            final int num = i + 1;
            LinearLayout line = new LinearLayout(this);
            line.setOrientation(LinearLayout.VERTICAL);
            line.setPadding(0, dp(8), 0, dp(8));
            String prefix = i == index ? "▶ " : "";
            line.addView(text(prefix + t.optString("title", ""), 14,
                    i == index ? ACCENT : TEXT));
            line.addView(text(t.optString("artists", ""), 11, MUTED));
            line.setOnClickListener(v -> postJson("/api/queue",
                    "{\"number\":" + num + "}"));
            queueList.addView(line);
        }
    }

    private void applySys(JSONObject o) {
        sysUp.setText("работает " + o.optDouble("uptime_h", 0) + " ч");
        JSONArray load = o.optJSONArray("load");
        sysCpu.setText(load != null ? load.optString(0) : "—");
        sysTemp.setText(o.optDouble("temp_c", 0) + "°");
        sysMem.setText(o.optInt("mem_used_mb", 0) + " / " + o.optInt("mem_total_mb", 0) + " МБ");
        sysDisk.setText(o.optInt("disk_used_mb", 0) + " / " + o.optInt("disk_total_mb", 0) + " МБ");
    }

    private void applyAlarms(JSONObject o) {
        JSONArray arr = o.optJSONArray("alarms");
        alarmList.removeAllViews();
        int n = arr == null ? 0 : arr.length();
        for (int i = 0; i < n; i++) {
            JSONObject a = arr.optJSONObject(i);
            if (a == null) continue;
            final int idx = i;
            int m = a.optInt("minutes", 0);
            LinearLayout line = row();
            line.setPadding(0, dp(8), 0, dp(8));
            LinearLayout box = new LinearLayout(this);
            box.setOrientation(LinearLayout.VERTICAL);
            box.addView(text(String.format("%02d:%02d", m / 60, m % 60), 15, TEXT));
            box.addView(text(a.optString("query", "подборка"), 11, MUTED));
            line.addView(box, new LinearLayout.LayoutParams(0,
                    ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            Button del = button("✕", false);
            del.setOnClickListener(v -> postJson("/api/alarms",
                    "{\"action\":\"remove\",\"index\":" + idx + "}"));
            line.addView(del, new LinearLayout.LayoutParams(dp(56), dp(40)));
            alarmList.addView(line);
        }
    }

    // ---------- actions ----------

    private void applyEq() {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < 5; i++) {
            if (i > 0) sb.append(",");
            sb.append(bands[i].getProgress() - 12);
        }
        sb.append("]");
        eqStatus.setText("Применяю… (~15 с)");
        applyEq.setEnabled(false);
        postJson("/api/eq", "{\"gains\":" + sb + ",\"enabled\":true}");
    }

    private void editUrl() {
        final EditText input = new EditText(this);
        input.setText(base());
        input.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        new AlertDialog.Builder(this)
                .setTitle("Адрес панели")
                .setView(input)
                .setPositiveButton("Сохранить", (d, w) -> {
                    String url = input.getText().toString().trim();
                    if (!url.startsWith("http")) url = "http://" + url;
                    getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                            .putString(KEY_URL, url).apply();
                    refresh();
                })
                .setNegativeButton("Отмена", null)
                .show();
    }

    @Override
    protected void onNewIntent(android.content.Intent intent) {
        super.onNewIntent(intent);
        int t = intent.getIntExtra("tab", -1);
        if (t >= 0 && t <= 3) showTab(t);
    }

    @Override
    public void onBackPressed() {
        if (tab != 0) {
            showTab(0);
        } else {
            super.onBackPressed();
        }
    }
}
