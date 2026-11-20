# Model — GTA VI trophy rarity forecast (gta6-trophy-rarity-forecast-01)

## Ringkasnya

Program meramalkan, untuk tiap trofi GTA VI di PS5, persen pemain yang
dilacak Exophase yang akan memegang trofi itu pada 26 Nov 2026 00:00 UTC,
dari semua pembacaan halaman trofi Exophase sampai deadline 21 Nov 2026
11:30 UTC. Skornya pinball loss pada skala logit; yang menang adalah
ramalan paling akurat dengan sebaran yang jujur — dan hadiah menuntut
loss di bawah entri house terbaik (baseline persistensi, baseline kurva,
dan forecast model house).

## Model: dilusi + earning, dalam hitungan pemain

Satu angka rarity adalah rasio `r = E / P` (pemegang / pemain terlacak).
Exophase hanya bergerak saat me-refresh halaman game (selang beberapa
jam, menurut jadwalnya sendiri). Dua gaya bekerja:

- **Dilusi** — pemain baru memegang tiap trofi dengan rate lebih rendah
  daripada pemain yang sudah dilacak, jadi refresh menekan rate ke
  bawah, paling keras untuk trofi langka.
- **Earning** — pemain yang sudah dilacak terus bermain dan mendapat
  trofi baru, jadi `E` tumbuh dan menaikkan rate, paling cepat untuk
  trofi awal yang mudah.

Program memulihkan keduanya dari histori kasusnya sendiri:

1. Pembacaan dirapatkan menjadi state-state berbeda (Exophase datar di
   antara refresh).
2. Per trofi, regresi ridge atas tiap interval antar state:
   `dE = g * P_avg * dh + q * dP`, dengan `g` = laju earning per pemain
   per jam dan `q` = rate pegangan pemain baru. Regresi berjalan dalam
   ruang rate (`dE / P_avg = g*dh + q*(dP/P_avg)`), interval dibobot
   menurut kebaruan (half-life 24 jam — rezim malam peluncuran, dengan
   kohort pertama yang kecil dan fanatik, berperilaku lain daripada
   rezim stabil di dekat checkpoint), dan ridge kecil menarik kedua
   koefisien ke prior kelas trofi (dari tier/nama/deskripsi di kasus
   itu sendiri) bila histori tipis atau kedua sukunya kolinear.
3. Pemain terlacak di target: laju pertumbuhan harian terakhir,
   diluruhkan eksponensial dengan konstanta waktu 1 hari (base tumbuh
   eksplosif di awal lalu jenuh; fit power-law atas seluruh histori
   terbukti over-ekstrapolasi berat — 395 ribu vs 85 ribu yang benar
   pada uji sintetis).
4. `E(target) = E(terakhir) + g * P_avg_masa_depan * dh + q * (P(target)
   - P(terakhir))`, `r(target) = E(target) / P(target)`.
5. Bila histori tidak menunjukkan dinamika sama sekali (satu state
   datar, seperti pada kasus practice), program memakai prior refresh:
   satu refresh sebelum target, pemain terlacak berlipat ~5x (refresh
   pertama yang tercatat melipatgandakan 6,06x), dan rate pegangan pemain
   baru dibagi antar trofi menurut kelas, dikalibrasi agar totalnya sama
   dengan refresh pertama yang terukur (3.333 trofi oleh 3.230 pemain
   baru, di luar trofi misi pertama yang bertahan 100%).
6. Kuantil logit-normal di sekitar median; sebaran tumbuh mengikuti
   besarnya gerakan yang diramal, ketidakpastian pertumbuhan pemain
   terlacak, dan horizon.

Kelas trofi (dari metadata di kasus): platinum (butuh semua trofi lain,
~200 jam — tidak ada yang mendapatkannya di minggu pertama), saturated
(rate ≥ 90% — misi pertama), story (chapter / misi final), side (misi
final untuk stranger), grind (hitungan, koleksi, medali), misc.

## Yang diketahui vs yang diasumsikan

**Diketahui (dari data):**

- Daftar 55 trofi (nama, deskripsi, tier) berasal dari berkas kasus —
  yaitu dari halaman Exophase sebagaimana direkam house. Rockstar, Sony,
  dan Microsoft TIDAK pernah menerbitkan daftar trofi resmi sebelum
  rilis; daftar itu baru publik saat game unlock 18–19 Nov 2026, dan
  semua tracker/outlet sepakat soal 55 nama itu.
- Refresh malam peluncuran adalah data house sendiri (dinyatakan di
  spek kompetisi): pemain terlacak 638 → 3.868, total trofi didapat
  943 → 4.276, semua rate kecuali yang 100% turun. Total pegangan
  pemain baru per trofi adalah ukuran; PEMBAGIANNYA per trofi adalah
  prior, bukan pengukuran.
- Spek kompetisi menyatakan kedua kasus practice memang dirancang
  mengangkangi refresh itu ("the practice rewards a forecast that
  expects a refresh") — jadi median pada rezim tanpa dinamika memang
  memprediksi refresh.

**Dipakai hanya sebagai bentuk prior (bukan data):**

- Cermin publik halaman Exophase pada 20 Nov 2026 (~38 jam setelah
  rilis): misi pertama 93,27% pemain terlacak, Chapter 1 0,47%, misi
  final 0,28%, platinum 0,00%. Cerita butuh ~80 jam; hampir tidak ada
  yang menamatkannya di minggu pertama.
- Rate seumur hidup GTA V (misi pertama 43,2%, misi final 8,7–16,8%,
  platinum 0,1%) sebagai batas atas apa yang bisa dicapai rate minggu
  pertama.

**Ketidakpastian terbesar:** waktu refresh Exophase. Jawabannya adalah
halaman per refresh terakhir sebelum target; bila refresh terakhir
jatuh jauh sebelum target, rate-nya lebih basi (earning dan dilusi lebih
sedikit) daripada yang diasumsikan median. Sebaran dirancang menutup
itu — dan pada uji practice, cakupan 90% tercatat 0,89–0,96.

## Validasi lokal

Jawaban practice yang sebenarnya tersegel di server, jadi validasi
memakai dua rekonstruksi jawaban yang memenuhi agregat spek secara
eksak (pemain terlacak 3.868, total trofi 4.276, trofi misi pertama
tetap 100%): A = proporsional (pemain baru memegang tiap trofi pada
6,67% dari rate kohort pertama), B = bertingkat menurut kelas
(story/misc/side/grind 20/15/10/3% dari rate kohort pertama, diskalakan
ke total yang sama). Baseline persistensi (house baseline) pada
rekonstruksi yang sama mencetak ~1,40–1,41 — dekat dengan ~1,51 yang
dinyatakan spek untuk jawaban sebenarnya — jadi perbandingan ini dapat
dipercaya arahnya.

| Skenario | Entri ini (loss) | Persistensi (loss) | Miss tipikal | Cakupan 90% |
|---|---|---|---|---|
| practice p00, rekonstruksi A | 0,337 | 1,405 | 0,17 pp | 0,89 |
| practice p00, rekonstruksi B | 0,322 | 1,412 | 0,16 pp | 0,96 |
| practice p01, rekonstruksi A | 0,360 | 1,405 | 0,18 pp | 0,89 |
| practice p01, rekonstruksi B | 0,343 | 1,412 | 0,18 pp | 0,96 |
| final sintetis | 0,228 | 0,823 | 4,60 pp | 1,00 |

Final sintetis: kasus f00 yang disimulasikan dari state 04:30 ke
deadline 21 Nov 11:30 dan jawaban 26 Nov 00:00, dengan dinamika "benar"
yang sengaja dibuat BERBEDA dari prior model (rasio pemain baru,
laju earning, dan pertumbuhan pemain terlacak berbeda) — jadi uji ini
mengukur apakah program memulihkan dinamika dari histori, bukan
sekadar mengulang priornya. Entri ini mengalahkan persistensi ~3,6x
di situ. Catatan jujur: skenario sintetis itu masih jauh lebih
optimistis soal progres cerita daripada kenyataan (Chapter 1 mencapai
29% pada jawabannya, sementara data 20 Nov menunjukkan 0,47%) — jadi
angka absolutnya jangan dibaca sebagai prediksi skor final; yang
diuji adalah mesinnya, bukan dunia nyatanya.

Determinisme: dua kali jalan pada kasus yang sama menghasilkan output
byte-identik. Waktu jalan ~0,01 detik per kasus (batas 8 detik).

## Batas-batas

- Program tidak pernah membaca jaringan dan tidak memakai angka luar
  saat berjalan; semua yang dibutuhkannya ada di berkas kasus.
- Bila histori hanya punya satu state, ramalan bersandar penuh pada
  prior refresh — tepat untuk practice, tetapi akan meleset bila
  Exophase mengubah kadens refreshnya secara drastis.
- Pemisahan earning vs dilusi secara inheren kolinear (refresh selalu
  memasangkan jam berlalu dengan pemain bertambah); ridge dan bobot
  kebaruan menstabilkannya, tetapi trofi yang pergerakannya didominasi
  satu gaya saja bisa salah bagi.
- Platinum dan trofi 100% completion diramalkan mendekati 0,01% (batas
  bawah clamp) — benar secara praktis, tetapi bila satu pemain
  menyelesaikan 100% sebelum 26 Nov, rate-nya tetap di bawah 0,01%
  untuk base sebesar itu.
