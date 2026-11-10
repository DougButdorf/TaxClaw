# TaxClaw — Privacy Policy

**Last updated:** 2026-11-10  
**Effective date:** 2026-11-11  
**Publisher:** Outbranch Network LLC, a New York limited liability company  
**Contact:** lando@outbranch.net  
**Applies to:** the open-source TaxClaw tool (CLI, web UI, local MCP server and OpenClaw skill) at https://github.com/DougButdorf/TaxClaw

---

## Overview

TaxClaw is a **local-first tool**. Your tax documents and extracted data are processed and stored on your device. In local mode nothing leaves your machine. Document data is transmitted to a third party only if you explicitly choose a cloud backend and record your privacy acknowledgement.

We do not require accounts. We do not collect analytics. We do not sell your data. Outbranch Network LLC never receives your documents or extracted values through the open-source tool.

> **TaxClaw Cloud is a separate, hosted service** at `https://mcp.taxclaw.net/mcp`, with its own Privacy Policy at https://mcp.taxclaw.net/privacy and Terms of Service at https://mcp.taxclaw.net/terms. If your agent sends documents to TaxClaw Cloud, that policy applies, not this one. This policy covers only the tool that runs on your own machine.

---

## 1. Local mode (default)

When you use TaxClaw in **local mode** (powered by Ollama running on your device; the default model is `gemma3:4b`):

**What stays on your machine, always:**

- your uploaded tax documents (PDFs and images);
- all extracted field values (W-2 boxes, 1099 amounts, K-1 fields and so on);
- your TaxClaw database (SQLite, stored in your configured data directory, by default `~/.local/share/taxclaw/`);
- all export files (JSON, wide CSV, long CSV, Form 8949 CSV, TXF) you generate.

**What is NEVER transmitted in local mode:**

- the contents of your tax documents;
- extracted field values;
- personally identifiable information from your documents (names, SSNs, EINs, account numbers, dollar amounts);
- metadata about your documents;
- your IP address or device identifier (TaxClaw has no telemetry, no analytics and no phone-home).

**AI processing in local mode.** All AI extraction is performed by Ollama, running on your local machine. No document data leaves your device during extraction. If you point `OLLAMA_HOST` at another computer, page images go to that Ollama server instead; the default is `127.0.0.1:11434`.

**Export files.** Exports contain the same sensitive data as your documents. Save them somewhere private and delete them when you no longer need them; files in synced folders (iCloud, Dropbox, Google Drive) leave your machine.

**No accounts required.** TaxClaw does not require user accounts, email addresses or registration of any kind. We maintain no user database.

---

## 2. Cloud backends (optional, requires explicit acknowledgement)

A cloud backend means choosing any extraction backend other than `local` in TaxClaw Settings or `config.yaml`: `anthropic`, `openai_compat` or `cloudflare_clairic`. With a cloud backend, **complete pages of your tax documents** are sent to the one third-party AI provider you chose, directly from your machine through that provider's API.

**Before a cloud backend will run, you must** affirmatively acknowledge the privacy notice in TaxClaw Settings, with `taxclaw use-cloud <provider> --accept-privacy`, or by setting `privacy_acknowledged: true` in `config.yaml`. TaxClaw records the time and the provider name in your config; switching back to local clears the record. Every cloud backend checks this acknowledgement itself before sending anything, whether you use the web UI, the CLI or the MCP server. The MCP server has no tool that can give this acknowledgement for you; an agent cannot switch you to a cloud backend.

**What leaves your device with a cloud backend:**

- a full rendered image (PNG) of each page TaxClaw reads: the classification pass sends page 1 when the PDF's text does not identify the form, and the extraction passes send the pages they read (normally every page). Everything printed on those pages goes with them, including names, SSNs and TINs, EINs, account numbers and dollar amounts;
- the extraction instructions (prompt and field schema). For the Cloudflare Clairic backend, the PDF's text layer for each page is sent as well.

**Sent to the provider you selected, and only that provider:**

- **Anthropic** (`anthropic` backend): `api.anthropic.com`
- **OpenAI** (`api.openai.com`), **OpenRouter** (`openrouter.ai`), **Google Gemini** (`generativelanguage.googleapis.com`) or a custom OpenAI-compatible URL you enter (`openai_compat` backend)
- **Cloudflare Workers AI** (`api.cloudflare.com`, `cloudflare_clairic` backend). Document types the Clairic adapter does not cover go to the backend you set as `clairic_fallback_backend` (local by default).

**Model lists (no document data).** `taxclaw models` and the Settings page ask a cloud provider for its list of available models only when that provider's API key is already set in your environment. That request carries the key, never document data. `taxclaw models --offline` makes no network calls.

**What Outbranch Network LLC does NOT do with cloud-backend data:**

- we do not receive your documents or extracted values; requests go from your local TaxClaw instance straight to the provider you chose;
- we do not log, store or retain any of it on any server of ours;
- we do not sell, share or analyze your document content.

**Third-party privacy policies.** Each provider's handling of API inputs, including retention and training, is governed by its own API terms, not by us:  
Anthropic: https://www.anthropic.com/privacy  
OpenAI: https://openai.com/policies/privacy-policy  
OpenRouter: https://openrouter.ai/privacy  
Google: https://policies.google.com/privacy  
Cloudflare: https://www.cloudflare.com/privacypolicy/

**Recommendation.** For maximum privacy, use local mode. It processes everything on your device and transmits nothing.

---

## 3. Agents and the local MCP server

TaxClaw exposes a local MCP server and an OpenClaw skill so that an AI agent can run it for you. The local MCP tools are `ingest_document`, `list_documents`, `get_document`, `export_documents`, `list_models`, `setup_status` and, from release 1.1.0, `delete_document`.

**Extracted values returned to an agent go wherever that agent's model runs.** If your agent's model is hosted by a third party (for example a cloud assistant), the values TaxClaw returns to it leave your machine through the agent, under that provider's terms. TaxClaw itself still sends nothing; the agent does. Choose your agent with that in mind, and read its provider's privacy terms.

**Identifier masking on MCP output (release 1.1.0 and later).** The `get_document`, `list_documents` and `export_documents` MCP tools mask Social Security numbers, TINs, EINs and account numbers to their last four characters by default (`redact_identifiers`), so that full identifiers do not reach the agent's model unless the caller passes `redact_identifiers: false`. CLI exports and the web UI are not masked. Masking is a convenience, not a guarantee: it applies to fields TaxClaw recognizes as identifiers and can miss one.

---

## 4. No analytics, no telemetry

TaxClaw does **not** collect usage analytics or telemetry, crash reports (unless you manually share logs with us), performance metrics, feature-usage data, device identifiers or fingerprints, or IP addresses. There is no tracking of any kind built into TaxClaw.

**Optional contact form.** The Contact page in the web UI is the only feature that sends anything to us. Do not type SSNs, account numbers or other tax details into it. If, and only if, you press Send, the request type, name, email address, subject and message you typed are sent to Formspree (formspree.io), a form-forwarding service, which delivers them to Outbranch Network LLC by email. The form never attaches your documents or extracted tax data. Formspree's handling of submissions is governed by its privacy policy: https://formspree.io/legal/privacy-policy. We keep what you send us as ordinary business correspondence. You can also email lando@outbranch.net directly.

---

## 5. Affiliate link

The "Crypto tools" page in the web UI links to Koinly, a third-party cost-basis reconciliation service. Those links are **referral (affiliate) links**: Outbranch Network LLC may earn a commission if you sign up for a paid Koinly plan through them, at no additional cost to you. The page says so where the links appear. Clicking a referral link sends a referral code to Koinly; Koinly's privacy policy governs what it collects from there. TaxClaw never sends your documents or extracted data to Koinly; any export you upload to Koinly is your own action. The referral relationship does not affect how TaxClaw extracts your data.

---

## 6. Your controls

**Delete a document.** Use the Delete button on a document's detail page, or, from release 1.1.0, the `delete_document` MCP tool. This removes the document record from the database and deletes the stored file from your data directory.

**Export your data.** Use the Export functions on the Documents list page or individual document pages, or the `export_documents` MCP tool.

**Wipe everything.** Delete your TaxClaw data directory (shown in Settings or `config.yaml`) and uninstall the application.

**No deletion requests needed.** Because TaxClaw stores your data on your device, you control deletion entirely yourself. There is no server-side data at Outbranch Network LLC to request deletion of. For data you chose to send to a cloud provider, or that your agent sent to its own model provider, contact that provider.

---

## 7. Children

TaxClaw is for adults. You must be at least 18 years old to use it, and it is not directed at anyone under 18. We do not knowingly collect information from anyone under 18.

---

## 8. Changes to this policy

If we make material changes to this policy (for example, if a future release adds a feature that sends data anywhere), we will update the "Last updated" date above and post the updated policy in the GitHub repository and in the web UI's Privacy page. We will call out any change that materially affects how your data is handled in the release notes.

---

## 9. Contact

For privacy questions or concerns:

**Outbranch Network LLC**  
Email: lando@outbranch.net  
GitHub: https://github.com/DougButdorf/TaxClaw

We will respond to privacy inquiries within a reasonable time.
