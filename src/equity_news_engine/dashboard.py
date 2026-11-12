"""Art-directed Streamlit publication interface for stored equity intelligence."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from .database import initialize_database
from .reporting import (build_intelligence_report, event_importance_chart,
                        event_type_chart, export_csv, export_json, news_volume_chart,
                        records_for_export, sentiment_chart)
from .repository import Repository


PAGES = ["Search", "Overview", "News Feed", "Events", "Sentiment", "Timeline", "Sources", "Export"]
_PALETTE = {"paper": "#171715", "ink": "#F1EEE5", "verm": "#E65C3A", "stone": "#A6A79D", "graphite": "#30302C"}


def _show_table(records: list[dict], empty_message: str) -> None:
    if records:
        st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
    else:
        st.info(empty_message)


def _editorial_rows(records: list[dict], *, kind: str) -> None:
    """Render compact publication-style rows; all record text is HTML-escaped."""
    if not records:
        st.info("No records match this edition. Adjust the filters or check back when new information is available.")
        return
    for row in records:
        if kind == "article":
            stamp = row.get("published_at") or row.get("first_seen_at") or "Date unavailable"
            title = row.get("title") or "Untitled report"
            meta = f"{row.get('ticker') or 'MARKET'}  ·  {stamp}"
            detail = row.get("description") or row.get("source_name") or row.get("url") or "Stored research item"
            st.markdown(
                f'<article class="article-row"><div class="article-meta">{escape(str(meta))}</div>'
                f'<div><div class="article-title">{escape(str(title))}</div>'
                f'<div class="article-meta">{escape(str(detail))}</div></div></article>',
                unsafe_allow_html=True,
            )
        else:
            stamp = row.get("timestamp") or "Date unavailable"
            category = row.get("type") or "Unclassified"
            title = row.get("headline") or row.get("event_id") or "Untitled event"
            importance = row.get("importance")
            score = f"{importance:.2f}" if isinstance(importance, (float, int)) else "—"
            st.markdown(
                f'<article class="event-row"><div class="article-meta">{escape(str(stamp))}</div>'
                f'<div><span class="tag">{escape(str(category))}</span><div class="article-title">{escape(str(title))}</div>'
                f'<div class="article-meta">{escape(str(row.get("ticker") or "MARKET"))}</div></div>'
                f'<div class="article-meta">IMPORTANCE<br><b>{score}</b></div></article>',
                unsafe_allow_html=True,
            )


def _page_title(number: str, title: str, dek: str) -> None:
    st.markdown(f'<div class="page-kicker">{number} / Intelligence desk</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="edition"><span>{escape(dek)}</span><span>Information moves markets.</span></div>', unsafe_allow_html=True)


def _style_charts() -> None:
    px.defaults.template = "plotly_dark"
    px.defaults.color_discrete_sequence = [_PALETTE["verm"], _PALETTE["ink"], _PALETTE["stone"]]


def render_app() -> None:
    st.set_page_config(page_title="EQUITY INTELLIGENCE", page_icon="E", layout="wide")
    css = Path(__file__).with_name("assets").joinpath("editorial.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    initialize_database()
    repository = Repository()
    _style_charts()

    st.markdown(
        '<div class="masthead"><div class="brand">EQUITY<span class="brand-dot" aria-hidden="true"></span><br>INTELLIGENCE</div>'
        '<div class="brand-meta">Independent market intelligence<br>Research edition &nbsp; / &nbsp; 01</div></div>',
        unsafe_allow_html=True,
    )

    try:
        equities = repository.list_records("EQUITIES", limit=10000)
        tickers = [row["ticker"] for row in equities]
        page = st.radio("Desk", PAGES, horizontal=True, label_visibility="collapsed")
        with st.sidebar:
            st.markdown("## EDITION FILTERS")
            st.caption("Refine the records shown across the intelligence desk.")
            choices = ["All equities", *tickers]
            saved = st.session_state.get("ticker_filter", "All equities")
            selected = st.selectbox("Equity", choices, index=choices.index(saved) if saved in choices else 0)
            today = date.today()
            date_range = st.date_input("Publication window", value=(today - timedelta(days=30), today))
            st.markdown("---")
            st.caption("EQUITY INTELLIGENCE  /  INFORMATION MOVES MARKETS")

        ticker = None if selected == "All equities" else selected
        if len(date_range) == 2:
            start, end = date_range[0].isoformat(), date_range[1].isoformat() + "T23:59:59"
        else:
            start = end = None
        filters = {"ticker": ticker} if ticker else {}

        if page == "Search":
            _page_title("01", "Research the record.", "Search stored coverage by ticker, then inspect the matching record set.")
            with st.form("search_form"):
                query = st.text_input("Ticker / equity", value=ticker or "", placeholder="Search a ticker already in the register")
                submitted = st.form_submit_button("SEARCH THE REGISTER")
            if submitted:
                normalized = query.strip().upper()
                if normalized and normalized not in tickers:
                    st.warning("That ticker is not in the equity register yet.")
                else:
                    st.session_state["ticker_filter"] = normalized or "All equities"
                    st.rerun()
            st.subheader("News record")
            _editorial_rows(repository.list_records("ARTICLES", filters=filters, start=start, end=end), kind="article")
            st.subheader("Event register")
            _editorial_rows(repository.list_records("EVENTS", filters=filters, start=start, end=end), kind="event")

        elif page == "Overview":
            _page_title("02", "The intelligence briefing.", "A measured view of coverage, events and recorded sentiment in the selected window.")
            articles = repository.list_records("ARTICLES", filters=filters, start=start, end=end)
            events = repository.list_records("EVENTS", filters=filters, start=start, end=end)
            sentiments = repository.sentiment_records(ticker=ticker, start=start, end=end)
            sources = repository.list_records("SOURCES", limit=10000)
            cols = st.columns([1, 1, 1, 1.25])
            for col, label, value in zip(cols, ["Articles", "Events", "Sentiment reads", "Publishers"], [len(articles), len(events), len(sentiments), len(sources)]):
                col.metric(label, f"{value:02,d}")
            left, right = st.columns([1.3, 1])
            with left:
                st.markdown("### Coverage pulse")
                chart = news_volume_chart(articles)
                st.plotly_chart(chart, use_container_width=True) if chart else st.info("Dated coverage will appear here when records are available.")
            with right:
                st.markdown("### Recorded tone")
                chart = sentiment_chart(sentiments)
                st.plotly_chart(chart, use_container_width=True) if chart else st.info("Sentiment distribution appears when results are recorded.")
            low, high = st.columns(2)
            with low:
                st.markdown("### Event importance")
                chart = event_importance_chart(events)
                st.plotly_chart(chart, use_container_width=True) if chart else st.info("Importance distribution appears when scored events are available.")
            with high:
                st.markdown("### Event mix")
                chart = event_type_chart(events)
                st.plotly_chart(chart, use_container_width=True) if chart else st.info("Event categories appear as the register grows.")

        elif page == "News Feed":
            _page_title("03", "The news desk.", "Headlines and source metadata from the selected coverage window.")
            articles = repository.list_records("ARTICLES", filters=filters, start=start, end=end)
            _editorial_rows(articles, kind="article")

        elif page == "Events":
            _page_title("04", "The event register.", "Structured market events, ordered by time and classified by recorded type.")
            events = repository.list_records("EVENTS", filters=filters, start=start, end=end)
            _editorial_rows(events, kind="event")
            a, b = st.columns(2)
            with a:
                chart = event_type_chart(events)
                if chart:
                    st.plotly_chart(chart, use_container_width=True)
            with b:
                chart = event_importance_chart(events)
                if chart:
                    st.plotly_chart(chart, use_container_width=True)

        elif page == "Sentiment":
            _page_title("05", "Sentiment, in context.", "Recorded model outputs scoped to the selected equity and period.")
            sentiments = repository.sentiment_records(ticker=ticker, start=start, end=end)
            chart = sentiment_chart(sentiments)
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            _show_table(sentiments, "No sentiment results are recorded for this selection.")

        elif page == "Timeline":
            _page_title("06", "The sequence of events.", "A chronological reading of dated articles and event records.")
            events = repository.list_records("EVENTS", filters=filters, start=start, end=end)
            articles = repository.list_records("ARTICLES", filters=filters, start=start, end=end)
            points = [{"timestamp": row.get("timestamp"), "type": "EVENT", "label": row.get("headline") or row.get("type") or row.get("event_id")} for row in events]
            points.extend({"timestamp": row.get("published_at"), "type": "NEWS", "label": row.get("title") or row.get("article_id")} for row in articles)
            frame = pd.DataFrame(points)
            if not frame.empty:
                frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
                frame = frame.dropna(subset=["timestamp"])
            if frame.empty:
                st.info("The chronology will take shape when dated articles or events are available.")
            else:
                fig = px.scatter(frame, x="timestamp", y="type", hover_name="label", title="Chronology of recorded information")
                fig.update_traces(marker={"size": 13, "line": {"width": 1, "color": _PALETTE["ink"]}})
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(frame.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)

        elif page == "Sources":
            _page_title("07", "The publisher directory.", "A register of known sources and their recorded classifications.")
            sources = repository.list_records("SOURCES", limit=10000)
            if not sources:
                st.info("No publishers are registered yet.")
            else:
                for source in sources:
                    name = escape(str(source.get("name") or "Unnamed publisher"))
                    source_type = escape(str(source.get("source_type") or "Unclassified"))
                    primary = "PRIMARY" if source.get("primary_source") else "SOURCE"
                    st.markdown(f'<div class="source-row"><b>{name}</b><span>{source_type}</span><span>{primary}</span></div>', unsafe_allow_html=True)
                counts = pd.DataFrame(sources)
                counts["source_type"] = counts["source_type"].fillna("Unspecified")
                counts = counts.groupby("source_type").size().rename("Sources").reset_index()
                st.plotly_chart(px.bar(counts, x="source_type", y="Sources", title="Publishers by source type"), use_container_width=True)

        elif page == "Export":
            _page_title("08", "Prepare the research note.", "Export stored records or assemble a structured intelligence report.")
            dataset = st.selectbox("Report dataset", ["articles", "events", "features"])
            records = records_for_export(repository, dataset, ticker=ticker, start=start, end=end)
            st.caption(f"{len(records)} stored record(s) in scope")
            _show_table(records, "No records match this report scope. Empty CSV and JSON downloads remain available.")
            with st.expander("Report contents", expanded=True):
                st.markdown("Select a dataset above, then download a tabular extract or the complete scoped report.")
                stem = dataset
                st.download_button("DOWNLOAD CSV", export_csv(records), f"{stem}.csv", "text/csv")
                st.download_button("DOWNLOAD JSON", export_json(records), f"{stem}.json", "application/json")
                report = build_intelligence_report(repository, ticker=ticker, start=start, end=end)
                st.download_button("DOWNLOAD INTELLIGENCE REPORT", json.dumps(report, ensure_ascii=False, indent=2), "intelligence_report.json", "application/json")
                st.json({"scope": report["scope"], "record_counts": report["record_counts"], "data_status": report["data_status"]})

    except Exception as exc:
        st.error(f"The intelligence desk could not load this view: {exc}")
        st.caption("Check the database path and schema initialization, then retry.")
