# -*- coding: utf-8 -*-
"""Durak arama indeksi — hızlandırma sonucu DEĞİŞTİRMEMELİ.

Arama, rota hesabının %50'sini yiyordu: her sorguda 15.112 durağın adı ve
ilçesi yeniden token'lara ayrılıyordu (tek istekte 241.800 `_tokenize`).
Token önbelleği + trigram tersine indeksi eklendi.

Bu dosyanın asıl işi tek bir soruyu yanıtlamak: **indeksin elediği
duraklarda gerçekten puan yok muydu?** İndeks kapalıyken (bütün duraklar
taranır) ve açıkken çıkan sonuçlar birebir aynı olmalı. Aksi hâlde
hızlandırma sessizce doğruluk bozar — ölçülmeden yapılan optimizasyonun
klasik tuzağı.
"""
import json
import os
import subprocess
import sys

import pytest

PROJE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SORGULAR = [
    "Avcılar", "Zincirlikuyu", "Bakırköy", "Üsküdar", "Kadıköy",
    "Söğütlüçeşme", "Mecidiyeköy", "Akik sitesi", "Taksim", "Beylikdüzü",
    "şişli", "eminönü", "kartal", "pendik", "levent", "bağcılar",
    "ataşehir merkez", "olmayan bir durak", "xyzq", "a", "15 temmuz",
]

# İki yolu ayrı süreçte çalıştıran betik: aynı sorgular, farklı mod.
BETIK = r'''
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PROJE = sys.argv[1]
MOD = sys.argv[2]
if MOD == "indekssiz":
    os.environ["DURAK_ARAMA_INDEKSSIZ"] = "1"
sys.path.insert(0, PROJE)
# .env kosulsuz acilirsa TEMIZ KLONDA bu test coker: dosya .gitignore'da,
# yani depoyu indiren kimsede yok. Zaten arama diskteki durak verisiyle
# calisiyor, kimlik gerekmiyor. (Ayni hata scripts/ altindaki iki betikte
# de vardi; orada da duzeltildi.)
_ENV = os.path.join(PROJE, ".env")
for satir in (open(_ENV, encoding="utf-8") if os.path.exists(_ENV) else []):
    satir = satir.strip()
    if satir and "=" in satir and not satir.startswith("#"):
        k, _, v = satir.partition("="); os.environ.setdefault(k.strip(), v.strip())

import services as s
s.load_panel_data(); s.load_hat_profil(); s.sira_diskten_yukle()
with open(os.path.join(PROJE, "memory_db.json"), encoding="utf-8") as f:
    s.MEMORY_DB.update({k: set(v) for k, v in json.load(f).items()})
s.IS_DB_READY = True
with open(os.path.join(PROJE, "durak_dict.json"), encoding="utf-8") as f:
    s.DURAK_DICT.update(json.load(f))

import routes
from flask import Flask
app = Flask(__name__, template_folder=os.path.join(PROJE, "templates"))
routes.register_routes(app, None)
c = app.test_client()

sorgular = json.loads(sys.argv[3])
cikti = {}
for q in sorgular:
    r = c.get("/api/durak_ara", query_string={"q": q})
    try:
        cikti[q] = r.get_json()
    except Exception:
        cikti[q] = None
print("###JSON###")
print(json.dumps(cikti, ensure_ascii=False, sort_keys=True))
'''


def _calistir(mod):
    r = subprocess.run(
        [sys.executable, "-c", BETIK, PROJE, mod, json.dumps(SORGULAR)],
        capture_output=True, text=True, encoding="utf-8", timeout=600,
    )
    assert "###JSON###" in r.stdout, (
        "%s modu çalışmadı:\n%s\n%s" % (mod, r.stdout[-800:], r.stderr[-800:]))
    return json.loads(r.stdout.split("###JSON###", 1)[1].strip())


@pytest.mark.slow
def test_indeksli_ve_indekssiz_sonuclar_ayni():
    """Trigram daraltması hiçbir geçerli sonucu elemiyor."""
    indeksli = _calistir("indeksli")
    indekssiz = _calistir("indekssiz")

    farklar = []
    for q in SORGULAR:
        if indeksli.get(q) != indekssiz.get(q):
            farklar.append(q)

    assert not farklar, (
        "İndeks sonucu değiştirdi — şu sorgularda fark var: %s\n"
        "indeksli:  %s\nindekssiz: %s"
        % (farklar,
           json.dumps(indeksli.get(farklar[0]), ensure_ascii=False)[:300],
           json.dumps(indekssiz.get(farklar[0]), ensure_ascii=False)[:300])
    )
