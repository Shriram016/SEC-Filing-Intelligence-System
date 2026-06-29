"""
pipeline.py

Root trace wrappers for Langfuse observability.

Two functions:
  run_query_pipeline()    — wraps retrieve → synthesize → score under one trace
  run_conflict_pipeline() — wraps analyze_conflicts() under one trace

The @observe() decorator on each function creates the root trace in Langfuse.
Child @observe() decorators on the component methods (retriever, synthesizer,
scorer, conflict_analyzer) automatically nest under this root.
"""

from langfuse import observe

from conflict.conflict_analyzer import analyze_conflicts


@observe(name="query-pipeline")
def run_query_pipeline(query: str, retriever, synthesizer, scorer) -> dict:
    """
    Full query pipeline: retrieve → synthesize → score.

    Returns:
        dict with keys from both synthesizer and scorer output:
            query, answer, sources, model_used, context_chunks,
            confidence_score, faithfulness_score, avg_retrieval_similarity, breakdown
        OR  {"error": str} if the query is rejected by the retriever.
    """
    chunks = retriever.retrieve(query)

    if isinstance(chunks, dict) and "error" in chunks:
        return chunks

    if not chunks:
        return {"error": "No relevant passages found for this query."}

    result = synthesizer.synthesize(query, chunks)
    score = scorer.score(result)

    return {**result, **score}


@observe(name="conflict-pipeline")
def run_conflict_pipeline(
    company: str,
    section: str,
    start_year: int,
    end_year: int,
) -> list:
    """
    Full conflict pipeline: analyze all year pairs for a company + section.
    """
    return analyze_conflicts(company, section, start_year, end_year)
