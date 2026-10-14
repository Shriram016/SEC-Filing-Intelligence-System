# Query types in RAG systems

## 1. The three categories (grouped by what the system must do)

```
                         USER QUESTION
                               |
        +----------------------+----------------------+
        |                      |                      |
   1. DIRECT             2. COMBINE            3. DECLINE / CLARIFY
 (one source)         (several sources)        (no clean answer)
        |                      |                      |
 - Single fact         - Compare entities     - Gap in the data
 - Explanation/        - Change over time     - Out of scope
   summary             - Multi-hop            - False premise
 - How-to              - Aggregation          - Ambiguous
 - Table/number

 Modifiers (apply to any branch):
   - Follow-up in a conversation
   - Adversarial / injection
```

The top level is what the system *does*: answer, combine or decline.
The subcategories are what the user *asks*. Each one gets its own test questions and metrics.

## 2. The same types as a flat list, sorted by frequency and cost of failure

The order shifts by domain (for finance, table numbers and aggregation move up).

| # | Query type | Example | What a good system does |
|---|---|---|---|
| 1 | **Direct lookup** | "What is the refund window?" | Finds the one passage and answers from it |
| 2 | **Unanswerable** | Topic fits, but the data has no answer | Refuses instead of guessing |
| 3 | **Comparison / multi-hop** | "How does plan A differ from plan B?" | Retrieves from each side and combines the facts |
| 4 | **Explanation / summary** | "Summarize our security policy." | Covers the topic across passages without inventing |
| 5 | **Ambiguous / vague** | "Tell me about the risks." | Answers broadly, or asks a clarifying question |
| 6 | **Follow-up in a conversation** | "And for the other plan?" | Uses earlier turns to resolve what is meant |
| 7 | **How-to / procedure** | "How do I reset my password?" | Gives ordered steps from the source |
| 8 | **Numbers in tables** | "What was Q3 revenue by region?" | Reads tables or figures correctly (plain text chunking does this badly) |
| 9 | **Aggregation / analysis** | "How many tickets mention billing?" | Counts or totals across many documents (plain RAG does this badly) |
| 10 | **False premise / adversarial** | "Why did revenue fall?" (it didn't), or an injection attempt | Corrects the premise, or resists the attack |
| 11 | **Out of scope** | "What's the weather today?" | Rejects early |
