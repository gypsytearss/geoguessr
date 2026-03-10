#!/usr/bin/env python3
"""Generate a GeoGuessr performance dashboard as a self-contained HTML file."""

import json
import math
import os
import sys
from collections import defaultdict

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_rounds(folder: str) -> list:
    path = os.path.join(folder, "games.json")
    games = json.load(open(path))
    rounds = []
    for g in games:
        for r in g["rounds"]:
            r["_game_id"] = g["game_id"]
            r["_date"] = g["date"]
            r["_opponent"] = g["opponent"]["nick"]
            rounds.append(r)
    return rounds


# ---------------------------------------------------------------------------
# Country metadata
# ---------------------------------------------------------------------------

COUNTRY_NAMES = {
    "ad": "Andorra", "ae": "UAE", "af": "Afghanistan", "ag": "Antigua",
    "al": "Albania", "am": "Armenia", "ao": "Angola", "ar": "Argentina",
    "at": "Austria", "au": "Australia", "az": "Azerbaijan", "ba": "Bosnia",
    "bb": "Barbados", "bd": "Bangladesh", "be": "Belgium", "bf": "Burkina Faso",
    "bg": "Bulgaria", "bh": "Bahrain", "bi": "Burundi", "bj": "Benin",
    "bn": "Brunei", "bo": "Bolivia", "br": "Brazil", "bs": "Bahamas",
    "bt": "Bhutan", "bw": "Botswana", "by": "Belarus", "bz": "Belize",
    "ca": "Canada", "cd": "DR Congo", "cf": "C. African Rep.", "cg": "Congo",
    "ch": "Switzerland", "ci": "Ivory Coast", "cl": "Chile", "cm": "Cameroon",
    "cn": "China", "co": "Colombia", "cr": "Costa Rica", "cu": "Cuba",
    "cv": "Cape Verde", "cy": "Cyprus", "cz": "Czechia", "de": "Germany",
    "dj": "Djibouti", "dk": "Denmark", "dm": "Dominica", "do": "Dominican Rep.",
    "dz": "Algeria", "ec": "Ecuador", "ee": "Estonia", "eg": "Egypt",
    "er": "Eritrea", "es": "Spain", "et": "Ethiopia", "fi": "Finland",
    "fj": "Fiji", "fr": "France", "ga": "Gabon", "gb": "UK",
    "gd": "Grenada", "ge": "Georgia", "gh": "Ghana", "gm": "Gambia",
    "gn": "Guinea", "gq": "Eq. Guinea", "gr": "Greece", "gt": "Guatemala",
    "gw": "Guinea-Bissau", "gy": "Guyana", "hn": "Honduras", "hr": "Croatia",
    "ht": "Haiti", "hu": "Hungary", "id": "Indonesia", "ie": "Ireland",
    "il": "Israel", "in": "India", "iq": "Iraq", "ir": "Iran",
    "is": "Iceland", "it": "Italy", "jm": "Jamaica", "jo": "Jordan",
    "jp": "Japan", "ke": "Kenya", "kg": "Kyrgyzstan", "kh": "Cambodia",
    "ki": "Kiribati", "km": "Comoros", "kn": "St Kitts", "kp": "North Korea",
    "kr": "South Korea", "kw": "Kuwait", "kz": "Kazakhstan", "la": "Laos",
    "lb": "Lebanon", "lc": "St Lucia", "li": "Liechtenstein", "lk": "Sri Lanka",
    "lr": "Liberia", "ls": "Lesotho", "lt": "Lithuania", "lu": "Luxembourg",
    "lv": "Latvia", "ly": "Libya", "ma": "Morocco", "mc": "Monaco",
    "md": "Moldova", "me": "Montenegro", "mg": "Madagascar", "mh": "Marshall Is.",
    "mk": "N. Macedonia", "ml": "Mali", "mm": "Myanmar", "mn": "Mongolia",
    "mr": "Mauritania", "mt": "Malta", "mu": "Mauritius", "mv": "Maldives",
    "mw": "Malawi", "mx": "Mexico", "my": "Malaysia", "mz": "Mozambique",
    "na": "Namibia", "ne": "Niger", "ng": "Nigeria", "ni": "Nicaragua",
    "nl": "Netherlands", "no": "Norway", "np": "Nepal", "nr": "Nauru",
    "nz": "New Zealand", "om": "Oman", "pa": "Panama", "pe": "Peru",
    "pg": "Papua NG", "ph": "Philippines", "pk": "Pakistan", "pl": "Poland",
    "pt": "Portugal", "pw": "Palau", "py": "Paraguay", "qa": "Qatar",
    "ro": "Romania", "rs": "Serbia", "ru": "Russia", "rw": "Rwanda",
    "sa": "Saudi Arabia", "sb": "Solomon Is.", "sc": "Seychelles", "sd": "Sudan",
    "se": "Sweden", "sg": "Singapore", "si": "Slovenia", "sk": "Slovakia",
    "sl": "Sierra Leone", "sm": "San Marino", "sn": "Senegal", "so": "Somalia",
    "sr": "Suriname", "ss": "South Sudan", "st": "São Tomé", "sv": "El Salvador",
    "sy": "Syria", "sz": "Eswatini", "td": "Chad", "tg": "Togo",
    "th": "Thailand", "tj": "Tajikistan", "tl": "Timor-Leste", "tm": "Turkmenistan",
    "tn": "Tunisia", "to": "Tonga", "tr": "Turkey", "tt": "Trinidad",
    "tv": "Tuvalu", "tz": "Tanzania", "ua": "Ukraine", "ug": "Uganda",
    "us": "USA", "uy": "Uruguay", "uz": "Uzbekistan", "va": "Vatican",
    "vc": "St Vincent", "ve": "Venezuela", "vn": "Vietnam", "vu": "Vanuatu",
    "ws": "Samoa", "xk": "Kosovo", "ye": "Yemen", "za": "South Africa",
    "zm": "Zambia", "zw": "Zimbabwe",
}

# Country areas in km² — used to compute effective radius for region accuracy
COUNTRY_AREA_KM2 = {
    "ad": 468, "ae": 83600, "af": 652230, "al": 28748, "am": 29743,
    "ao": 1246700, "ar": 2780400, "at": 83871, "au": 7692024, "az": 86600,
    "ba": 51197, "bd": 147570, "be": 30528, "bf": 274200, "bg": 110879,
    "bh": 760, "bi": 27830, "bj": 112622, "bn": 5765, "bo": 1098581,
    "br": 8515767, "bt": 38394, "bw": 581730, "by": 207600, "bz": 22966,
    "ca": 9984670, "cd": 2344858, "cf": 622984, "cg": 342000, "ch": 41285,
    "ci": 322463, "cl": 756102, "cm": 475442, "cn": 9596960, "co": 1141748,
    "cr": 51100, "cu": 109884, "cy": 9251, "cz": 78867, "de": 357114,
    "dj": 23200, "dk": 43094, "do": 48671, "dz": 2381741, "ec": 283561,
    "ee": 45228, "eg": 1002450, "er": 117600, "es": 505990, "et": 1104300,
    "fi": 338145, "fj": 18274, "fr": 551695, "ga": 267668, "gb": 243610,
    "ge": 69700, "gh": 238533, "gm": 11295, "gn": 245857, "gq": 28051,
    "gr": 131957, "gt": 108889, "gy": 214969, "hn": 112492, "hr": 56594,
    "ht": 27750, "hu": 93028, "id": 1904569, "ie": 70273, "il": 20770,
    "in": 3287263, "iq": 438317, "ir": 1648195, "is": 103000, "it": 301340,
    "jm": 10991, "jo": 89342, "jp": 377975, "ke": 580367, "kg": 199951,
    "kh": 181035, "kp": 120538, "kr": 100210, "kw": 17818, "kz": 2724900,
    "la": 236800, "lb": 10452, "li": 160, "lk": 65610, "lr": 111369,
    "ls": 30355, "lt": 65300, "lu": 2586, "lv": 64589, "ly": 1759541,
    "ma": 446550, "md": 33846, "me": 13812, "mg": 587041, "mk": 25713,
    "ml": 1240192, "mm": 676578, "mn": 1564116, "mr": 1030700, "mt": 316,
    "mu": 2040, "mv": 298, "mw": 118484, "mx": 1964375, "my": 329847,
    "mz": 801590, "na": 824292, "ne": 1267000, "ng": 923768, "ni": 130373,
    "nl": 41543, "no": 323802, "np": 147181, "nz": 270467, "om": 309500,
    "pa": 75417, "pe": 1285216, "pg": 462840, "ph": 300000, "pk": 881913,
    "pl": 312696, "pt": 92212, "py": 406752, "qa": 11586, "ro": 238397,
    "rs": 77474, "ru": 17098242, "rw": 26338, "sa": 2149690, "sb": 28896,
    "sd": 1886068, "se": 450295, "sg": 728, "si": 20273, "sk": 49035,
    "sl": 71740, "sn": 196722, "so": 637657, "sr": 163820, "ss": 619745,
    "sv": 21041, "sy": 185180, "sz": 17364, "td": 1284000, "tg": 56785,
    "th": 513120, "tj": 143100, "tl": 14874, "tm": 488100, "tn": 163610,
    "to": 747, "tr": 783562, "tt": 5130, "tz": 945087, "ua": 603550,
    "ug": 241038, "us": 9372610, "uy": 176215, "uz": 447400, "ve": 916445,
    "vn": 331212, "ws": 2842, "xk": 10887, "ye": 527968, "za": 1221037,
    "zm": 752612, "zw": 390757,
}


def effective_radius_km(cc: str) -> float:
    """Effective radius of a country: sqrt(area / pi)."""
    area = COUNTRY_AREA_KM2.get(cc.lower(), 500000)
    return math.sqrt(area / math.pi)


def name(cc: str) -> str:
    return COUNTRY_NAMES.get(cc.lower(), cc.upper()) if cc else "Unknown"


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------

def country_stats(rounds: list) -> dict:
    """Per-country avg score for me and opponent."""
    my_data = defaultdict(list)
    opp_data = defaultdict(list)
    for r in rounds:
        cc = r["actual"]["country_code"]
        my_score = r["my_guess"]["score"]
        opp_score = r["opponent_guess"]["score"]
        if cc:
            if my_score is not None:
                my_data[cc].append(my_score)
            if opp_score is not None:
                opp_data[cc].append(opp_score)
    result = {}
    all_ccs = set(my_data) | set(opp_data)
    for cc in all_ccs:
        ms = my_data[cc]
        os_ = opp_data[cc]
        result[cc] = {
            "my_scores": ms,
            "my_avg": sum(ms) / len(ms) if ms else 0,
            "my_count": len(ms),
            "opp_avg": sum(os_) / len(os_) if os_ else 0,
            "opp_count": len(os_),
        }
    return result


def confusion_matrix_data(rounds: list):
    """Row-normalized confusion matrix using same labels on both axes."""
    pairs = defaultdict(int)
    all_countries = set()
    for r in rounds:
        actual = r["actual"]["country_code"]
        guessed = r["my_guess"]["country_code"]
        if actual and guessed:
            pairs[(actual, guessed)] += 1
            all_countries.add(actual)
            all_countries.add(guessed)

    labels = sorted(all_countries)
    idx = {cc: i for i, cc in enumerate(labels)}
    n = len(labels)

    counts = [[0] * n for _ in range(n)]
    row_totals = defaultdict(int)
    for (actual, guessed), count in pairs.items():
        row_totals[actual] += count

    normalized = [[0.0] * n for _ in range(n)]
    for (actual, guessed), count in pairs.items():
        i, j = idx[actual], idx[guessed]
        counts[i][j] = count
        normalized[i][j] = count / row_totals[actual]

    return labels, normalized, counts


def score_distribution(rounds: list) -> list:
    return [r["my_guess"]["score"] for r in rounds if r["my_guess"]["score"] is not None]


def region_accuracy(rounds: list) -> list:
    """
    For rounds where I guessed the correct country, compute normalized distance:
    distance_km / effective_radius_km(country).
    Returns list of (country_code, normalized_distance) sorted by avg normalized distance.
    """
    data = defaultdict(list)
    for r in rounds:
        actual_cc = r["actual"]["country_code"]
        my_cc = r["my_guess"]["country_code"]
        dist_m = r["my_guess"]["distance_m"]
        if actual_cc and my_cc == actual_cc and dist_m is not None:
            radius_km = effective_radius_km(actual_cc)
            normalized = (dist_m / 1000) / radius_km
            data[actual_cc].append(normalized)

    result = []
    for cc, vals in data.items():
        result.append((cc, sum(vals) / len(vals), len(vals)))
    result.sort(key=lambda x: x[1])
    return result


# ---------------------------------------------------------------------------
# Build dashboard
# ---------------------------------------------------------------------------

def build_dashboard(rounds: list) -> go.Figure:
    stats = country_stats(rounds)
    labels, matrix, counts = confusion_matrix_data(rounds)
    all_scores = score_distribution(rounds)
    region_acc = region_accuracy(rounds)

    fig = make_subplots(
        rows=4, cols=2,
        subplot_titles=(
            "Best Countries (avg score, min 2 rounds)",
            "Worst Countries (avg score, min 2 rounds)",
            "Me vs Opponent — Avg Score by Country",
            "Score Distribution",
            "Country Confusion Matrix (row-normalized)",
            "Region Accuracy — correct country guesses<br><sup>normalized distance / country radius (lower = better)</sup>",
            "Stats Summary", "",
        ),
        specs=[
            [{"type": "bar"}, {"type": "bar"}],
            [{"type": "bar"}, {"type": "histogram"}],
            [{"type": "heatmap"}, {"type": "bar"}],
            [{"type": "table", "colspan": 2}, None],
        ],
        vertical_spacing=0.1,
        horizontal_spacing=0.1,
        row_heights=[0.2, 0.2, 0.35, 0.15],
    )

    # --- 1. Best countries ---
    qualified = [(cc, s) for cc, s in stats.items() if s["my_count"] >= 2]
    best = sorted(qualified, key=lambda x: x[1]["my_avg"], reverse=True)[:10]
    fig.add_trace(go.Bar(
        x=[name(cc) for cc, _ in best],
        y=[round(s["my_avg"]) for _, s in best],
        marker_color="#2ecc71",
        text=[f"{round(s['my_avg'])}" for _, s in best],
        textposition="outside",
        showlegend=False,
    ), row=1, col=1)

    # --- 2. Worst countries ---
    worst = sorted(qualified, key=lambda x: x[1]["my_avg"])[:10]
    fig.add_trace(go.Bar(
        x=[name(cc) for cc, _ in worst],
        y=[round(s["my_avg"]) for _, s in worst],
        marker_color="#e74c3c",
        text=[f"{round(s['my_avg'])}" for _, s in worst],
        textposition="outside",
        showlegend=False,
    ), row=1, col=2)

    # --- 3. Me vs Opponent avg by country (all countries, sorted by my avg) ---
    all_sorted = sorted(stats.items(), key=lambda x: x[1]["my_avg"], reverse=True)
    ccs = [cc for cc, _ in all_sorted]
    fig.add_trace(go.Bar(
        name="Me", x=[name(cc) for cc in ccs],
        y=[round(stats[cc]["my_avg"]) for cc in ccs],
        marker_color="#3498db", offsetgroup=0,
        customdata=[stats[cc]["my_count"] for cc in ccs],
        hovertemplate="<b>%{x}</b><br>My avg: %{y}<br>Rounds: %{customdata}<extra></extra>",
    ), row=2, col=1)
    fig.add_trace(go.Bar(
        name="Opponent", x=[name(cc) for cc in ccs],
        y=[round(stats[cc]["opp_avg"]) for cc in ccs],
        marker_color="#e67e22", offsetgroup=1,
        customdata=[stats[cc]["opp_count"] for cc in ccs],
        hovertemplate="<b>%{x}</b><br>Opp avg: %{y}<br>Rounds: %{customdata}<extra></extra>",
    ), row=2, col=1)

    # --- 4. Score distribution ---
    mean_score = sum(all_scores) / len(all_scores)
    fig.add_trace(go.Histogram(
        x=all_scores, nbinsx=20,
        marker_color="#3498db",
        showlegend=False,
    ), row=2, col=2)

    # --- 5. Confusion matrix (row-normalized) ---
    label_names = [name(cc) for cc in labels]
    fig.add_trace(go.Heatmap(
        z=matrix,
        x=label_names,
        y=label_names,
        colorscale="Reds",
        zmin=0, zmax=1,
        showscale=True,
        customdata=counts,
        hovertemplate="Actual: %{y}<br>Guessed: %{x}<br>Rate: %{z:.0%}<br>Rounds: %{customdata}<extra></extra>",
        showlegend=False,
    ), row=3, col=1)

    # --- 6. Region accuracy bar chart ---
    if region_acc:
        ra_ccs = [cc for cc, _, _ in region_acc]
        ra_vals = [v for _, v, _ in region_acc]
        ra_counts = [c for _, _, c in region_acc]
        colors = ["#2ecc71" if v < 0.5 else "#f39c12" if v < 1.0 else "#e74c3c"
                  for v in ra_vals]
        fig.add_trace(go.Bar(
            x=[name(cc) for cc in ra_ccs],
            y=ra_vals,
            marker_color=colors,
            text=[f"n={c}" for c in ra_counts],
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Norm. distance: %{y:.2f}x radius<br>%{text}<extra></extra>",
            showlegend=False,
        ), row=3, col=2)
        # Reference line at 1.0 (= one country radius off)
        fig.add_shape(
            type="line", x0=-0.5, x1=len(ra_ccs) - 0.5, y0=1, y1=1,
            xref="x6", yref="y6",
            line=dict(dash="dash", color="#7f8c8d", width=1.5),
        )
        fig.add_annotation(
            x=len(ra_ccs) - 1, y=1.05, xref="x6", yref="y6",
            text="1× radius", showarrow=False,
            font=dict(color="#7f8c8d", size=10), xanchor="right",
        )

    # --- 7. Stats summary table ---
    sorted_scores = sorted(all_scores)
    n = len(sorted_scores)
    median = sorted_scores[n // 2]
    wins = sum(
        1 for r in rounds
        if r["my_guess"]["score"] is not None
        and r["opponent_guess"]["score"] is not None
        and r["my_guess"]["score"] > r["opponent_guess"]["score"]
    )
    total_with_opp = sum(
        1 for r in rounds
        if r["my_guess"]["score"] is not None and r["opponent_guess"]["score"] is not None
    )
    correct_country = sum(
        1 for r in rounds
        if r["actual"]["country_code"] and r["my_guess"]["country_code"]
        and r["actual"]["country_code"] == r["my_guess"]["country_code"]
    )

    fig.add_trace(go.Table(
        header=dict(
            values=["Metric", "Value", "Metric", "Value"],
            fill_color="#2c3e50",
            font=dict(color="white", size=12),
            align="left",
        ),
        cells=dict(
            values=[
                ["Rounds played", "Avg score", "Median score", "Max score"],
                [n, f"{mean_score:.0f}", median, max(all_scores)],
                ["Min score", "Rounds won vs opp", "Correct country %", "Countries faced"],
                [min(all_scores), f"{wins}/{total_with_opp} ({100*wins//total_with_opp}%)",
                 f"{100*correct_country//n}%", len(stats)],
            ],
            fill_color="#ecf0f1",
            align="left",
            font=dict(size=12),
        ),
    ), row=4, col=1)

    # --- Layout ---
    fig.update_layout(
        title=dict(text="GeoGuessr Performance Dashboard", font=dict(size=24), x=0.5),
        height=1800,
        paper_bgcolor="#f8f9fa",
        plot_bgcolor="#f8f9fa",
        font=dict(family="Arial, sans-serif"),
        barmode="group",
        legend=dict(orientation="h", y=0.58, x=0.5, xanchor="center"),
    )

    for row, col in [(1, 1), (1, 2), (2, 1), (3, 2)]:
        fig.update_xaxes(tickangle=-35, row=row, col=col)
    fig.update_xaxes(tickangle=-50, row=3, col=1)
    fig.update_yaxes(tickangle=-45, row=3, col=1)
    fig.update_xaxes(title_text="Score", row=2, col=2)
    fig.update_yaxes(title_text="Rounds", row=2, col=2)
    fig.update_yaxes(title_text="Avg Score", row=2, col=1)
    fig.update_yaxes(title_text="Norm. distance (× radius)", row=3, col=2)

    # Mean line on histogram
    fig.add_shape(
        type="line", x0=mean_score, x1=mean_score, y0=0, y1=1,
        yref="y4 domain", xref="x4",
        line=dict(dash="dash", color="#e67e22", width=2),
    )
    fig.add_annotation(
        x=mean_score, y=0.9, xref="x4", yref="y4 domain",
        text=f"avg {mean_score:.0f}", showarrow=False,
        font=dict(color="#e67e22"), xanchor="left",
    )

    return fig


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    rounds = load_rounds(folder)
    print(f"Loaded {len(rounds)} rounds from {folder}/games.json")

    fig = build_dashboard(rounds)

    output = os.path.join(folder, "dashboard.html")
    pio.write_html(fig, output, include_plotlyjs="cdn", full_html=True)
    print(f"Dashboard written to {output} — open in your browser")


if __name__ == "__main__":
    main()
