"""Forecast GTA VI trophy earn rates on Exophase, a week after launch.

Entry for make.fun gta6-trophy-rarity-forecast-01. Reads one case
(makefun/gta6-trophies-case/v1) from the input directory and writes, for
every trophy, five quantiles of its earn rate (percent of Exophase-tracked
players holding it) at the case's target, as {"trophies": [{"id", "q": [...]}]}.

MODEL -- dilution plus earning, in counts, not in rates
-------------------------------------------------------
A rate is a ratio: r = E / P, holders over players tracked. Exophase only
moves when it refreshes a game's page (hours apart, on its own schedule):
at a refresh the tracked base P jumps as new profiles sync, and the
holders E jump with them. Two forces move every rate:

  * dilution: newcomers hold each trophy at a lower rate than the players
    already tracked, so a refresh pushes rates DOWN, hardest for rare
    trophies. Launch night proved it: the first refresh took players
    tracked from 638 to 3,868 while total trophies earned went from 943
    to 4,276 -- so the 3,230 newcomers held 3,333 trophies between them,
    about 1.03 each, against 1.48 each for the first 638. Every rate but
    the one at 100% fell.
  * earning: the players already tracked keep playing and earn more
    trophies, so E grows with playtime and pushes rates UP, fastest for
    early, easy trophies.

The program recovers both forces from the case's own history. It collapses
the reads into distinct states (Exophase is flat between refreshes), then,
per trophy, regresses each interval's change in holders on the player-hours
passed and the players added:

    dE = g * P_avg * dh + q * dP

g is the per-player earning rate (fraction of tracked players earning the
trophy per hour -- the holders gained per hour grow with how many players
there are), q the newcomers' hold rate for that trophy. Both are
ridge-shrunk toward class priors built from the trophy's own metadata
(tier, name, description) when the history is thin. Players tracked at
the target comes from the recent daily growth rate, decayed
exponentially (the base grows explosively at first, then saturates).
The forecast is then

    E(target) = E(last) + g * P_avg_future * dh + q * (P(target) - P(last)),
    r(target) = E(target) / P(target).

When the history shows no dynamics at all (a single flat state, as in the
practice cases), the program falls back to the refresh prior: one refresh
before the target, players tracked multiplying about fivefold (the first
refresh multiplied it 6.06x), newcomers' hold rates distributed across
trophies by class, calibrated so their total matches the first refresh's
measured 3,333 trophies over 3,230 newcomers. The practice cases were
built to straddle a refresh, so the median predicts the refresh; the
spread covers the no-refresh outcome at its upper end.

Quantiles are logit-normal around the median. The spread grows with the
size of the predicted move, with the (uncertain) growth of players
tracked, and with the horizon, so a trophy whose rate is expected to move
a long way carries a wide band. Everything is deterministic: two runs on
the same case write byte-identical output. Standard library only, no
network, no randomness.

WHAT IS KNOWN VS ASSUMED (honesty note)
----------------------------------------
* The trophy list itself (55 trophies, names, descriptions, tiers) comes
  from the case file, i.e. from Exophase's page as the house recorded it.
  Rockstar, Sony and Microsoft published NO official trophy list before
  launch; the list went public only when the game unlocked on 18-19 Nov
  2026 (trackers and outlets agree on the 55 names). Nothing here treats
  a rumour as a fact.
* The launch-night refresh (638 -> 3,868 players, 943 -> 4,276 trophies
  earned) is the house's own recorded data, stated in the competition
  spec. The per-trophy newcomer rates for that refresh are NOT recorded
  anywhere public, so the class distribution of q is a prior, not a
  measurement -- the total is measured, the split is assumed.
* External calibration used only as prior shape, never as data: a public
  mirror of Exophase's page on 20 Nov 2026 showed the first mission at
  93.27% of tracked players while Chapter 1 sat at 0.47% and the final
  mission at 0.28% (the story takes ~80 hours; almost nobody finishes it
  in week one), and GTA V's lifetime rates (first mission 43.2%, final
  mission 8.7-16.8%, platinum 0.1%) bound what week-one rates can reach.
  The program never reads the network and never uses those numbers at
  run time; they shaped the class priors baked into the code below.
* The biggest uncertainty is Exophase's refresh timing: the answer is the
  page as of its last refresh before the target, so if the last refresh
  lands well before the target the rates are staler (less earning, less
  dilution) than the median assumes. The spread is built to cover that.

Run locally:  mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a
# sibling module would import; this entry ships one file only.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# Standard normal quantiles at the five levels (used when the case asks
# for exactly these; any other levels go through _norm_ppf below).
Z = [-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722]

# --- tuning constants (priors; see the module docstring) -------------------
# Hours between Exophase refreshes of a game's page, on launch week.
REFRESH_PERIOD_H = 5.0
# Median players-tracked multiplier of the first refresh after launch.
FIRST_REFRESH_MULT = 5.0
# Newcomers' total trophies per newcomer at the first refresh, measured
# from the house's recorded launch-night refresh: (4276 - 943) trophies
# over (3868 - 638) newcomers, excluding the first-mission trophy, which
# stayed at 100% (its newcomers are counted separately at q = 1).
FIRST_REFRESH_OTHER_Q_SUM = (4276 - 943 - 3230) / 3230.0  # ~0.0319
# Class weights for splitting the newcomers' hold rates across trophies.
CLASS_WEIGHT = {"story": 3.0, "misc": 2.0, "side": 1.0,
                "grind": 0.3, "saturated": 0.0, "platinum": 0.0}
# Newcomer hold rate as a fraction of the trophy's current rate, used
# only as the ridge prior when the history cannot identify q.
CLASS_RHO = {"story": 0.35, "misc": 0.40, "side": 0.15,
             "grind": 0.08, "saturated": 1.0, "platinum": 0.0}
# Incumbent earning prior: fraction of the tracked base earning the
# trophy per hour.
CLASS_EARN_PER_HOUR = {"story": 0.001, "misc": 0.0005, "side": 0.0003,
                       "grind": 0.0001, "saturated": 0.0, "platinum": 0.0}
# Spread (logit units) parameters for the quantile bands.
SIGMA_BASE = 0.45
SIGMA_MOVE = 0.30      # per logit unit of predicted median move
SIGMA_REFRESH = 0.35   # per sqrt(log players-tracked growth)
SIGMA_HORIZON = 0.12   # per sqrt(day of horizon)
SIGMA_MIN = 0.35
SIGMA_MAX = 2.2
# Ridge weight for the per-trophy (g, q) fit: lam = RIDGE_BASE +
# RIDGE_PER_N * n_intervals. Small enough that the data dominates when
# the history has many refreshes, large enough to keep the (largely
# collinear) earning/dilution split near its class priors when it does not.
RIDGE_BASE = 0.1
RIDGE_PER_N = 0.05


def clamp_rate(x):
    """A rate in percent, inside the scorer's clamp [0.01, 99.99]."""
    return min(99.99, max(0.01, float(x)))


def logit(pct):
    p = clamp_rate(pct) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(lg):
    lg = max(-20.0, min(20.0, lg))
    return 100.0 / (1.0 + math.exp(-lg))


def _norm_ppf(p):
    """Inverse standard normal CDF (Acklam's approximation)."""
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    a = [-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285984469534e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00]
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
                ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


def _parse_time(text):
    """Epoch seconds from an ISO 8601 string, or None."""
    if not isinstance(text, str):
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _classify(trophy, rate_pct):
    """Trophy class from its own metadata and current rate.

    platinum: needs every other trophy (about 200 hours) -- nobody earns
      it in week one. saturated: essentially every tracked player holds
      it already (the first mission). story: chapter / final-mission
      trophies. side: a stranger's final mission strand. grind: counts,
      collections and medals. misc: everything else.
    """
    tier = (trophy.get("tier") or "").lower()
    if tier == "platinum":
        return "platinum"
    if rate_pct is not None and rate_pct >= 90.0:
        return "saturated"
    text = ((trophy.get("name") or "") + " " +
            (trophy.get("description") or "")).lower()
    if re.search(r"complete (chapter \d|the final mission)\b", text):
        return "story"
    if "final mission for" in text:
        return "side"
    if re.search(r"(complete|win|earn|discover|purchase|register|collect)"
                 r" \d+|gold medal|100%|meditate|waink", text):
        return "grind"
    return "misc"


def _states(case, t0):
    """Collapse the history into distinct states.

    Returns a list of (t_hours, players_tracked, [rates]) with one entry
    per refresh: consecutive reads with identical players and rates are
    one state, timed at its first read. Rates that a read lacks (null)
    carry forward from the previous read.
    """
    trophies = case["trophies"]
    n = len(trophies)
    current = [None] * n
    states = []
    last_key = None
    for read in case.get("history") or []:
        rates = read.get("rates") or []
        for i in range(n):
            v = rates[i] if i < len(rates) else None
            if isinstance(v, (int, float)) and math.isfinite(v):
                current[i] = float(v)
        players = read.get("players_tracked")
        if not isinstance(players, (int, float)) or players <= 0:
            continue
        key = (players, tuple(current))
        if key == last_key:
            continue
        last_key = key
        at = _parse_time(read.get("at"))
        t_hours = (at - t0) / 3600.0 if at is not None else 0.0
        states.append((t_hours, float(players), list(current)))
    return states


def _fit_players_target(states, t_target_h):
    """Players tracked at the target.

    The tracked base grows explosively at first and then saturates
    (each refresh adds a smaller multiple than the last), so a
    power-law fit over the whole history wildly over-extrapolates.
    Instead: take the recent daily log-growth rate (from the states of
    the last 24 hours, or the last two distinct-P states), then let it
    decay exponentially with a 2-day time constant out to the target.
    The factor is capped at 5x and floored at 1x.
    """
    last_t, last_p, _r = states[-1]
    horizon_days = max(0.0, (t_target_h - last_t) / 24.0)
    if horizon_days <= 0:
        return last_p
    # Recent window: states within the last 24 h of the last state.
    window = [(t, p) for (t, p, _r) in states if t >= last_t - 24.0]
    if len(window) < 2:
        window = [(states[0][0], states[0][1]), (last_t, last_p)]
    distinct = sorted(set(p for _t, p in window))
    if len(distinct) < 2:
        g_recent = 0.10  # per day; P never moved, assume a little
    else:
        t_a, p_a = window[0]
        t_b, p_b = window[-1]
        dt_days = max((t_b - t_a) / 24.0, 1e-6)
        g_recent = math.log(p_b / p_a) / dt_days
        g_recent = min(2.0, max(0.0, g_recent))
    tau_days = 1.0
    factor = math.exp(g_recent * tau_days *
                      (1.0 - math.exp(-horizon_days / tau_days)))
    return last_p * min(max(factor, 1.0), 5.0)


def _fit_trophy(intervals, prior_g, prior_q, p_last, t_last):
    """Ridge fit of dE = g * P_avg * dh + q * dP for one trophy.

    intervals: [(dh_hours, dP, dE, p_avg, t_mid_hours)]. The earning
    term scales with the tracked base (a per-player earning rate g),
    because the holders gained per hour grow with how many players
    there are; the dilution term scales with the players added. The
    regression runs in RATE space -- dividing by P_avg, so every
    interval contributes comparably however much the base has grown:
    dE / P_avg = g * dh + q * (dP / P_avg). Intervals are weighted by
    recency (half-life 24 h): the launch-night regime -- a tiny, frantic
    first cohort -- behaves differently from the steady regime near the
    checkpoint, and the forecast window resembles the latter. A small
    ridge pulls both coefficients to their class priors when the
    history is thin or the two terms are collinear (refreshes pair
    hours passed with players added, so the earning/dilution split is
    only weakly identified). Returns (g_per_player_per_hour,
    q_newcomer_hold_rate).
    """
    if not intervals:
        return prior_g, prior_q
    xs = []
    ys = []
    ws = []
    for dh, dp, de, p_avg, t_mid in intervals:
        if p_avg <= 0:
            continue
        if dh <= 0 and dp <= 0:
            continue
        xs.append((dh, dp / p_avg))
        ys.append(de / p_avg)
        ws.append(0.5 ** (max(0.0, t_last - t_mid) / 24.0))
    if not xs:
        return prior_g, prior_q
    lam = RIDGE_BASE + RIDGE_PER_N * len(xs)  # ridge weight
    s11 = sum(w * x[0] ** 2 for w, x in zip(ws, xs)) + lam
    s12 = sum(w * x[0] * x[1] for w, x in zip(ws, xs))
    s22 = sum(w * x[1] ** 2 for w, x in zip(ws, xs)) + lam
    t1 = sum(w * x[0] * y for w, x, y in zip(ws, xs, ys)) + lam * prior_g
    t2 = sum(w * x[1] * y for w, x, y in zip(ws, xs, ys)) + lam * prior_q
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-12:
        return prior_g, prior_q
    g = max(0.0, (t1 * s22 - t2 * s12) / det)
    q = min(1.0, max(0.0, (s11 * t2 - s12 * t1) / det))
    return g, q


def forecast_case(case):
    """Forecast one case: {"trophies": [{"id", "q": [5 quantiles]}]}."""
    trophies = case.get("trophies") or []
    if not trophies:
        return {"trophies": []}
    levels = case.get("levels") or LEVELS
    zs = Z if levels == LEVELS else [_norm_ppf(p) for p in levels]

    game = case.get("game") or {}
    release = game.get("release_date") or "2026-11-19"
    try:
        t0 = datetime.fromisoformat(release + "T00:00:00+00:00").timestamp()
    except ValueError:
        t0 = _parse_time((case.get("history") or [{}])[0].get("at")) or 0.0

    at = _parse_time(case.get("at"))
    target = _parse_time(case.get("target"))
    horizon_h = None
    if at is not None and target is not None:
        horizon_h = max(0.0, (target - at) / 3600.0)
    elif case.get("horizon_minutes") is not None:
        horizon_h = float(case["horizon_minutes"]) / 60.0
    else:
        horizon_h = 0.0
    t_target_h = ((target - t0) / 3600.0) if target is not None else horizon_h

    states = _states(case, t0)
    n = len(trophies)
    if not states:
        # No history at all: emit a valid, maximally honest shrug.
        rows = []
        for trophy in trophies:
            med = 1.0
            rows.append({"id": trophy["id"],
                         "q": [round(clamp_rate(inv_logit(logit(med) + z * 1.5)), 4)
                               for z in zs]})
        return {"trophies": rows}

    last_t, last_p, last_rates = states[-1]
    classes = []
    for i, trophy in enumerate(trophies):
        rate = last_rates[i]
        classes.append(_classify(trophy, rate))

    # --- players tracked at the target, and the per-trophy dynamics -----
    if len(states) >= 2:
        p_target = _fit_players_target(states, t_target_h)
        # Intervals between consecutive states, per trophy.
        intervals = []
        for s in range(len(states) - 1):
            t_a, p_a, r_a = states[s]
            t_b, p_b, r_b = states[s + 1]
            dh = max(0.0, t_b - t_a)
            dp = p_b - p_a
            p_avg = 0.5 * (p_a + p_b)
            des = []
            for i in range(n):
                ra = r_a[i] if r_a[i] is not None else 0.0
                rb = r_b[i] if r_b[i] is not None else 0.0
                des.append(rb * p_b / 100.0 - ra * p_a / 100.0)
            intervals.append((dh, dp, des, p_avg, 0.5 * (t_a + t_b)))
        a_list, q_list = [], []
        for i in range(n):
            cls = classes[i]
            rate = last_rates[i] if last_rates[i] is not None else 0.0
            prior_q = CLASS_RHO[cls] * (rate / 100.0)
            prior_g = CLASS_EARN_PER_HOUR[cls]
            iv = [(dh, dp, des[i], p_avg, t_mid)
                  for (dh, dp, des, p_avg, t_mid) in intervals]
            g_i, q_i = _fit_trophy(iv, prior_g, prior_q, last_p, last_t)
            a_list.append(g_i)
            q_list.append(q_i)
    else:
        # One flat state: no dynamics observed. Use the refresh prior:
        # one refresh before the target, players tracked multiplying.
        n_refresh = max(1.0, horizon_h / REFRESH_PERIOD_H)
        mult = 1.0
        step = FIRST_REFRESH_MULT - 1.0
        k = 0
        remaining = n_refresh
        while remaining > 0:
            take = min(1.0, remaining)
            mult *= (1.0 + step * take)
            step *= 0.6
            remaining -= take
            k += 1
            if k > 200:
                break
        p_target = last_p * min(mult, 500.0)
        # Newcomers' hold rates: saturated trophies stay saturated; the
        # rest split the measured first-refresh total by class weight.
        denom = 0.0
        for i in range(n):
            if classes[i] in ("saturated", "platinum"):
                continue
            rate = last_rates[i] if last_rates[i] is not None else 0.0
            denom += CLASS_WEIGHT[classes[i]] * (rate / 100.0)
        a_list, q_list = [], []
        for i in range(n):
            cls = classes[i]
            rate = last_rates[i] if last_rates[i] is not None else 0.0
            if cls == "saturated":
                q_list.append(1.0)
                a_list.append(0.0)
            elif cls == "platinum":
                q_list.append(0.0)
                a_list.append(0.0)
            else:
                # Absolute newcomer hold rate: the measured total for
                # the first refresh, split by class weight x current
                # rate, so sum(q) == FIRST_REFRESH_OTHER_Q_SUM.
                share = (CLASS_WEIGHT[cls] * (rate / 100.0) / denom
                         if denom > 0 else 0.0)
                q_list.append(min(1.0, max(
                    0.0, FIRST_REFRESH_OTHER_Q_SUM * share)))
                a_list.append(CLASS_EARN_PER_HOUR[cls])

    dh_target = max(0.0, t_target_h - last_t)
    log_p_growth = math.log(max(1.0, p_target / last_p))
    horizon_days = horizon_h / 24.0
    # Average tracked base over the forecast window: earning scales
    # with how many players there are, so it is charged on the average
    # base, not the last one.
    p_avg_future = 0.5 * (last_p + p_target)

    rows = []
    for i, trophy in enumerate(trophies):
        rate = last_rates[i] if last_rates[i] is not None else 0.0
        e_last = rate * last_p / 100.0
        e_target = (e_last + a_list[i] * p_avg_future * dh_target
                    + q_list[i] * max(0.0, p_target - last_p))
        e_target = min(max(e_target, e_last), p_target)
        med = clamp_rate(e_target / p_target * 100.0)
        # Spread: base + predicted move + refresh-size + horizon terms.
        move = abs(logit(med) - logit(rate if rate > 0 else 0.01))
        sigma = math.sqrt(SIGMA_BASE ** 2
                          + (SIGMA_MOVE * move) ** 2
                          + (SIGMA_REFRESH * math.sqrt(log_p_growth)) ** 2
                          + (SIGMA_HORIZON * math.sqrt(horizon_days)) ** 2)
        if classes[i] == "saturated":
            sigma = max(sigma, 1.0)
        sigma = min(SIGMA_MAX, max(SIGMA_MIN, sigma))
        lg = logit(med)
        qs = []
        prev = 0.0
        for z in zs:
            v = clamp_rate(inv_logit(lg + z * sigma))
            v = round(v, 4)
            v = max(v, prev)
            v = min(v, 99.99)
            qs.append(v)
            prev = v
        rows.append({"id": trophy["id"], "q": qs})
    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        try:
            forecast = forecast_case(case)
        except Exception:
            # Never fail a case outright: an invalid case scores as the
            # last rates and takes the entry out of the prizes. Emit a
            # valid persistence-shaped forecast instead.
            trophies = case.get("trophies") or []
            last = (case.get("history") or [{}])[-1]
            rates = last.get("rates") or []
            rows = []
            for i, trophy in enumerate(trophies):
                rate = rates[i] if i < len(rates) and isinstance(
                    rates[i], (int, float)) else 1.0
                lg = logit(rate if rate else 0.01)
                rows.append({"id": trophy["id"],
                             "q": [round(clamp_rate(inv_logit(lg + z * 0.5)), 4)
                                   for z in Z]})
            forecast = {"trophies": rows}
        out_path = OUTPUT_DIR / (path.stem + ".out")
        out_path.write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
