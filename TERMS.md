# TaxClaw — Terms of Use

**Last updated:** 2026-11-10  
**Effective date:** 2026-11-11  
**Publisher:** Outbranch Network LLC, a New York limited liability company  
**Contact:** lando@outbranch.net  
**Applies to:** the open-source TaxClaw tool (CLI, web UI, local MCP server and OpenClaw skill) at https://github.com/DougButdorf/TaxClaw

---

> **IMPORTANT:** These Terms of Use are a binding agreement between you and Outbranch Network LLC. By downloading, installing or using TaxClaw, or by letting an AI agent use it on your behalf, you agree to these Terms. If you do not agree, do not use TaxClaw.

> **TaxClaw Cloud is a separate, hosted service** at `https://mcp.taxclaw.net/mcp`. It has its own Terms of Service at https://mcp.taxclaw.net/terms and its own Privacy Policy at https://mcp.taxclaw.net/privacy. These Terms of Use cover only the open-source tool that runs on your own machine.

---

## 1. What TaxClaw is, and is not

**TaxClaw is a data extraction tool.**

TaxClaw reads fields printed on your tax documents (W-2, 1099 variants, Schedule K-1, consolidated brokerage 1099 statements and similar forms, with Form 1040 on a best-effort basis) and organizes that data into a structured local database for your review and export (JSON, wide CSV, long CSV, Form 8949 CSV and TXF).

**TaxClaw is NOT:**

- a tax preparation service;
- a tax return review or filing service, or an IRS-authorized e-file provider;
- a source of tax, legal, accounting or financial advice;
- a CPA firm, law firm, enrolled agent service or credentialed tax service of any kind.

**TaxClaw does NOT:**

- prepare, review or file tax returns on your behalf;
- interpret tax items or tell you how to treat any item on your return;
- place amounts on return lines or compute tax liability;
- compute cost basis;
- verify the accuracy of data printed on your source documents;
- guarantee that extracted values are correct, complete or usable for any purpose.

Outbranch Network LLC is not a CPA firm, a law firm, an enrolled agent, a tax return preparer or a fiduciary. Use of TaxClaw does not create any professional, fiduciary, advisory, accountant-client, preparer-client or attorney-client relationship between you and Outbranch Network LLC.

**For tax advice, consult a qualified tax professional:** a CPA, an Enrolled Agent or a licensed tax attorney.

Nothing produced by TaxClaw is intended or written to be used, and cannot be used, by any taxpayer for the purpose of avoiding penalties that may be imposed under the Internal Revenue Code or any state or local tax law.

---

## 2. AI accuracy: your responsibility

TaxClaw uses artificial intelligence (AI) vision models to extract data fields from tax documents. **AI extraction is imperfect and may produce errors, omissions, transpositions or misreadings of your source documents.** Confidence values and review flags are aids for your review, not guarantees: a value can be wrong without being flagged, and a flagged value can be right.

**YOU ARE SOLELY RESPONSIBLE FOR:**

- verifying every extracted value against your original source documents before using that data for any purpose, including every row of any Form 8949 CSV or TXF export;
- the accuracy of any tax return you file with the IRS or any state taxing authority;
- any tax, penalty, interest or professional costs resulting from errors in data you relied upon;
- determining whether extracted data is suitable for your intended use.

The published benchmark (see "Measured accuracy" in the CHANGELOG at https://github.com/DougButdorf/TaxClaw/blob/main/CHANGELOG.md) is measured on invented documents under test conditions. It is not a measurement of accuracy on your documents and not a promise about them.

Outbranch Network LLC makes **no representation or warranty, express or implied**, regarding the accuracy, completeness or fitness for any particular purpose of data extracted by TaxClaw.

---

## 3. Your agent acts for you

TaxClaw can be used by an AI agent through its local MCP server or the OpenClaw skill. When an agent uses TaxClaw on your behalf, its actions are your actions, and its acceptance of these Terms is your acceptance. Extracted values that TaxClaw returns to an agent go wherever that agent's model runs; if the agent's model is hosted by a third party, that third party's terms govern what happens to the values there. You are responsible for the agent you connect and for where it sends your data.

---

## 4. Your machine, your data, your choices

TaxClaw runs on your own machine. In local mode (the default, using Ollama on your device) no document data leaves your machine. If you choose a cloud backend, full page images of your documents are sent to the one AI provider you selected, only after you record your privacy acknowledgement. You are responsible for that choice and for the provider's terms. See the Privacy Policy at https://github.com/DougButdorf/TaxClaw/blob/main/PRIVACY.md for exactly what goes where.

The `redact_identifiers` option on the MCP tools masks identifiers in tool output as a convenience. It can miss an identifier, and we make no warranty that any identifier was masked.

You must be at least 18 years old to use TaxClaw.

---

## 5. Prohibited uses

You may not use TaxClaw to:

1. process tax documents belonging to other people without their permission, or any document that is forged, stolen or otherwise unlawful to possess or process;
2. provide tax preparation services to third parties for compensation using TaxClaw output as the primary data source, without independently verifying all extracted values;
3. use TaxClaw in violation of any applicable law, including tax law, data-protection law and sanctions law;
4. transmit malicious content through TaxClaw's upload or contact functionality;
5. misrepresent TaxClaw as a licensed tax preparation, review or filing service to any third party, or describe any output as "TaxClaw-certified" or verified by TaxClaw;
6. remove, obscure or alter any disclaimer, copyright notice or legal notice in TaxClaw's interface or output files, except as the MIT License permits when you redistribute modified source code under your own name.

---

## 6. License

TaxClaw is free, open-source software released under the MIT License. The MIT License text is in the LICENSE file in the repository at https://github.com/DougButdorf/TaxClaw/blob/main/LICENSE. There is no paid tier of the open-source tool and no proprietary component in it.

**The MIT License and these Terms work together.** The MIT License governs copying, modifying and redistributing the source code, and nothing in these Terms limits your rights under it. These Terms govern your use of TaxClaw as a running application, including the disclaimers and limitations in sections 1, 2, 7 and 8. If you redistribute TaxClaw, the MIT License requires you to keep its copyright and permission notice; you may not use the TaxClaw name or logo to imply that Outbranch Network LLC endorses your version.

---

## 7. No warranty: "as is"

TAXCLAW IS PROVIDED **"AS IS"** AND **"AS AVAILABLE"** WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. OUTBRANCH NETWORK LLC EXPRESSLY DISCLAIMS ALL WARRANTIES, INCLUDING BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE (INCLUDING FITNESS FOR PREPARING OR FILING ANY TAX RETURN), NON-INFRINGEMENT, ACCURACY OR COMPLETENESS OF EXTRACTED DATA, UNINTERRUPTED OR ERROR-FREE OPERATION, AND COMPATIBILITY WITH YOUR OPERATING SYSTEM, HARDWARE, MODELS OR AGENT. YOU USE TAXCLAW ENTIRELY AT YOUR OWN RISK. Some jurisdictions do not allow the exclusion of implied warranties, so some of the above exclusions may not apply to you.

---

## 8. Limitation of liability

**TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW:**

IN NO EVENT SHALL OUTBRANCH NETWORK LLC, ITS MEMBERS, OFFICERS, EMPLOYEES, CONTRACTORS OR AFFILIATES BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY OR PUNITIVE DAMAGES ARISING FROM YOUR USE OF TAXCLAW OR RELIANCE ON ANY DATA EXTRACTED BY TAXCLAW, INCLUDING BUT NOT LIMITED TO:

- tax penalties, interest or underpayment assessments;
- IRS audit costs or professional representation fees;
- lost refunds or missed deductions resulting from extraction errors;
- any consequential financial harm;

**EVEN IF OUTBRANCH NETWORK LLC HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.**

**Total liability cap.** TaxClaw is provided free of charge. Outbranch Network LLC's total liability to you for any and all claims arising from your use of TaxClaw shall not exceed one hundred US dollars ($100).

These limitations are essential terms of these Terms of Use. If you do not accept them, do not use TaxClaw. Some jurisdictions do not allow the exclusion or limitation of incidental or consequential damages, so some of the limitations above may not apply to you. Nothing in these Terms limits any liability that cannot be limited under applicable law.

---

## 9. Open source and third-party components

TaxClaw incorporates open-source libraries and components, and relies on Ollama and the models you install. Their licenses govern them. Outbranch Network LLC is not responsible for defects in third-party components or models.

---

## 10. Privacy

Your use of TaxClaw is also governed by the TaxClaw Privacy Policy at https://github.com/DougButdorf/TaxClaw/blob/main/PRIVACY.md, which is incorporated into these Terms by reference. The web UI also shows it at its Privacy page.

---

## 11. Changes to these Terms

Outbranch Network LLC may update these Terms of Use. Updated Terms will be posted in the TaxClaw repository with a new "Last updated" date, and the web UI shows the version shipped with your installed release. Continued use of TaxClaw after Terms are updated constitutes acceptance of the updated Terms.

---

## 12. Governing law; dispute resolution

These Terms of Use are governed by the laws of the **State of New York**, without regard to conflict-of-law principles.

Any dispute arising from these Terms or your use of TaxClaw shall be brought in the state or federal courts located in **Albany County, New York**. You consent to personal jurisdiction in those courts.

**Limitation period.** Any claim arising from these Terms must be brought within **one (1) year** of the event giving rise to the claim, or it is permanently barred. Some jurisdictions do not allow a shortened limitation period for certain claims; where that is the case, the shortest period the law allows applies.

---

## 13. Severability; entire agreement

If any provision of these Terms is found unenforceable, the remaining provisions remain in full force. These Terms, together with the Privacy Policy and the MIT License, constitute the entire agreement between you and Outbranch Network LLC regarding the open-source TaxClaw tool. TaxClaw Cloud is governed by its own Terms of Service at https://mcp.taxclaw.net/terms.

---

## 14. Contact

Questions about these Terms:

**Outbranch Network LLC**  
Email: lando@outbranch.net  
GitHub: https://github.com/DougButdorf/TaxClaw
