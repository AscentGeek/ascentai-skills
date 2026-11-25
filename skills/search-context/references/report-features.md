# Required report features (v2)

The report's features are drawn in code by the renderer in `scripts/sc.py`. When you change the renderer, change this list and `scripts/check_report.py` along with it.
If `check_report.py` reports even one ✗ after Step 7, do not hand the report over.

## Screen order (keep the content light)
1. **Header** · seed, market, date, monthly search volume · path count · keyword count
2. **Summary** (2~3 sentences) + **What to do from a marketing perspective** (M1… 3~5 items: the to-do, the evidence, the execution, related keyword chips → clicking one selects that path on the map)
3. **Path map** (the main feature)
   - **Path count = the number the user chose at the start (100 · 200 · 300, default 300)**; the "100 / 200 / 300 paths" control in the map header shows only the values within the range received (hidden if there is only one) and raises or lowers it → the map, the chat evidence and the path count display all change together, remembered in the viewer's browser
   - The seed sits in the middle, left = preceding searches, right = following searches, 4 levels, line thickness = path count
   - **Only the top 3 per level** are shown, the rest behind "+N more", which expands on click and collapses again with "− collapse"
   - **Hovering "+N more" shows a modal of the hidden keywords** (keyword and path count) · clicking a keyword in the modal expands it and selects that path
   - **Hovering a keyword highlights every path that contains it** (including the same keyword on other branches), with "Analyze this path" / "Select" right on the card
   - The **"Hover card" toggle** in the map header: turning it off stops the cards and the hover highlight and shows **only the selected path in full clarity (the rest dimmed)**. Remembered in the viewer's browser. Close with the card's × button or Esc
   - **It starts at "Fit", showing everything**: the viewBox matches the actually drawn extent (labels included), and the map height is set to the drawing's aspect ratio (320px~75% of the screen)
   - The map is full width; the "Selected path" (선택한 경로) panel sits below the map
   - Wheel zoom, drag to pan (8px screen threshold), ＋ / − / Fit / ◎
   - Keyword search (list ordered by search volume) → picking one selects the path up to that keyword
   - **Clicking a keyword (selecting it) pins the highlight on every path that contains it** (including the same keyword on other branches, with the seed→keyword path drawn thicker),
     and **any open modal closes** so the full path is not hidden. The modal does not reappear while the cursor stays on the same keyword, but does when it moves to another keyword.
     Briefly hovering another keyword switches to that keyword's highlight, then returns to the selection highlight when the mouse leaves. The selected path is shown in the "Selected path" (선택한 경로) panel below the map
4. **Question · path analysis chat** (below the map, replacing the "Selected path" (선택한 경로) panel)
   - **Selected path bar** at the top: the selected path (the clicked keyword in blue), how many paths run through it, "Path analysis" (경로 분석) / "View saved analyses" / "Clear selection"
   - **Conversation area**: when the user asks a question, the user's Claude (`sample`) answers immediately (streaming), **based only on this page's path data**
     - Evidence: the branches searched after · before the seed and their path counts, the next level of the main branches, up to 45 paths containing the selected keyword (or representative paths if there are none), saved analyses of the selected path, the report summary · to-dos, and the earlier conversation
     - Keywords in the answer (in 「」) are shown as chips, and clicking one selects that path on the map · if the question needs a SERP, "Path analysis" (경로 분석) is recommended
   - The SERPs for path analysis are looked up in this order: ① the SERPs fetched when the report was built (E1…, embedded in the page) ② the page store ③ ListeningMind `serp` · a SERP already fetched is never paid for again
   - **Path analysis** also enters the same conversation flow as a card (progress steps shown → result: purpose · interpretation · insights · to-dos · verdict, evidence behind an expander)
   - **Suggested question chips**: different when nothing is selected (the biggest flow, marketing opportunities, paths with conditions attached) and when something is (analyze this path, the searches before and after, similar paths)
   - Input box: Enter to send, Shift+Enter for a newline · when Claude or the connector is not connected or not permitted, guidance plus "Open permission settings"
   - The conversation history is kept in a per-viewer store (`data/users/me/chat/…`) and resumes when the page is reopened
5. **Saved analyses** · a **numbered card** per analysis (purpose, path, date, "View analysis ▾ / collapse ▴"). An expanded card is set apart by its border and header background,
   its body sits inside a coloured left-hand band, and **only one is expanded at a time** (opening another closes the previous one). View on map · delete sit below the expanded card. Expanding shows the analysis content (insights · to-dos), and the evidence takes one more expand inside that
   (no separate evidence SERP section at the bottom of the report)

## Differences by execution tool (`render --host`)
- **claude** · 4 and 5 above exactly as written (the user's Claude `sample` + ListeningMind `serp` + the `db` store)
- **chatgpt** · the page does not call an LLM
  - "Copy path analysis request" (경로 분석 요청 복사) (on the selected path bar · hover card): copies the path plus the analysis instructions (ChatGPT looks up the SERP through the ListeningMind connector's `serp`; evidence stated in words, like "keyword" AI overview · "keyword" organic result #N (site name); answer in readable prose)
  - Question input: copies a request text containing the path-data evidence (same as above) + the earlier questions + the question
  - The request text and a "Copy again" button appear in the conversation area (if automatic copying is blocked, guidance to select and copy manually)
  - Claude connection · permission guidance, saved analyses and conversation-history saving do not appear. The visible text must contain no "Claude"

## Common behaviour
- Clicking empty space on the map clears the selection (releasing after a drag to pan is not a click · the selection is kept while a path analysis is running)
- The Target keyword on the hover card is an outline-only chip (body colour), to distinguish it from the filled "Analyze this path" button

## What we do not do
- Comparison with a past time point (A/B), a full path list, type · change cards, copying a request sentence
