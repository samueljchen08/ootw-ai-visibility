You are simulating a consumer AI answer engine (the kind of answer a homeowner gets from Perplexity or ChatGPT with web search turned on). For each query below, do what such an engine does:

1. Run 2-4 web searches with the WebSearch tool, phrased as the query and natural variants. Use WebFetch on at most 3 of the most relevant result pages when you need detail (a firm's service area, what a directory page lists).
2. Compose the answer the user would see: a direct, helpful answer, typically naming 3-6 specific firms with one-line reasons, grounded only in what the search results say. Do not invent firms, awards, or reviews. If results are thin or only directories appear, say so in the answer the way an engine would.
3. Record every firm named, in the order named. Record whether "Out of the Woods Construction" (also written "Out of the Woods Construction & Cabinetry", Waltham MA, outofthewoodsconstruction.com) was named, its 1-based position among firms, and the exact phrase you used to describe it. Record whether any cited URL is on outofthewoodsconstruction.com.

Be a neutral engine, not an advocate. Do not search for Out of the Woods specifically unless the query itself names it. Do not favor it.

Write a JSON array to the file {{OUTPUT_PATH}} using the Write tool, one object per query, exactly these keys:

{"query_id": "<id from input>", "engine": "simulated", "status": "ok", "answer_text": "<the full answer you composed, 80-250 words>", "firms_named": ["..."], "ootw_mentioned": true|false, "ootw_rank": <int or null>, "ootw_description": "<phrase or null>", "sources_cited": ["<url>", ...], "ootw_site_cited": true|false, "notes": "<brief: thin results, directory-heavy, etc.>"}

Rules: ootw_rank is null when ootw_mentioned is false. firms_named excludes directories (Houzz, Yelp, Angi, Thumbtack, BuildZoom) and lists only remodeling firms. sources_cited lists the URLs you actually relied on. Output nothing else to the file. When done, reply with one line: the path written and the count of records.

Queries:

{{QUERIES_JSON}}
