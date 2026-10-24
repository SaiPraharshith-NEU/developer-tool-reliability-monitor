# Developer Tool Reliability Monitor
Streamlit interface for the A3/A4 saved issue collection and local classifier.

Run with Python 3.12:

```
pip install -r requirements.txt
streamlit run app.py
```

Use the three-report starter or up to 100 saved reports, upload CSV/JSON collections, or paste one public issue. Reports and CSV queues are generated in the user's session and downloaded through the browser. No AI-provider API key is used. It does not fetch issue URLs or verify live status. Public issue text only; no private reports or secrets.

The model is the existing A4 Multinomial Naive Bayes model with the same review gates. It achieved 21/30 agreement against AI-assisted draft labels, equal to the baseline. It is not a validated severity, fix or vulnerability classifier.

Data: the A3 snapshot collected October 1, 2026, with 41 python/cpython, 42 microsoft/vscode and 17 nodejs/node issues. Original source links remain attached. Training and reference labels are included for reproducibility and are not independent human ground truth. Names and report text originate from public GitHub issues; the snapshot is not all current issues.

The public cloud processes input for the current session. The application does not intentionally persist uploads or results to disk and does not send them to third-party model providers. Host infrastructure may retain operational logs. Download outputs you want to keep.

Course project by Sai Praharshith Gujjar. AI assistance was used for implementation, checks and documentation. No real user tests are claimed by the automated test suite.
