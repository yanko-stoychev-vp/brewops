## Steps

1. If `brewops.db` is missing, run `uv run seed`.
2. Run the tests: `uv run pytest`. All must pass.
3. If the change relates to Lab A, run `uv run scripts/lab_a_check.py` and require `[DONE]`.
4. Start the app with `uv run start`, confirm http://localhost:8123 loads and `/api/stats` responds, then stop it.
5. Report each command you ran and its result. If anything failed, say so plainly.