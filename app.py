import os
import json
import traceback
import gradio as gr
from pydantic import BaseModel, Field

from google import genai
from google.genai import types
from docling.document_converter import DocumentConverter


# ---------------------------------------------------------------------------
# Schema
# We avoid a recursive Pydantic model for the mindmap (the GenAI SDK chokes on
# deeply-nested/recursive schemas). We ask for JSON via the prompt instead and
# parse it ourselves, which is far more robust than response_schema with dict.
# ---------------------------------------------------------------------------

def get_client(api_key: str):
    """Initialize the Google GenAI client."""
    if not api_key:
        raise ValueError("Please provide a valid Gemini API Key.")
    return genai.Client(api_key=api_key)


def _resolve_path(file_obj):
    """Gradio 5 may hand us a str path, a dict, or a NamedString. Normalize it."""
    if isinstance(file_obj, str):
        return file_obj
    # gr.File objects expose .name; dicts use 'path' or 'name'
    if hasattr(file_obj, "name"):
        return file_obj.name
    if isinstance(file_obj, dict):
        return file_obj.get("path") or file_obj.get("name")
    return str(file_obj)


def render_mindmap_html(node: dict, _root: bool = True) -> str:
    """
    Render a mindmap dict ({'name', 'description', 'children': [...]}) as a
    collapsible, styled HTML tree. Pure HTML/CSS — uses <details>/<summary> so
    nodes expand/collapse with no JS, which is robust inside Gradio's iframe.
    """
    if not isinstance(node, dict):
        return ""

    name = str(node.get("name", "Untitled"))
    desc = str(node.get("description", "")).strip()
    children = node.get("children") or []
    has_children = isinstance(children, list) and len(children) > 0

    # Escape minimal HTML-sensitive chars
    def esc(s):
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    name_html = esc(name)
    desc_html = f'<div class="lx-desc">{esc(desc)}</div>' if desc else ""

    if has_children:
        kids = "".join(render_mindmap_html(c, _root=False) for c in children)
        node_html = (
            f'<details class="lx-node" open>'
            f'<summary class="lx-summary"><span class="lx-name">{name_html}</span>'
            f'<span class="lx-count">{len(children)}</span></summary>'
            f'{desc_html}'
            f'<div class="lx-children">{kids}</div>'
            f'</details>'
        )
    else:
        node_html = (
            f'<div class="lx-node lx-leaf">'
            f'<div class="lx-summary lx-leaf-summary">'
            f'<span class="lx-bullet">•</span><span class="lx-name">{name_html}</span></div>'
            f'{desc_html}'
            f'</div>'
        )

    if _root:
        style = """
        <style>
        .lx-tree { font-family: 'Inter', system-ui, sans-serif; line-height: 1.4;
                   color: #e6e6e6; padding: 8px 4px; }
        .lx-tree details { margin: 0; }
        .lx-node { margin: 4px 0; padding-left: 4px; }
        .lx-children { margin-left: 14px; padding-left: 12px;
                       border-left: 2px solid #3a3f4b; margin-top: 4px; }
        .lx-summary { cursor: pointer; padding: 6px 10px; border-radius: 8px;
                      display: flex; align-items: center; gap: 8px;
                      transition: background 0.15s ease; list-style: none; }
        .lx-summary::-webkit-details-marker { display: none; }
        .lx-summary:hover { background: rgba(255,140,60,0.10); }
        .lx-leaf-summary { cursor: default; }
        .lx-leaf-summary:hover { background: rgba(255,255,255,0.04); }
        .lx-name { font-weight: 600; font-size: 0.92rem; color: #f5f5f5; }
        .lx-count { margin-left: auto; background: #ff7a33; color: #1a1a1a;
                    font-size: 0.7rem; font-weight: 700; padding: 1px 8px;
                    border-radius: 999px; }
        .lx-bullet { color: #ff7a33; font-weight: 700; }
        .lx-desc { font-size: 0.82rem; color: #a8b0bd; margin: 2px 0 4px 28px;
                   line-height: 1.45; }
        details > .lx-summary .lx-name::before { content: '▸ '; color: #ff7a33;
                   font-size: 0.75rem; transition: transform 0.15s; }
        details[open] > .lx-summary .lx-name::before { content: '▾ '; }
        </style>
        """
        return f'{style}<div class="lx-tree">{node_html}</div>'

    return node_html


EMPTY_MINDMAP_HTML = (
    '<div style="color:#888; font-style:italic; padding:20px; '
    'font-family:Inter,sans-serif;">Upload a document to see its '
    'structure mapped here.</div>'
)


def run_ingestion_agent(file_path: str, api_key: str) -> str:
    """
    Agent 1: Ingestion (Docling / Gemini Multimodal)
    Uses IBM Docling for PDFs, DOCX, and images.
    Falls back to Gemini for audio, unsupported files, or if Docling crashes.
    """
    ext = os.path.splitext(file_path)[1].lower()

    # Handle audio files via Gemini
    if ext in ['.wav', '.mp3', '.m4a']:
        client = get_client(api_key)
        uploaded_file = client.files.upload(file=file_path)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=["You are a transcription agent. Transcribe this audio file accurately and extract any legal context.", uploaded_file]
        )
        return response.text

    # Try Documents via IBM Docling
    try:
        converter = DocumentConverter()
        result = converter.convert(file_path)
        return result.document.export_to_markdown()
    except Exception as e:
        print(f"Docling error encountered: {e}. Initiating Gemini Fallback...")
        # FALLBACK: Let Gemini Multimodal read the document natively
        try:
            client = get_client(api_key)
            uploaded_file = client.files.upload(file=file_path)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=["You are an expert document parser. Read this document and extract its full text and structure precisely into Markdown format.", uploaded_file]
            )
            return response.text
        except Exception as gemini_e:
            return f"EXTRACTION_FAILED: Both Docling and Gemini failed to parse the document.\n\nDocling: {str(e)}\nGemini: {str(gemini_e)}"


def _clean_json(raw: str) -> str:
    """Strip markdown code fences from a JSON response, however the model wraps them."""
    raw = raw.strip()
    # Remove ```json ... ``` or ``` ... ``` or just leading/trailing backticks
    if raw.startswith("```"):
        # Split on the opening fence, take everything after it
        parts = raw.split("```", 2)
        raw = parts[1] if len(parts) >= 2 else raw
        # Remove optional language tag (e.g. "json\n")
        if raw.startswith("json"):
            raw = raw[4:]
        # Remove closing fence if present
        if raw.endswith("```"):
            raw = raw[:-3]
    return raw.strip()


def run_analysis_agent(extracted_text: str, api_key: str) -> dict:
    """
    Agent 2: Analysis — two separate calls to avoid JSON parse failures.

    Call A: free-form markdown summary (no JSON, so no escaping issues).
    Call B: mindmap-only JSON on a shorter excerpt (small payload = reliable parse).
    """
    if "EXTRACTION_FAILED" in extracted_text or "DOCLING_EXTRACTION_ERROR" in extracted_text:
        return {
            "summary": "### Extraction Failed\n" + extracted_text,
            "mindmap": {"name": "Error", "description": "Failed to parse document", "children": []}
        }

    client = get_client(api_key)
    # Use first 30k chars for summary, first 15k for mindmap (structure is in the front matter)
    text_for_summary = extracted_text[:30000]
    text_for_mindmap = extracted_text[:15000]

    # ── Call A: Summary (plain markdown, zero JSON risk) ──────────────────────
    summary_prompt = f"""You are a legal analysis agent. Read the document excerpt below and write a comprehensive legal summary in markdown.

Structure your response with these sections:
## Title
## Parties
## Key Obligations
## Rights & Entitlements
## Risks & Liabilities
## Important Dates / Deadlines

Be thorough. Use bullet points within each section. Do NOT output JSON.

Document:
{text_for_summary}"""

    try:
        summary_resp = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=summary_prompt,
            config=types.GenerateContentConfig(temperature=0.1)
        )
        summary = summary_resp.text.strip()
    except Exception as e:
        summary = f"### Summary Generation Failed\n\nError: {str(e)}"

    # ── Call B: Mindmap JSON only (small, tight schema, short excerpt) ─────────
    mindmap_prompt = f"""You are a document structure agent. Analyse the document excerpt and output ONLY a JSON object — no markdown fences, no explanation, no preamble.

The JSON must follow this exact schema (max 3 levels deep, max 6 children per node, descriptions ≤ 15 words):
{{
  "name": "Short document title",
  "description": "One sentence overview",
  "children": [
    {{
      "name": "Section heading",
      "description": "What this section covers",
      "children": [
        {{"name": "Sub-section", "description": "Brief note", "children": []}}
      ]
    }}
  ]
}}

Document excerpt:
{text_for_mindmap}"""

    default_mindmap = {"name": "Document", "description": "Structure unavailable", "children": []}
    try:
        mindmap_resp = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=mindmap_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0   # zero temp for structural output = more deterministic JSON
            )
        )
        raw = _clean_json(mindmap_resp.text)
        mindmap = json.loads(raw)
    except json.JSONDecodeError as e:
        # Surface the raw response so it's diagnosable, but don't crash the whole pipeline
        print(f"[Mindmap JSON parse error] {e}\nRaw response: {mindmap_resp.text[:500]}")
        mindmap = default_mindmap
    except Exception as e:
        print(f"[Mindmap generation error] {e}")
        mindmap = default_mindmap

    return {"summary": summary, "mindmap": mindmap}


def run_guardrail_agent(query: str, api_key: str) -> dict:
    """Agent 3: Guardrail. Validates if the user query is ethical/relevant."""
    client = get_client(api_key)
    prompt = f"""
Analyze this user query: "{query}".
Does this query ask for illegal advice, physical harm, or violate ethical guidelines?
Respond strictly in JSON: {{"isSafe": true/false, "reason": "brief explanation"}}
"""
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0)
    )
    try:
        return json.loads(response.text)
    except Exception:
        return {"isSafe": True, "reason": "Fallback allowed"}


def run_counsel_agent(query: str, context_docs: list, api_key: str) -> str:
    """Agent 4: Counsel. Drafts the legal response with strict citation instructions."""
    client = get_client(api_key)
    context_str = "\n\n".join([f"--- DOCUMENT: {d['name']} ---\n{d['text'][:30000]}" for d in context_docs])

    prompt = f"""User Query: {query}

Context Documents:
{context_str}

Answer the query based ONLY on the provided context.
CRITICAL RULE: You MUST cite your sources directly in the text using the format [Document Name].
If you cannot find the answer in the context, explicitly state "I cannot find this information in the provided documents."
Draft your response in professional legal markdown."""

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2)
    )
    return response.text


def run_validation_agent(draft: str, context_docs: list, api_key: str) -> str:
    """Agent 5: Validation (QA). Checks the draft for hallucinations against source text."""
    client = get_client(api_key)
    context_str = "\n\n".join([f"--- DOCUMENT: {d['name']} ---\n{d['text'][:20000]}" for d in context_docs])

    prompt = f"""Context Documents:
{context_str}

Draft Response:
{draft}

Task: Verify the Draft Response against the Context.
1. Are all claims supported by the context?
2. Are the citations accurate?
If valid, return the draft as is. If hallucinated or unverified, rewrite the draft to remove false claims and append a note about the correction.
Return ONLY the finalized markdown response."""

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1)
    )
    return response.text


def handle_file_upload(files, api_key, current_state):
    """Processes newly uploaded files through the Ingestion and Analysis agents."""
    if not files:
        yield current_state, "No files uploaded.", gr.update(), gr.update()
        return

    if not api_key:
        yield current_state, "⚠️ Please provide your Gemini API Key first.", gr.update(), gr.update()
        return

    new_state = list(current_state) if current_state else []
    status_msg = "Processing started...\n"

    for file in files:
        file_path = _resolve_path(file)
        file_name = os.path.basename(file_path)

        status_msg += f"📄 {file_name}: Ingesting via Docling...\n"
        yield new_state, status_msg, gr.update(), gr.update()

        # 1. Ingestion
        try:
            extracted_text = run_ingestion_agent(file_path, api_key)
        except Exception as e:
            status_msg += f"❌ {file_name}: Ingestion failed — {e}\n\n"
            yield new_state, status_msg, gr.update(), gr.update()
            continue

        status_msg += f"🧠 {file_name}: Analyzing structure...\n"
        yield new_state, status_msg, gr.update(), gr.update()

        # 2. Analysis
        analysis_data = run_analysis_agent(extracted_text, api_key)

        new_doc = {
            "name": file_name,
            "text": extracted_text,
            "summary": analysis_data.get("summary", "No summary available."),
            "mindmap": analysis_data.get("mindmap", {"name": file_name, "children": []})
        }
        new_state.append(new_doc)
        status_msg += f"✅ {file_name}: Ready!\n\n"

        yield new_state, status_msg, new_doc["summary"], render_mindmap_html(new_doc["mindmap"])


def handle_chat(text_query, audio_query, chat_history, api_key, document_state):
    """Orchestrates the user query through the multi-agent conversation workflow."""
    query = text_query
    chat_history = list(chat_history) if chat_history else []

    if audio_query:
        chat_history.append({"role": "user", "content": "*(Audio message)*"})
        yield chat_history, "", None

        try:
            chat_history.append({"role": "assistant", "content": "🎙️ *Transcribing audio via Gemini...*"})
            yield chat_history, "", None
            query = run_ingestion_agent(_resolve_path(audio_query), api_key)
            chat_history[-2]["content"] = f"🎙️ Audio Transcript: {query}"
            chat_history.pop()  # Remove the transcription status message
            yield chat_history, "", None
        except Exception as e:
            chat_history[-1]["content"] = f"❌ Audio Error: {str(e)}"
            yield chat_history, "", None
            return
    elif query:
        chat_history.append({"role": "user", "content": query})
    else:
        yield chat_history, "", None
        return

    if not api_key:
        chat_history.append({"role": "assistant", "content": "⚠️ Please provide your Gemini API Key."})
        yield chat_history, "", None
        return

    if not document_state:
        chat_history.append({"role": "assistant", "content": "⚠️ Please upload at least one document first so I have context."})
        yield chat_history, "", None
        return

    try:
        # 3. Guardrail Agent
        chat_history.append({"role": "assistant", "content": "🛡️ *Guardrail Agent: Checking compliance...*"})
        yield chat_history, "", None

        guardrail = run_guardrail_agent(query, api_key)
        if not guardrail.get("isSafe", True):
            chat_history[-1]["content"] = f"🛑 **Blocked by Guardrails:** {guardrail.get('reason')}"
            yield chat_history, "", None
            return

        # 4. Counsel Agent
        chat_history[-1]["content"] = "⚖️ *Counsel Agent: Drafting legal response with citations...*"
        yield chat_history, "", None

        draft = run_counsel_agent(query, document_state, api_key)

        # 5. Validation Agent
        chat_history[-1]["content"] = "🔍 *Validation Agent: Checking draft against source context...*"
        yield chat_history, "", None

        final_response = run_validation_agent(draft, document_state, api_key)

        chat_history[-1]["content"] = final_response
        yield chat_history, "", None

    except Exception as e:
        chat_history[-1]["content"] = f"❌ **System Error:** {str(e)}"
        yield chat_history, "", None


custom_css = """
.gradio-container { font-family: 'Inter', sans-serif; }
.mindmap-json { max-height: 500px; overflow-y: auto; }
"""

with gr.Blocks(title="LexiNotebook - Law Firm AI", css=custom_css) as demo:
    document_state = gr.State([])

    gr.Markdown("""
    # ⚖️ LexiNotebook Multi-Agent Legal AI
    **Powered by IBM Docling & Gemini (2.5-flash API)**
    Upload legal documents or dictations. The multi-agent system will ingest (OCR), analyze, structure, and answer questions with citations.
    """)

    api_key_input = gr.Textbox(label="Google Gemini API Key", type="password", placeholder="Enter your api key here (AIza...)")

    with gr.Row():
        with gr.Column(scale=1):
            file_upload = gr.File(label="Upload Source Documents", file_count="multiple", file_types=[".pdf", ".docx", ".png", ".jpg"])
            upload_status = gr.Textbox(label="Agent Pipeline Status", interactive=False, lines=10)
            audio_query = gr.Audio(label="Or dictate your question", type="filepath")

        with gr.Column(scale=2):
            with gr.Tabs():
                with gr.Tab("💬 Interactive Chat"):
                    chatbot = gr.Chatbot(
                        label="Lexi AI Counsel",
                        type="messages",
                        height=550,
                        avatar_images=(None, "https://api.dicebear.com/7.x/bottts/svg?seed=lexi"),
                    )
                    text_query = gr.Textbox(label="Ask a question about the documents...", placeholder="E.g., What are the main liabilities listed in the contract?")
                    submit_btn = gr.Button("Send to Agents", variant="primary")

                with gr.Tab("📄 Document Summaries"):
                    summary_view = gr.Markdown("*Upload a document to see its AI-generated summary here.*")

                with gr.Tab("🧠 Interactive Mindmap"):
                    gr.Markdown("Explore the hierarchical structure of your document automatically extracted by the Analysis Agent.")
                    mindmap_view = gr.HTML(value=EMPTY_MINDMAP_HTML, elem_classes="mindmap-json")

    # Use .change instead of .upload — more reliable in Gradio 5
    file_upload.change(
        fn=handle_file_upload,
        inputs=[file_upload, api_key_input, document_state],
        outputs=[document_state, upload_status, summary_view, mindmap_view]
    )

    submit_events = [submit_btn.click, text_query.submit]
    for event in submit_events:
        event(
            fn=handle_chat,
            inputs=[text_query, audio_query, chatbot, api_key_input, document_state],
            outputs=[chatbot, text_query, audio_query]
        )

if __name__ == "__main__":
    demo.launch(debug=False, share=False)
