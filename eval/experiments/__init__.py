"""Iteration 2 experiments on the synthetic dev set (specs/002-decide-on-dev).

These modules run the registered experiments through the pipeline's own adapters, compare
retrievers, and apply the registered decision rules. They live in `eval/` because they evaluate
variants, but unlike `eval/answers.py` they never read `data/receipts.jsonl`. An architecture
test enforces that. Their results are written only by the code, under
`explorations/results/iter2/`.
"""
