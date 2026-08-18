
import io
import os
import sys

from flask import Flask, render_template


# ── .env yükleyici — services import edilmeden ÖNCE çalışmalı ─────────────
def _env_yukle(dosya=".env"):
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), dosya)
    if not os.path.exists(yol):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(yol)
    except ImportError:
        with open(yol, encoding="utf-8") as f:
            for satir in f:
                satir = satir.strip()
                if satir and not satir.startswith("#") and "=" in satir:
                    k, _, v = satir.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_env_yukle()

# Windows konsolunda Türkçe karakterler bozulmasın
if (sys.stdout.encoding or "").lower() != "utf-8":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    except Exception as e:
        print(f"Encoding ayarlanamadi: {e}")

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.route("/")
@app.route("/canli")
def canli():
    return render_template("index.html")


# services/routes .env yüklendikten SONRA import edilmeli —
# IETT_USER / IETT_PASS modül seviyesinde okunuyor.
from services import start_background_threads   # noqa: E402
from routes import register_routes              # noqa: E402

# İkinci parametre orijinal imzayla uyum için; kullanılmıyor (MSSQL kaldırıldı).
register_routes(app, None)


if __name__ == "__main__":
    start_background_threads()
    # Port 5001: staj paneli (Desktop/iett staj/iett_panel) 5000'i kullanıyor,
    # ikisi aynı anda çalışabilsin diye ayrıldı.
    print("Baslatiliyor → http://localhost:5001")
    app.run(port=5001, threaded=True, debug=False)
