# Ramalan Rarity Trofi GTA VI di Exophase

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/wengki620-prog/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/wengki620-prog/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Entri untuk **gta6-trophy-rarity-forecast-01**: program yang meramalkan,
untuk setiap trofi Grand Theft Auto VI di PlayStation 5, persen pemain
yang dilacak Exophase yang akan memegang trofi itu pada 26 November 2026
pukul 00:00 UTC — seminggu setelah rilis — sebagai lima kuantil per trofi,
dari semua pembacaan halaman trofi Exophase yang direkam house sampai
deadline 21 November 2026 pukul 11:30 UTC.

## Cara kerja

Satu angka rarity adalah rasio: `r = E / P`, pemegang dibagi pemain yang
dilacak. Exophase hanya bergerak saat me-refresh halaman gamenya (selang
beberapa jam, menurut jadwalnya sendiri): saat refresh, `P` melonjak
karena profil baru tersinkronisasi, dan `E` ikut melonjak. Dua gaya yang
saling tarik:

- **Dilusi:** pemain baru memegang tiap trofi dengan rate lebih rendah
  daripada pemain yang sudah dilacak, jadi refresh menekan rate ke bawah
  — paling keras untuk trofi langka. Malam peluncuran membuktikannya:
  refresh pertama menaikkan pemain terlacak dari 638 ke 3.868 sementara
  total trofi yang didapat naik dari 943 ke 4.276 — jadi 3.230 pemain baru
  itu memegang 3.333 trofi, sekitar 1,03 per orang, melawan 1,48 per
  orang untuk 638 pemain pertama. Semua rate kecuali yang 100% turun.
- **Earning:** pemain yang sudah dilacak terus bermain dan mendapat trofi
  baru, jadi `E` tumbuh seiring waktu bermain dan menaikkan rate — paling
  cepat untuk trofi awal yang mudah.

Program ini memulihkan kedua gaya itu dari histori kasusnya sendiri. Ia
merapatkan pembacaan menjadi state-state berbeda (Exophase datar di antara
refresh), lalu per trofi meregresi perubahan pemegang tiap interval
terhadap jam yang berlalu dan pemain yang bertambah: `dE = a*dh + q*dP`
(`a` = laju earning pemain lama, `q` = rate pegangan pemain baru),
dengan ridge ke prior kelas trofi bila histori tipis. Pemain terlacak di
target diramalkan dari fit power-law `log P` terhadap `log(1 + jam sejak
rilis)`. Ramalannya lalu `E(target) = E(terakhir) + a*dh + q*(P(target) -
P(terakhir))`, `r(target) = E(target) / P(target)`. Kuantilnya
logit-normal di sekitar median, dengan sebaran yang melebar mengikuti
besarnya gerakan yang diramal, ketidakpastian pertumbuhan pemain
terlacak, dan horizon. Detail lengkap + asumsi dan kejujuran soal
ketidakpastian: lihat `MODEL.md`.

## Cara menjalankan

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Program membaca tiap berkas `*.in` di direktori input dan menulis satu
berkas `.out` per kasus ke direktori output: `{"trophies": [{"id": n,
"q": [q05, q25, q50, q75, q95]}, ...]}`, satu baris per trofi. Tanpa
variabel lingkungan, program membaca `/input/` dan menulis `/output/`.

Python 3.13, pustaka standar saja, tanpa jaringan, deterministis:
dijalankan dua kali, keluarannya byte-identik. Waktu jalan sekitar
0,01 detik per kasus (batas 8 detik).

## Struktur

```
main.py   program utama (Python 3.13, pustaka standar saja)
MODEL.md  model, asumsi, riset, dan hasil validasi lokal
LICENSE   lisensi MIT
```

## Catatan

Ramalan ini adalah perkiraan model entri ini, bukan angka resmi Exophase
dan bukan saran apa pun. Entri ini murni program peramal: tidak membaca
Exophase saat berjalan dan tidak memperdagangkan apa pun.

Lisensi: MIT. Lihat `LICENSE`.

---

<sub>Entered on [make.fun](https://make.fun/?ref=vaskwypj&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
