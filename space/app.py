"""Hugging Face Space: shows the latest picks and the expectation-vs-reality scorecard.

Reads reports/latest.json from the GitHub repo (written nightly by GitHub Actions).
Set DATA_URL in the Space settings if your repo name differs.
"""
import os

import gradio as gr
import pandas as pd
import requests

DATA_URL = os.getenv(
    "DATA_URL",
    "https://raw.githubusercontent.com/NANDAN-CREATOR/nse-llm-picker/main/reports/latest.json",
)
NOTE = "_Experiment, not investment advice. Past patterns and headlines do not guarantee a next-day move._"


def load():
    r = requests.get(DATA_URL, timeout=20, headers={"Cache-Control": "no-cache"})
    r.raise_for_status()
    return r.json()


def pct(x, nd=2):
    return "-" if x is None else f"{x:+.{nd}f}%"


def render():
    try:
        d = load()
    except Exception as e:
        msg = f"Could not load data from `{DATA_URL}`: {e}"
        return msg, pd.DataFrame(), "", pd.DataFrame(), pd.DataFrame()

    if not d.get("picks"):
        return "No picks yet. The first nightly run will create them.", pd.DataFrame(), "", pd.DataFrame(), pd.DataFrame()

    p = d["picks"]
    head = (f"## Picks for session {d['target_date']}\n"
            f"Based on closing data of {d.get('asof_date')} · generated {d['generated_at'][:16].replace('T', ' ')} IST\n\n{NOTE}")

    table = pd.DataFrame([{
        "#": x["rank"], "Symbol": x["symbol"], "Company": x["name"], "Ref close": x["ref_close"],
        "Expected": pct(x["exp_ret_pct"]), "Target": x["target_price"], "Stop": x["stop_price"],
        "P(up) prior": f"{x['p_up']:.0%}", "Pattern": f"{x['quant_score']:+.2f}",
        "News": f"{x['news_score']:+.2f}", "Combined": f"{x['combined']:+.2f}",
        "Catalyst": x["catalyst"],
    } for x in p])

    top = p[0]
    heads = "\n".join(f"- {h['title']}" for h in top.get("headlines", [])) or "- none found"
    card = (f"### #1 pick: {top['symbol']} - {top['name']}\n"
            f"Expecting **{pct(top['exp_ret_pct'])}** (close ≈ {top['exp_close']}), target {top['target_price']}, stop {top['stop_price']}.\n\n"
            f"**News read** ({top['news_engine']}): {top['catalyst']} - {top['news_summary']}\n\n"
            f"**Headlines used**\n{heads}")
    if top.get("low_conviction"):
        card = "> Low conviction: combined score is below the threshold.\n\n" + card

    sc = d.get("scorecard", {})
    rows = []
    for label, key in (("Rank-1 picks", "pick"), ("Shadow picks (2-5)", "shadow")):
        s = sc.get(key)
        if s:
            rows.append({"Group": label, "Sessions": int(s["n"]),
                         "Direction hit rate": f"{s['direction_hit_rate']:.0%}",
                         "P(up) prior": f"{s['avg_p_up_prior']:.0%}",
                         "Avg expected": pct(s["avg_expected_pct"]), "Avg actual": pct(s["avg_actual_pct"]),
                         "Mean abs error (pp)": f"{s['mean_abs_error_pp']:.2f}",
                         "Alpha vs Nifty": pct(s["avg_alpha_pct"]),
                         "Target hit": f"{s['target_hit_rate']:.0%}", "Stop hit": f"{s['stop_hit_rate']:.0%}"})
    score = pd.DataFrame(rows) if rows else pd.DataFrame({"Info": ["No session has been evaluated yet."]})

    hist = pd.DataFrame(d.get("history", []))
    if not hist.empty:
        hist = hist.rename(columns={"target_date": "Date", "rank": "#", "symbol": "Symbol",
                                    "exp_ret_pct": "Expected %", "act_ret_pct": "Actual %",
                                    "error_pp": "Error (pp)", "alpha_pct": "Alpha %",
                                    "dir_hit": "Dir hit", "target_hit": "Target hit",
                                    "stop_hit": "Stop hit", "p_up": "P(up)"}).round(2)
    return head, table, card, score, hist


with gr.Blocks(title="NSE LLM Picker") as demo:
    gr.Markdown("# NSE LLM Picker")
    head = gr.Markdown()
    table = gr.Dataframe(label="Top 5 for the next session", interactive=False)
    card = gr.Markdown()
    gr.Markdown("## Expectation vs reality")
    score = gr.Dataframe(label="Scorecard", interactive=False)
    hist = gr.Dataframe(label="Evaluated sessions (newest first)", interactive=False)
    gr.Button("Refresh").click(render, None, [head, table, card, score, hist])
    demo.load(render, None, [head, table, card, score, hist])

if __name__ == "__main__":
    demo.launch()
