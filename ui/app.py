"""
ui/app.py

Component 18 — Streamlit UI

Two tabs:
  Tab 1: Query        — natural language Q&A with confidence scoring + citation panel
  Tab 2: Conflict Explorer — cross-year conflict detection for a chosen company + section

Run from project root:
    streamlit run ui/app.py
"""

import os
import sys

# Resolve project root so all sibling packages (retrieval, synthesis, etc.) import correctly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from config import COMPANIES, YEARS, TARGET_SECTIONS
from retrieval.retriever import Retriever
from synthesis.synthesizer import Synthesizer
from scoring.scorer import Scorer
from pipeline import run_query_pipeline, run_conflict_pipeline
from logger import setup_query_logger, setup_conflict_logger


# ---------------------------------------------------------------------------
# Cached resources — loaded once per session
# ---------------------------------------------------------------------------

@st.cache_resource
def load_retriever() -> Retriever:
    return Retriever()


# Synthesizer and Scorer are stateless (pure Groq API calls) — instantiate
# once per session for consistency, no heavy model load involved.
@st.cache_resource
def load_synthesizer() -> Synthesizer:
    return Synthesizer()


@st.cache_resource
def load_scorer() -> Scorer:
    return Scorer()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEVERITY_COLOR = {
    "high":   "#d62728",
    "medium": "#ff7f0e",
    "low":    "#2ca02c",
    "none":   "#aec7e8",
}


def severity_badge(severity: str) -> str:
    color = SEVERITY_COLOR.get(severity.lower(), "#888888")
    label = severity.upper()
    return (
        f'<span style="background-color:{color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;font-weight:bold;">{label}</span>'
    )


def render_query_tab(retriever: Retriever, synthesizer: Synthesizer, scorer: Scorer) -> None:
    st.header("Ask a Question")
    st.caption(
        "Ask anything about the 25 SEC 10-K filings (Apple, Microsoft, Amazon, "
        "Google, Meta — 2020–2024). The system identifies relevant companies, "
        "years, and sections automatically from your question."
    )

    with st.form("query_form"):
        query = st.text_input(
            "Your question",
            placeholder='e.g. "What were Apple\'s main risk factors in 2022?"',
        )
        submit = st.form_submit_button("Submit", type="primary")

    if not submit or not query.strip():
        return

    log = setup_query_logger(query)

    try:
        with st.spinner("Running query pipeline..."):
            result = run_query_pipeline(query, retriever, synthesizer, scorer)

        if isinstance(result, dict) and "error" in result:
            log.warning(f"PIPELINE | query_rejected | reason={result['error']!r}")
            st.error(f"Query rejected: {result['error']}")
            return

    except Exception as e:
        log.error(f"PIPELINE | EXCEPTION | {type(e).__name__}: {e}")
        st.error(f"An unexpected error occurred: {e}")
        return

    # --- Answer --------------------------------------------------------------
    st.subheader("Answer")
    st.markdown(result["answer"])

    # --- Confidence metrics --------------------------------------------------
    st.subheader("Confidence")
    col1, col2, col3 = st.columns(3)
    col1.metric("Confidence Score", f"{result['confidence_score']:.2f}")
    col2.metric("Faithfulness",     f"{result['faithfulness_score']:.2f}")
    col3.metric("Avg Retrieval Sim",f"{result['avg_retrieval_similarity']:.2f}")

    with st.expander("Score breakdown"):
        bd  = result["breakdown"]
        avg = result["avg_retrieval_similarity"]
        fth = result["faithfulness_score"]
        rw  = bd["retrieval_weight"]
        fw  = bd["faithfulness_weight"]
        st.write(f"- Avg retrieval similarity: **{avg:.4f}** (weight {rw})")
        st.write(f"- Faithfulness score: **{fth:.4f}** (weight {fw})")
        st.write(f"- Sources used: **{bd['num_sources']}**")
        st.write(
            f"- Formula: `{rw} × {avg:.4f} + {fw} × {fth:.4f}"
            f" = {result['confidence_score']:.4f}`"
        )

    # --- Citations -----------------------------------------------------------
    st.subheader(f"Sources ({result['context_chunks']} passages used)")
    for i, cite in enumerate(result["sources"], start=1):
        label = (
            f"[{i}] {cite['company']} · {cite['year']} · "
            f"{cite['section_name']} · similarity {cite['similarity_score']:.3f}"
        )
        with st.expander(label):
            st.caption(f"Chunk: `{cite['chunk_id']}`  |  File: `{cite['source_file']}`")
            st.write(cite["text"])


def render_conflict_tab() -> None:
    st.header("Conflict Explorer")
    st.caption(
        "Detect cross-year contradictions and material changes in SEC disclosures "
        "for a chosen company and section."
    )

    col1, col2 = st.columns(2)
    with col1:
        company = st.selectbox("Company", COMPANIES)
        section = st.selectbox("Section", list(TARGET_SECTIONS.keys()),
                               format_func=lambda k: f"{k} — {TARGET_SECTIONS[k]}")
    with col2:
        start_year = st.selectbox("Start Year", YEARS, index=0)
        valid_end_years = [y for y in YEARS if y > start_year]
        end_year = st.selectbox("End Year", valid_end_years,
                                index=len(valid_end_years) - 1 if valid_end_years else 0)

    n_pairs = len([(a, b) for a in range(start_year, end_year + 1)
                   for b in range(start_year, end_year + 1) if b > a])
    est_minutes = round(n_pairs * 65 / 60)

    st.warning(
        f"**Heads-up:** This will run **{n_pairs} LLM call(s)** "
        f"({start_year}–{end_year}, {n_pairs} year pair(s)). "
        f"A mandatory ~65-second delay between calls keeps the analysis within "
        f"Groq's rate limits. Estimated wait: **~{est_minutes} minute(s)**."
    )

    run = st.button("Run Analysis", type="primary", disabled=not valid_end_years)
    if not run:
        return

    log = setup_conflict_logger(company, section, start_year, end_year)

    try:
        with st.spinner(
            f"Analyzing {company} · {section} from {start_year} to {end_year}…"
        ):
            results = run_conflict_pipeline(company, section, start_year, end_year)
    except Exception as e:
        log.error(f"PIPELINE | EXCEPTION | {type(e).__name__}: {e}")
        st.error(f"An unexpected error occurred during conflict analysis: {e}")
        return

    if not results:
        st.info("No results returned. Check that the section exists for all selected years.")
        return

    # Summary strip — counts individual conflicts, not pairs
    high   = sum(1 for r in results for c in r.get("conflicts", []) if c.get("severity") == "high")
    medium = sum(1 for r in results for c in r.get("conflicts", []) if c.get("severity") == "medium")
    low    = sum(1 for r in results for c in r.get("conflicts", []) if c.get("severity") == "low")
    none_  = sum(1 for r in results if r.get("conflict_count", 0) == 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("High",   high)
    c2.metric("Medium", medium)
    c3.metric("Low",    low)
    c4.metric("No change", none_)

    st.divider()

    for result in results:
        year_a = result["year_a"]
        year_b = result["year_b"]
        conflict_count = result.get("conflict_count", 0)
        label = f"{year_a} vs {year_b} — {conflict_count} conflict(s) found"

        with st.expander(label, expanded=(conflict_count > 0)):
            if conflict_count == 0:
                st.success("No significant changes detected between these two years.")
                continue

            for conflict in result.get("conflicts", []):
                severity = conflict.get("severity", "low")
                st.markdown(
                    f"**{conflict.get('topic', 'Unnamed topic')}** &nbsp; "
                    + severity_badge(severity),
                    unsafe_allow_html=True,
                )
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**{year_a} claim**")
                    st.write(conflict.get("year_a_claim", "—"))
                with col_b:
                    st.markdown(f"**{year_b} claim**")
                    st.write(conflict.get("year_b_claim", "—"))
                st.caption(f"Change: {conflict.get('change_description', '—')}")
                st.divider()


# ---------------------------------------------------------------------------
# App entry point
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="SEC Filing Intelligence",
        page_icon="📄",
        layout="wide",
    )
    st.title("SEC Filing Intelligence System")
    st.caption(
        "RAG system over 25 10-K filings — Apple, Microsoft, Amazon, Google, Meta · 2020–2024"
    )

    retriever   = load_retriever()
    synthesizer = load_synthesizer()
    scorer      = load_scorer()

    tab_query, tab_conflict = st.tabs(["Query", "Conflict Explorer"])

    with tab_query:
        render_query_tab(retriever, synthesizer, scorer)

    with tab_conflict:
        render_conflict_tab()


if __name__ == "__main__":
    main()
