# MyBizVault team test guide

Use [the production app](https://mybizvault.vercel.app/) and fictional business names, customers, amounts and contract terms. Keep real customer details out of demonstration records. Sign in as an owner when testing consultation requests.

1. **Transaction:** Open Transactions → New transaction. Create a fictional customer in the form, enter an itemized sale, an initial payment and a future due date. Save once; the transaction should appear in the list.
2. **Historical receipt:** Open the transaction from Transactions. Preview and download its receipt. It should also remain available after navigating away and returning.
3. **Formal agreement:** Open the same transaction or Agreements. Preview the exact agreement version and its history. Create a review link only for a fictional transaction.
4. **Contract draft:** Open Document Vault → Create a contract draft. Enter fictional parties and terms, save, then preview and download the PDF from the Vault. It is a draft; it has no acceptance or signature.
5. **My Vault:** Search for the contract and agreement. Reopen an older document version and download it. Verify another business cannot access it.
6. **Business law:** Open Legal Assistant. Search for “debt” and choose a category. Open a source link and follow a link to Transactions, Agreements, Negotiations or the Vault.
7. **Practical guidance:** In a Legal Assistant topic, read the meaning, owner action, rights, documents, dispute steps and lawyer referral fields.
8. **Find a Lawyer:** Choose an issue type and review the matching fictional profiles. Select a profile, enter a fictional issue of at least 20 characters and save a consultation request. Confirm it appears under Saved requests with status `draft`. No profile receives the request.
9. **Communications:** On a fictional agreement, use a provider send button only when that channel is configured and the recipient has authorized the test. Check the transaction communication log: `submitted` or `simulated` does not mean delivered. The manual WhatsApp link opens a share composer; sending requires a separate user action.
10. **Approvals:** With a consenting test recipient and configured delivery, open the public review link, request a code and accept the displayed version. For Africa's Talking sandbox, use the simulator's registered number, SMS inbox and service code `*384*12566#`. Check the agreement events, transaction history and communication logs afterward. Never use a real customer agreement for this test.

If a provider is unconfigured, record the blocked step rather than claiming a successful send. See [deployment setup](deployment.md) for callback URLs and environment variable names.
