import argparse
import os
import re
import json
import math
import pandas as pd
import numpy as np
from itertools import product
from scipy.stats import spearmanr
import hashlib

# ---------------------------
# Helpers (same logic as app)
# ---------------------------
def safe_parse_json_like(val):
    if pd.isna(val):
        return None
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str) and (val.strip().startswith('[') or val.strip().startswith('{')):
        try:
            return json.loads(val)
        except Exception:
            return None
    return None

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2*R*math.atan2(math.sqrt(a), math.sqrt(1-a))

def load_data(csv_path):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    df = pd.read_csv(csv_path)

    # parse list-like columns
    for col in ['food_type_tags', 'priority_tags', 'all_keywords_for_recommendation', 'opening_hours']:
        if col in df.columns:
            df[col] = df[col].apply(safe_parse_json_like)

    # numeric columns
    for col in ['avg_rating', 'total_ratings', 'avg_sentiment_compound', 'latitude', 'longitude']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    if 'avg_sentiment_compound' in df.columns:
        df['avg_sentiment_compound'] = df['avg_sentiment_compound'].fillna(0.0)

    return df

def compute_scores(df,
                   M_bayes=10,
                   sentiment_w=0.2,
                   kw_bonus_per_hit=0.03,
                   kw_bonus_cap=0.15,
                   keywords=None,
                   kw_hits=None,
                   kw_hits_mode="constant"):
    """
    Return df with columns:
      base_bayesian, sentiment_bonus, tag_bonus, final_score
    """
    tdf = df.copy()

    # 1) Bayesian average on avg_rating with M_bayes
    C = tdf['avg_rating'].mean()
    tdf['base_bayesian'] = tdf.apply(
        lambda x: ((x['total_ratings'] / (x['total_ratings'] + M_bayes)) * x['avg_rating'])
                  + ((M_bayes / (x['total_ratings'] + M_bayes)) * C),
        axis=1
    )

    # 2) sentiment
    if 'avg_sentiment_compound' in tdf.columns:
        tdf['sentiment_bonus'] = sentiment_w * tdf['avg_sentiment_compound']
    else:
        tdf['sentiment_bonus'] = 0.0

    # 3) keyword/tag bonus
    keywords = [k.strip() for k in (keywords or []) if k.strip()]
    kw_pattern_list = [re.compile(re.escape(k), re.IGNORECASE) for k in keywords] if keywords else []

    def calc_tag_bonus(row):
        if kw_hits is not None:
            if kw_hits_mode == "constant":
                hits = kw_hits
            elif kw_hits_mode == "hash":
                key = row.get('place_id') or row.get('restaurant_name') or str(row.name)
                h = hashlib.md5(str(key).encode("utf-8")).hexdigest()
                hits = int(h, 16) % (kw_hits + 1)
            else:
                hits = kw_hits
            return min(hits * kw_bonus_per_hit, kw_bonus_cap)

        if not kw_pattern_list:
            return 0.0
        tags = row.get('all_keywords_for_recommendation')
        if not isinstance(tags, list):
            return 0.0
        hits = 0
        for kwp in kw_pattern_list:
            if any(kwp.search(str(t)) for t in tags):
                hits += 1
        return min(hits * kw_bonus_per_hit, kw_bonus_cap)

    tdf['tag_bonus'] = tdf.apply(calc_tag_bonus, axis=1)

    # final score = bayesian + sentiment + tag bonuses
    tdf['final_score'] = tdf['base_bayesian'] + tdf['sentiment_bonus'] + tdf['tag_bonus']
    return tdf

def distance_filter(df, lat=None, lng=None, radius_m=None):
    if lat is None or lng is None or radius_m is None:
        return df
    t = df.dropna(subset=['latitude', 'longitude']).copy()
    t['distance_m'] = t.apply(lambda r: haversine_m(lat, lng, r['latitude'], r['longitude']), axis=1)
    return t.loc[t['distance_m'] <= radius_m].copy()

# ---------------------------
# Main experiment runner
# ---------------------------
def run_experiments(args):
    df = load_data(args.input)

    # Optional prefilter: min rating/reviews
    if args.min_rating is not None:
        df = df.loc[df['avg_rating'] >= args.min_rating]
    if args.min_reviews is not None:
        df = df.loc[df['total_ratings'] >= args.min_reviews]

    # Optional distance filter
    df = distance_filter(df, args.lat, args.lng, args.radius)

    # Prepare grid
    M_list = [int(x) for x in args.M_list.split(',')]
    S_list = [float(x) for x in args.S_list.split(',')]
    B_list = [float(x) for x in args.kw_bonus_list.split(',')]
    Cap_list = [float(x) for x in args.kw_cap_list.split(',')]
    keywords = [k.strip() for k in args.keywords.split(',')] if args.keywords else []
    H_list = [int(x) for x in args.kw_hits_list.split(',')] if args.kw_hits_list else [None]

    os.makedirs(args.outdir, exist_ok=True)

    # Baseline: first value in each list
    baseline_cfg = (M_list[0], S_list[0], B_list[0], Cap_list[0])
    cfg_rows = []
    rank_maps = {}  # cfg -> Series(index=place_id or name, rank)

    for M, S, B, C, H in product(M_list, S_list, B_list, Cap_list, H_list):
        cfg_name = f"M{M}_S{S}_B{B}_Cap{C}" + (f"_H{H}" if H is not None else "")
        scored = compute_scores(
            df,
            M_bayes=M,
            sentiment_w=S,
            kw_bonus_per_hit=B,
            kw_bonus_cap=C,
            keywords=keywords,
            kw_hits=H,
            kw_hits_mode=args.kw_hits_mode
        ).sort_values(['final_score', 'total_ratings'], ascending=[False, False])

        # Select key columns for inspection
        cols = [
            'place_id' if 'place_id' in scored.columns else None,
            'restaurant_name' if 'restaurant_name' in scored.columns else None,
            'avg_rating', 'total_ratings',
            'avg_sentiment_compound',
            'base_bayesian', 'sentiment_bonus', 'tag_bonus', 'final_score'
        ]
        cols = [c for c in cols if c is not None and c in scored.columns]
        out_path = os.path.join(args.outdir, f"scored_{cfg_name}.csv")
        scored[cols].to_csv(out_path, index=False)

        # Save top-N list for quick view
        topN = scored.head(args.topn)[cols]
        topN.to_csv(os.path.join(args.outdir, f"top{args.topn}_{cfg_name}.csv"), index=False)

        # Keep rank map for correlation/overlap
        key = 'place_id' if 'place_id' in scored.columns else 'restaurant_name'
        rk = pd.Series(range(1, len(scored) + 1), index=scored[key].values)
        rank_maps[cfg_name] = rk

        cfg_rows.append({
            'config': cfg_name,
            'M_bayes': M,
            'sentiment_w': S,
            'kw_bonus_per_hit': B,
            'kw_bonus_cap': C,
            'n_items': len(scored)
        })

    # Summary table of configurations
    pd.DataFrame(cfg_rows).to_csv(os.path.join(args.outdir, "configs_summary.csv"), index=False)

    # Compare each config to baseline (overlap@N, Spearman corr on common keys)
    base_key = list(rank_maps.keys())[0]  # first iter = baseline
    base_rk = rank_maps[base_key]
    compare_rows = []
    for cfg, rk in rank_maps.items():
        # overlap@N
        top_base = set(base_rk.nsmallest(args.topn).index)
        top_curr = set(rk.nsmallest(args.topn).index)
        overlap = len(top_base & top_curr) / max(1, len(top_base))
        # spearman on intersection
        common = list(set(base_rk.index) & set(rk.index))
        sp = np.nan
        if len(common) >= 5:
            s1 = base_rk.loc[common].values
            s2 = rk.loc[common].values
            sp = spearmanr(s1, s2).correlation
        compare_rows.append({
            'config': cfg,
            'baseline': base_key,
            'overlap_at_topN': round(overlap, 3),
            'spearman': round(sp, 3) if not np.isnan(sp) else ''
        })
    pd.DataFrame(compare_rows).to_csv(os.path.join(args.outdir, "ranking_comparison_vs_baseline.csv"), index=False)

    print(f"✅ Done. Files saved under: {args.outdir}")
    print("- configs_summary.csv")
    print("- ranking_comparison_vs_baseline.csv")
    print("- scored_*.csv and top{N}_*.csv for each configuration")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Offline experiments for Bayesian & sentiment & keyword weights.")
    p.add_argument("--input", required=True, help="Processed CSV (the one your app loads).")
    p.add_argument("--outdir", default="exp_outputs", help="Directory to save results.")
    p.add_argument("--M_list", default="10,25,50", help="Comma-separated M for Bayesian (e.g., 10,25,50)")
    p.add_argument("--S_list", default="0.0,0.2,0.5", help="Comma-separated sentiment weights")
    p.add_argument("--kw_bonus_list", default="0.03,0.05", help="Comma-separated bonus per keyword match")
    p.add_argument("--kw_cap_list", default="0.15,0.2", help="Comma-separated cap for keyword bonus")
    p.add_argument("--kw_hits_list", default="",
                   help="Comma-separated assumed keyword hits per restaurant (e.g., 1,2,3,4,5). If empty, use real keyword matching.")
    p.add_argument("--kw_hits_mode", choices=["constant", "hash"], default="constant",
                   help="How to generate synthetic hits when kw_hits_list is used.")
    p.add_argument("--keywords", default="", help="Comma-separated keywords to match (e.g., chinese,relaxing)")
    p.add_argument("--min_rating", type=float, default=None, help="Optional prefilter on avg_rating")
    p.add_argument("--min_reviews", type=int, default=None, help="Optional prefilter on total_ratings")
    p.add_argument("--lat", type=float, default=None, help="Optional user latitude for distance filter")
    p.add_argument("--lng", type=float, default=None, help="Optional user longitude for distance filter")
    p.add_argument("--radius", type=float, default=None, help="Optional radius in meters for distance filter")
    p.add_argument("--topn", type=int, default=10, help="Top-N to export for each config & for overlap")
    args = p.parse_args()
    run_experiments(args)
