# TaxClaw — Privacy Policy

**Last updated:** October 20, 2026  
**Effective date:** February 22, 2026  
**Publisher:** Outbranch Network LLC, a New York limited liability company  
**Contact:** lando@outbranch.net

---

## Overview

TaxClaw is designed as a **local-first tool**. Your tax documents and extracted data are processed and stored on your device by default and are not transmitted to Outbranch Network LLC or any third party unless you explicitly enable Cloud Mode.

We do not require accounts. We do not collect analytics. We do not sell your data.

---

## 1. Local Mode (Default)

When you use TaxClaw in **Local Mode** (powered by Ollama running on your device):

**What stays on your machine — always:**
- Your uploaded tax documents (PDFs and images)
- All extracted field values (W-2 boxes, 1099 amounts, K-1 fields, etc.)
- Your TaxClaw database (SQLite, stored in your configured data directory)
- All export files (CSV, JSON) you generate

**What is NEVER transmitted in Local Mode:**
- The contents of your tax documents
- Extracted field values
- Personally identifiable information from your documents (names, SSNs, EINs, account numbers, dollar amounts)
- Metadata about your documents
- Your IP address or device identifier (TaxClaw has no telemetry, no analytics, no phone-home)

**AI processing in Local Mode:**  
All AI extraction is performed by Ollama, running entirely on your local machine. No document data leaves your device during extraction. (If you point `OLLAMA_HOST` at another computer, page images go to that Ollama server instead; the default is `127.0.0.1:11434`.)

**Export files:** CSV, JSON, Form 8949 CSV and TXF exports contain the same sensitive data as your documents. Save them somewhere private and delete them when you no longer need them; files in synced folders (iCloud, Dropbox, Google Drive) leave your machine.

**No accounts required:**  
TaxClaw does not require user accounts, email addresses, or registration of any kind. We maintain no user database.

---

## 2. Cloud Mode (Optional — Requires Explicit Consent)

"Cloud Mode" means choosing any extraction backend other than `local` in TaxClaw Settings or `config.yaml` (`anthropic`, `openai_compat` or `cloudflare_clairic`). In Cloud Mode, **complete pages of your tax documents** are sent to the third-party AI provider you chose, directly from your machine through that provider's API.

**Before enabling Cloud Mode, you must:**
- Affirmatively acknowledge the Cloud Mode privacy notice in TaxClaw Settings (or set `privacy_acknowledged: true` in `config.yaml`)
- Confirm you understand that document data will leave your device

Every cloud backend checks this acknowledgment itself before sending anything, whether you use the web UI, the CLI or the MCP server.

**What leaves your device when Cloud Mode is enabled:**
- A full rendered image (PNG) of each page TaxClaw reads: the classification pass sends page 1 when the PDF's text doesn't identify the form, and the extraction passes send the pages they read (normally every page). Everything printed on those pages goes with them, including names, SSNs/TINs, EINs, account numbers and dollar amounts.
- The extraction instructions (prompt and field schema). For the Cloudflare Clairic backend, the PDF's text layer for each page is sent as well.
- Sent to the provider you selected, and only that provider:
  - **Anthropic, Inc.** (`anthropic` backend): `api.anthropic.com`
  - **OpenAI** (`api.openai.com`), **OpenRouter** (`openrouter.ai`), **Google Gemini** (`generativelanguage.googleapis.com`) or a custom OpenAI-compatible URL you enter (`openai_compat` backend)
  - **Cloudflare Workers AI** (`api.cloudflare.com`, `cloudflare_clairic` backend). Document types the Clairic adapter doesn't cover go to the backend you set as `clairic_fallback_backend` (local by default).
- Purpose: AI-powered field extraction from your documents

**Model lists (no document data):** `taxclaw models` and the Settings page ask a cloud provider for its list of available models only when that provider's API key is already set in your environment. That request carries the key, never document data. `taxclaw models --offline` makes no network calls.

**What Outbranch Network LLC does NOT do with Cloud Mode data:**
- We do not log, store, or retain your document data on our servers
- We do not receive your raw document files — requests go from your local TaxClaw instance straight to the provider you chose
- We do not sell, share, or analyze your document content

**Third-party privacy policies:**  
Each provider's handling of API inputs is governed by its own policy, for example:  
Anthropic: https://www.anthropic.com/privacy  
OpenAI: https://openai.com/policies/privacy-policy  
OpenRouter: https://openrouter.ai/privacy  
Google: https://policies.google.com/privacy  
Cloudflare: https://www.cloudflare.com/privacypolicy/

**Recommendation:** For maximum privacy, use Local Mode (Ollama). Local Mode processes everything on your device and transmits nothing.

---

## 3. No Analytics, No Telemetry

TaxClaw does **not** collect:
- Usage analytics or telemetry
- Crash reports (unless you manually share logs with us)
- Performance metrics
- Feature usage data
- Device identifiers or fingerprints
- IP addresses

There is no tracking of any kind built into TaxClaw.

**Optional contact form:** The in-app Contact page is the only feature that sends anything to us. Don't type SSNs, account numbers or other tax details into it. If — and only if — you submit it, the name, email address, subject and message you type are sent to Formspree (formspree.io), a form-forwarding service, which delivers them to Outbranch Network LLC by email. The form never attaches your documents or extracted tax data. Formspree's handling of submissions is governed by its privacy policy: https://formspree.io/legal/privacy-policy

---

## 4. Affiliate Links

TaxClaw's export flow may include links to third-party tax reconciliation services (such as Koinly, CoinTracker, or ZenLedger). These are **affiliate links** — Outbranch Network may earn a referral commission if you sign up through these links at no additional cost to you.

Clicking affiliate links may transmit referral data (such as a referral code or click identifier) to those third-party services. Their privacy policies govern what data they collect. We recommend reviewing each service's privacy policy before signing up.

Affiliate links are clearly disclosed wherever they appear in TaxClaw's interface.

---

## 5. Your Controls

**Delete all data:**  
You can delete any document from TaxClaw using the Delete button on the document detail page. This removes the document record from the database and deletes the stored file from your data directory.

**Export your data:**  
You can export all your extracted data at any time using the Export functions on the Documents list page or individual document pages (CSV or JSON format).

**Wipe everything:**  
To completely remove TaxClaw data, delete your TaxClaw data directory (configured in Settings or config.yaml) and uninstall the application.

**No deletion requests needed:**  
Because TaxClaw stores your data locally on your device, you control deletion entirely yourself. There is no server-side data to request deletion of (in Local Mode).

---

## 6. Children's Privacy

TaxClaw is not directed at children under 13 and is intended for use by adults managing their own tax documents. We do not knowingly collect information from anyone under 13.

---

## 7. Changes to This Policy

If we make material changes to this Privacy Policy (for example, if a future version of TaxClaw adds server-side features), we will update the "Last updated" date above and post the updated policy within the TaxClaw application and on the GitHub repository. We will provide prominent notice for any changes that materially affect how your data is handled.

---

## 8. Contact

For privacy questions or concerns:

**Outbranch Network LLC**  
Email: lando@outbranch.net  
GitHub: https://github.com/DougButdorf/TaxClaw

We will respond to privacy inquiries within a reasonable time.

---

*This Privacy Policy was last reviewed and updated: October 20, 2026.*
