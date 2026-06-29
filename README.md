# ⚖️ LexiNotebook — Multi-Agent Legal AI

**Created by Abdul Samad**

LexiNotebook is a multi-agent AI system for legal document analysis. Upload contracts, legislation, or any legal document and get an instant structured summary, interactive mindmap, and a citation-grounded Q&A counsel — all powered by IBM Docling and Google Gemini 2.5 Flash.

---

## Features

- **Multi-format ingestion** — PDFs, DOCX, PNG/JPG images, and audio dictations (WAV, MP3, M4A)
- **5-agent pipeline** — Ingestion → Analysis → Guardrail → Counsel → Validation
- **AI-generated summary** — structured markdown with Title, Parties, Obligations, Risks, and Deadlines
- **Interactive mindmap** — collapsible visual tree of the document's section hierarchy
- **Cited Q&A** — ask questions and get responses grounded in the uploaded documents with `[Document Name]` citations
- **Hallucination check** — a dedicated validation agent cross-checks every answer against the source text before it reaches you
- **Audio queries** — dictate your question via microphone; Gemini transcribes and routes it through the same pipeline
- **Guardrails** — unsafe or off-topic queries are blocked before they reach the counsel agent

---

## Agent Pipeline

```
Upload
  └─► [Agent 1] Ingestion       — Docling OCR / Gemini multimodal fallback
        └─► [Agent 2] Analysis  — Summary (markdown) + Mindmap (JSON), two separate calls
              └─► [Agent 3] Guardrail   — Ethics & relevance check on user queries
                    └─► [Agent 4] Counsel      — Draft legal response with citations
                          └─► [Agent 5] Validation  — Hallucination check vs source text
                                └─► Final response
```

---

## Quickstart

### 1. Clone & install

```bash
git clone https://github.com/your-username/lexinotebook.git
cd lexinotebook
pip install -r requirements.txt
```

### 2. Run

```bash
python lexinotebook.py
```

The app launches locally and prints a public `share=True` URL you can open in any browser.

### 3. In-notebook (Google Colab)

```python
!pip install -r requirements.txt
```

Then run the cell containing `demo.launch(debug=False, share=True)`. Gradio 5.x is required; use `.change()` on the file upload component (already configured).

---

## Requirements

| Package | Purpose |
|---|---|
| `gradio>=5.0.0` | Web UI and event handling |
| `google-genai>=1.0.0` | Gemini 2.5 Flash API client |
| `docling>=2.0.0` | IBM Docling PDF/DOCX/image OCR |
| `pydantic>=2.0.0` | Schema definitions |

Install all with:

```bash
pip install -r requirements.txt
```

---

## Configuration

The app takes your **Google Gemini API key** directly in the UI — no `.env` file needed. Get a key at [aistudio.google.com](https://aistudio.google.com).

Supported file types for upload: `.pdf`, `.docx`, `.png`, `.jpg`
Supported audio formats: `.wav`, `.mp3`, `.m4a`

---

## Architecture notes

**Why two analysis calls?**
Asking Gemini for a single JSON object containing a full markdown summary consistently causes JSON parse failures — the summary field contains quotes, newlines, and markdown syntax that break JSON string escaping. LexiNotebook splits the call: one free-form markdown call for the summary, one tight JSON-only call for the mindmap. This eliminates the parse error entirely.

**Why `.change()` instead of `.upload()`?**
Gradio 5.x passes file paths as strings to event handlers, not file objects. The `.upload()` event is also unreliable in Gradio 5 generators. `.change()` fires consistently and the `_resolve_path()` helper normalises whatever type Gradio hands back.

**Why `<details>/<summary>` for the mindmap?**
Native HTML collapsibles require zero JavaScript, render reliably inside Gradio's iframe sandbox, and handle arbitrarily deep nesting without a library dependency.

---

## Known limitations

- Document text is truncated at 30 000 chars for summary generation and 15 000 chars for mindmap generation. Very long documents may have incomplete coverage in later sections.
- Audio transcription requires the file to be uploadable to the Gemini Files API; very large audio files may time out.
- The Gemini 2.5 Flash model name may need adjustment depending on your API region and SDK version. Run `client.models.list()` to confirm available model IDs.

---

## License

MIT License — free to use, modify, and distribute with attribution.

---

*Built with [IBM Docling](https://github.com/DS4SD/docling) · [Google Gemini](https://ai.google.dev/) · [Gradio](https://gradio.app/)*
