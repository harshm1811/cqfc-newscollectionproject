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
from .integration import run_equity_intelligence
from .reporting import (build_intelligence_report, event_importance_chart,
                        event_type_chart, export_csv, export_json, news_volume_chart,
                        feature_frame, records_for_export, sentiment_chart)
from .repository import Repository


PAGES = ["Search", "Overview", "News Feed", "Events", "Sentiment", "Timeline", "Sources", "Export"]
_PALETTE = {"paper": "#171715", "ink": "#F1EEE5", "verm": "#E65C3A", "stone": "#A6A79D", "graphite": "#30302C"}


def _show_table(records: list[dict], empty_message: str) -> None:
    if records:
        st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)
    else:
        st.info(empty_message)


def _with_source_metadata(records: list[dict], repository: Repository) -> list[dict]:
    sources = {
        row["source_id"]: row
        for row in repository.list_records("SOURCES", limit=10000)
        if row.get("source_id") is not None
    }
    enriched = []
    for row in records:
        source = sources.get(row.get("source_id"), {})
        enriched.append({
            **row,
            "source_name": source.get("name", "Unknown publisher"),
            "source_type": source.get("source_type", "UNKNOWN"),
        })
    return enriched


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
            source_label = row.get("source_name") or "Unknown publisher"
            source_type = row.get("source_type") or "UNKNOWN"
            provenance = "PRIMARY SOURCE" if row.get("primary_source") == 1 else "SECONDARY"
            description = row.get("description") or row.get("url") or "Stored research item"
            detail = f"{source_label} · {source_type} · {provenance} · {description}"
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
            _page_title("01", "Research the record.", "Run a company analysis or search the stored record set.")
            with st.form("search_form"):
                query = st.text_input("Company / ticker", value=ticker or "", placeholder="For example: TCS or Infosys")
                fetch_text = st.checkbox("Attempt article-page extraction", value=True)
                extraction_limit = st.slider("Maximum pages to fetch", min_value=1, max_value=20, value=5, disabled=not fetch_text)
                similarity_threshold = st.slider(
                    "Semantic duplicate similarity threshold", min_value=0.30, max_value=0.95,
                    value=0.65, step=0.05,
                    help="Lower values group more similar stories; tune against your review needs.",
                )
                search_col, run_col = st.columns(2)
                searched = search_col.form_submit_button("SEARCH THE REGISTER")
                submitted = run_col.form_submit_button("GENERATE ANALYSIS")
            if submitted:
                if not query.strip():
                    st.warning("Enter a company name or ticker to run an analysis.")
                else:
                    try:
                        with st.spinner("Collecting public coverage and building the intelligence record…"):
                            run_result = run_equity_intelligence(
                                query.strip(), start_date=start, end_date=end,
                                fetch_article_text=fetch_text, article_text_limit=extraction_limit,
                                semantic_similarity_threshold=similarity_threshold,
                            )
                        st.session_state["last_analysis_result"] = run_result
                        resolved_ticker = run_result.get("ticker")
                        if resolved_ticker:
                            st.session_state["ticker_filter"] = resolved_ticker
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Analysis could not be completed: {exc}")
            if searched:
                normalized = query.strip().upper()
                if normalized and normalized not in tickers:
                    st.warning("That ticker is not in the equity register yet.")
                else:
                    st.session_state["ticker_filter"] = normalized or "All equities"
                    st.rerun()
            latest_run = st.session_state.get("last_analysis_result")
            if latest_run:
                status = latest_run.get("status")
                status_view = st.success if status == "succeeded" else st.warning
                status_view(
                    f"Run {status}: {latest_run.get('raw_article_count', 0)} candidates, "
                    f"{latest_run.get('processed_article_count', 0)} articles, "
                    f"{latest_run.get('event_count', 0)} events; sentiment model "
                    f"{latest_run.get('sentiment_model') or 'not available'}; semantic embeddings "
                    f"{latest_run.get('semantic_embedding_backend') or 'not available'}."
                )
                if latest_run.get("extraction_status_counts"):
                    st.caption(f"Page extraction outcomes: {latest_run['extraction_status_counts']}")
                failures = latest_run.get("failures") or []
                if failures:
                    with st.expander(f"Collection and analysis issues ({len(failures)})"):
                        st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)
            st.subheader("News record")
            _editorial_rows(_with_source_metadata(repository.list_records("ARTICLES", filters=filters, start=start, end=end), repository), kind="article")
            st.subheader("Event register")
            _editorial_rows(repository.list_records("EVENTS", filters=filters, start=start, end=end), kind="event")

        elif page == "Overview":
            _page_title("02", "The intelligence briefing.", "A measured view of coverage, events and recorded sentiment in the selected window.")
            articles = repository.list_records("ARTICLES", filters=filters, start=start, end=end)
            events = repository.list_records("EVENTS", filters=filters, start=start, end=end)
            sentiments = repository.sentiment_records(ticker=ticker, start=start, end=end)
            sources = repository.list_records("SOURCES", limit=10000)
            features = feature_frame(repository.list_records(
                "DAILY_FEATURES", filters=filters, start=start, end=end, limit=10000
            ))
            relevant_count = sum(float(row.get("relevance_score") or 0) > 0 for row in articles)
            publisher_count = len({row.get("source_id") for row in articles if row.get("source_id") is not None})
            independent_publishers = len({
                row.get("source_id") for row in articles
                if row.get("source_id") is not None and row.get("independent_source") == 1
            })
            independent_value = (
                independent_publishers
                if any(row.get("independent_source") is not None for row in articles)
                else "—"
            )
            cols = st.columns(5)
            metric_values = [len(articles), relevant_count, len(events), publisher_count, independent_value]
            for index, (col, label, value) in enumerate(zip(cols, ["Articles discovered", "Relevant articles", "Unique events", "Publishers", "Independent publishers"], metric_values)):
                rendered_value = f"{value:02,d}" if isinstance(value, int) else value
                if index == 4:
                    col.metric(label, rendered_value, help="Unavailable for legacy records collected before independent-source provenance was persisted.")
                else:
                    col.metric(label, rendered_value)
            if not features.empty:
                st.markdown("### Company sentiment series")
                if ticker:
                    latest = features[features["ticker"] == ticker].iloc[-1]
                    sentiment_cols = st.columns(4)
                    for col, label, key in zip(
                        sentiment_cols,
                        ["Weighted sentiment", "24H sentiment", "7D sentiment", "30D sentiment"],
                        ["weighted_sentiment", "sentiment_1d", "sentiment_7d", "sentiment_30d"],
                    ):
                        value = latest.get(key)
                        col.metric(label, f"{float(value):+.3f}" if pd.notna(value) else "—")
                    trend_cols = [key for key in ("weighted_sentiment", "sentiment_1d", "sentiment_7d", "sentiment_30d") if key in features]
                    if trend_cols:
                        st.line_chart(features.set_index("feature_date")[trend_cols], height=260)
                else:
                    latest_by_ticker = features.sort_values("feature_date").groupby("ticker", as_index=False).tail(1)
                    sentiment_cols = [key for key in ("weighted_sentiment", "sentiment_1d", "sentiment_7d", "sentiment_30d") if key in features]
                    st.dataframe(latest_by_ticker[["ticker", "feature_date", *sentiment_cols]], use_container_width=True, hide_index=True)
                    if "weighted_sentiment" in features:
                        st.line_chart(features.pivot(index="feature_date", columns="ticker", values="weighted_sentiment"), height=260)
                volume_cols = [key for key in ("news_count", "unique_event_count") if key in features]
                if volume_cols:
                    st.markdown("### Coverage and event volume")
                    if ticker:
                        st.line_chart(features.set_index("feature_date")[volume_cols], height=220)
                    else:
                        for key in volume_cols:
                            st.caption(key.replace("_", " ").title())
                            st.line_chart(features.pivot(index="feature_date", columns="ticker", values=key), height=180)
                polarity_cols = [key for key in ("positive_event_count", "negative_event_count", "neutral_event_count") if key in features]
                if polarity_cols:
                    st.markdown("### Event polarity")
                    if ticker:
                        st.bar_chart(features.set_index("feature_date")[polarity_cols], height=220)
                    else:
                        for key in polarity_cols:
                            st.caption(key.replace("_", " ").title())
                            st.bar_chart(features.pivot(index="feature_date", columns="ticker", values=key), height=180)
                st.dataframe(features.sort_values(["ticker", "feature_date"], ascending=[True, False]), use_container_width=True, hide_index=True)
            else:
                st.info("Daily weighted sentiment appears after event analysis has generated dated feature records.")
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
            if ticker:
                runs = repository.list_records(
                    "COLLECTION_RUNS", filters={"requested_ticker": ticker},
                    order_by="created_at", limit=10,
                )
            else:
                runs = repository.list_records("COLLECTION_RUNS", order_by="created_at", limit=10)
            st.markdown("### Recent analysis runs")
            if runs:
                st.dataframe(pd.DataFrame([
                    {"Created": run.get("created_at"), "Ticker": run.get("requested_ticker"),
                     "Status": run.get("status"), "Articles": run.get("article_count"),
                     "Events": run.get("event_count"), "Failures": run.get("failure_count"),
                     "Run ID": run.get("run_id")}
                    for run in runs
                ]), use_container_width=True, hide_index=True)
                latest_run = runs[0]
                if latest_run.get("failure_count", 0):
                    try:
                        failure_rows = json.loads(latest_run.get("failures_json") or "[]")
                    except json.JSONDecodeError:
                        failure_rows = [{"error": "Stored run failure details could not be decoded."}]
                    with st.expander("Latest run issues"):
                        st.dataframe(pd.DataFrame(failure_rows), use_container_width=True, hide_index=True)
            else:
                st.info("No collection runs have been recorded for this scope.")

        elif page == "News Feed":
            _page_title("03", "The news desk.", "Headlines and source metadata from the selected coverage window.")
            articles = _with_source_metadata(repository.list_records("ARTICLES", filters=filters, start=start, end=end), repository)
            _editorial_rows(articles, kind="article")

        elif page == "Events":
            _page_title("04", "The event register.", "Structured market events, ordered by time and classified by recorded type.")
            events = repository.list_records("EVENTS", filters=filters, start=start, end=end)
            _editorial_rows(events, kind="event")
            if events:
                choices = {f"{row.get('headline') or row['event_id']} · {row['event_id']}": row for row in events}
                selected_event = st.selectbox("Inspect event coverage", list(choices))
                event = choices[selected_event]
                linked = _with_source_metadata(repository.linked_articles(event["event_id"]), repository)
                independent_count = event.get("independent_source_count")
                primary_status = event.get("primary_source_present")
                st.caption(
                    f"{len(linked)} underlying article(s) · {independent_count if independent_count is not None else 'unknown'} independent source(s) · "
                    f"primary source confirmed: {'yes' if primary_status == 1 else 'no' if primary_status == 0 else 'unknown'} · "
                    f"event sentiment {event.get('sentiment_score')}"
                )
                _show_table(linked, "No linked articles are available for this event.")
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
            models = sorted({row.get("model_version") or "unspecified" for row in sentiments})
            if models:
                selected_model = st.selectbox("Sentiment model", ["All models", *models])
                if selected_model != "All models":
                    sentiments = [row for row in sentiments if (row.get("model_version") or "unspecified") == selected_model]
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
                with st.expander("Read structured findings", expanded=True):
                    st.json({key: report[key] for key in (
                        "scope", "record_counts", "coverage", "sentiment", "event_breakdown",
                        "major_positive_events", "major_negative_events", "emerging_themes",
                        "key_risks", "source_analysis", "failures", "data_status",
                    )})

    except Exception as exc:
        st.error(f"The intelligence desk could not load this view: {exc}")
        st.caption("Check the database path and schema initialization, then retry.")
