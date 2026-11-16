/*
 * eqrelay вЂ” ALSA loopback relay with a 5-band parametric EQ.
 *
 * Reads S16 stereo from a capture PCM, applies five peaking biquads per channel,
 * writes the result to a playback PCM. Gains are read from a small text file
 * (five numbers in dB) and hot-reloaded while running.
 *
 * Build (cross): zig cc -target aarch64-linux-gnu -O2 eqrelay.c libasound.so.2 -o eqrelay
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>

/* minimal alsa declarations: avoids pulling alsa headers onto the build host */
typedef struct _snd_pcm snd_pcm_t;
extern int snd_pcm_open(snd_pcm_t **pcm, const char *name, int stream, int mode);
extern int snd_pcm_set_params(snd_pcm_t *pcm, int format, int access,
                              unsigned int channels, unsigned int rate,
                              int soft_resample, unsigned int latency);
extern long snd_pcm_readi(snd_pcm_t *pcm, void *buf, unsigned long frames);
extern long snd_pcm_writei(snd_pcm_t *pcm, const void *buf, unsigned long frames);
extern int snd_pcm_prepare(snd_pcm_t *pcm);
extern int snd_pcm_start(snd_pcm_t *pcm);
extern int snd_pcm_recover(snd_pcm_t *pcm, int err, int silent);
extern int snd_pcm_close(snd_pcm_t *pcm);

#define STREAM_PLAYBACK 0
#define STREAM_CAPTURE 1
#define FMT_S16_LE 2
#define ACCESS_RW_INTERLEAVED 3

#define CHANNELS 2
#define FRAMES 512
#define BANDS 5
#define RATE 48000

static const double FREQS[BANDS] = {60.0, 230.0, 910.0, 3600.0, 14000.0};
static const double QS[BANDS] = {0.9, 1.0, 1.1, 1.2, 1.3};

typedef struct {
    double b0, b1, b2, a1, a2;
    double x1, x2, y1, y2;
} biquad;

static biquad bands[CHANNELS][BANDS];
static double gains[BANDS] = {0, 0, 0, 0, 0};
static const char *gains_path = "/data/eq/gains.txt";

static void calc_band(biquad *bq, double f0, double q, double gain_db) {
    double A = pow(10.0, gain_db / 40.0);
    double w0 = 2.0 * M_PI * f0 / (double) RATE;
    double alpha = sin(w0) / (2.0 * q);
    double a0 = 1.0 + alpha / A;
    bq->b0 = (1.0 + alpha * A) / a0;
    bq->b1 = (-2.0 * cos(w0)) / a0;
    bq->b2 = (1.0 - alpha * A) / a0;
    bq->a1 = (-2.0 * cos(w0)) / a0;
    bq->a2 = (1.0 - alpha / A) / a0;
}

static void recalc(void) {
    for (int c = 0; c < CHANNELS; c++) {
        for (int i = 0; i < BANDS; i++) {
            calc_band(&bands[c][i], FREQS[i], QS[i], gains[i]);
        }
    }
}

static void load_gains(void) {
    FILE *f = fopen(gains_path, "r");
    if (!f) return;
    double v[BANDS];
    int n = fscanf(f, "%lf %lf %lf %lf %lf", &v[0], &v[1], &v[2], &v[3], &v[4]);
    fclose(f);
    if (n == BANDS) {
        int changed = 0;
        for (int i = 0; i < BANDS; i++) {
            if (v[i] > 12.0) v[i] = 12.0;
            if (v[i] < -12.0) v[i] = -12.0;
            if (fabs(v[i] - gains[i]) > 0.001) changed = 1;
            gains[i] = v[i];
        }
        if (changed) recalc();
    }
}

static inline double process(biquad *bq, double x) {
    double y = bq->b0 * x + bq->b1 * bq->x1 + bq->b2 * bq->x2
             - bq->a1 * bq->y1 - bq->a2 * bq->y2;
    bq->x2 = bq->x1;
    bq->x1 = x;
    bq->y2 = bq->y1;
    bq->y1 = y;
    return y;
}

int main(int argc, char **argv) {
    const char *in_dev = argc > 1 ? argv[1] : "hw:Loopback,1,0";
    const char *out_dev = argc > 2 ? argv[2] : "hw:0,0";
    if (argc > 3) gains_path = argv[3];

    snd_pcm_t *in = NULL, *out = NULL;
    int err;

    if ((err = snd_pcm_open(&in, in_dev, STREAM_CAPTURE, 1)) < 0) {
        fprintf(stderr, "capture open %s failed: %d\n", in_dev, err);
        return 1;
    }
    if ((err = snd_pcm_open(&out, out_dev, STREAM_PLAYBACK, 0)) < 0) {
        fprintf(stderr, "playback open %s failed: %d\n", out_dev, err);
        return 1;
    }

    if ((err = snd_pcm_set_params(in, FMT_S16_LE, ACCESS_RW_INTERLEAVED,
                                  CHANNELS, RATE, 1, 20000)) < 0) {
        fprintf(stderr, "capture params failed: %d\n", err);
        return 1;
    }
    if ((err = snd_pcm_set_params(out, FMT_S16_LE, ACCESS_RW_INTERLEAVED,
                                  CHANNELS, RATE, 1, 20000)) < 0) {
        fprintf(stderr, "playback params failed: %d\n", err);
        return 1;
    }

    /* capture streams on aloop do not start themselves */    snd_pcm_start(in);
    snd_pcm_start(out);

    load_gains();
    recalc();
    fprintf(stderr, "eqrelay: %s -> %s, gains %.1f %.1f %.1f %.1f %.1f\n",
            in_dev, out_dev, gains[0], gains[1], gains[2], gains[3], gains[4]);

    static short buf[FRAMES * CHANNELS];
    long counter = 0;
    long idle = 0;

    while (1) {
        long n = snd_pcm_readi(in, buf, FRAMES);
        if (counter < 300) {
            fprintf(stderr, "eqrelay: read %ld frames\n", n);
        }
        if (n == -11 || n == -EAGAIN) {
            /* no data yet: give the loopback a moment, restart the stream now and then */
            if (++idle % 500 == 0) {
                snd_pcm_prepare(in);
                snd_pcm_start(in);
                fprintf(stderr, "eqrelay: capture restarted after idle\n");
            }
            usleep(2000);
            continue;
        }
        if (n < 0) {
            snd_pcm_recover(in, (int) n, 1);
            snd_pcm_prepare(in);
            snd_pcm_start(in);
            usleep(2000);
            continue;
        }
        if (n == 0) continue;

        for (long i = 0; i < n; i++) {
            for (int c = 0; c < CHANNELS; c++) {
                double x = (double) buf[i * CHANNELS + c];
                for (int b = 0; b < BANDS; b++) {
                    x = process(&bands[c][b], x);
                }
                if (x > 32767.0) x = 32767.0;
                if (x < -32768.0) x = -32768.0;
                buf[i * CHANNELS + c] = (short) x;
            }
        }

        long written = 0;
        while (written < n) {
            long w = snd_pcm_writei(out, buf + written * CHANNELS, (unsigned long) (n - written));
            if (w < 0) {
                snd_pcm_recover(out, (int) w, 1);
                snd_pcm_prepare(out);
                break;
            }
            written += w;
        }

        if (++counter % 50 == 0) {
            load_gains();
            double acc = 0;
            for (long i = 0; i < n * CHANNELS; i += 8) acc += (double) buf[i] * buf[i];
            double rms = sqrt(acc / (double) ((n * CHANNELS) / 8 + 1));
            fprintf(stderr, "eqrelay: frames=%ld rms=%.0f gains=%.1f/%.1f/%.1f/%.1f/%.1f\n",
                    counter, rms, gains[0], gains[1], gains[2], gains[3], gains[4]);
        }
    }
    return 0;
}







