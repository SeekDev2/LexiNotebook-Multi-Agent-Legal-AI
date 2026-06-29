LexiNotebook - Law Firm AI
Created by: Abdul Samad
LexiNotebook is a Multi-Agent Legal AI application tailored for law firms, powered by IBM Docling and Google's Gemini API. It allows legal professionals to upload documents (PDF, DOCX, PNG, JPG) or dictate audio queries. The built-in multi-agent system autonomously ingests documents using OCR, analyzes their structure, generates interactive mindmaps, and answers legal questions with strict source citations.
Features
Multi-Agent Architecture: Includes dedicated agents for Ingestion, Analysis, Guardrails (safety checks), Counsel (drafting), and Validation (preventing hallucinations).
Robust Document Parsing: Uses IBM Docling for high-fidelity structural extraction, with a self-healing fallback to Gemini Multimodal if local OCR dependencies fail.
Multimodal Chat: Supports both text queries and voice dictations.
Interactive Mindmaps: Extracts and visualizes document clauses and hierarchies as an interactive HTML tree.
Source-Grounded: Answers are strictly validated against uploaded documents, complete with citations.
Installation
Ensure you have Python 3.9+ installed.
Install the required dependencies using the provided requirements.txt:
pip install -r requirements.txt


Usage
Run the application from your terminal:
python app.py


Open the provided localhost or .gradio.live link in your web browser.
Enter your Google Gemini API Key.
Upload your legal documents and start chatting or interacting with the generated mindmaps and summaries.
Note for Google Colab Users
If you are running this application in Google Colab or a Jupyter Notebook, the application is configured to run with debug=False and share=True to prevent event loop conflicts during file uploads.
