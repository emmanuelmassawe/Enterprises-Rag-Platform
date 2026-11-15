# Owner Decisions (fill in BEFORE starting Milestone 0)

The agent will use these answers to set requirements and architecture. Anything left blank will be treated as an open question and the agent will stop and ask.

## 1. Product

- What will this chatbot be used for? (company knowledge base, customer support, legal/medical/financial documents, education, other)
- Who are the users and roughly how many? (20 users in 12 months)
- Number of tenants/organizations expected:
- Languages of the documents and of the questions ( english documents only ): _this decides the embedding model; it must be multilingual if Swahili documents are involved_
- Types and sizes of documents (PDF only 20 pages and above):
- Approximate total number of documents / pages at launch and in 12 months:

## 2. Providers

- LLM provider and model preference (Gemini api key ):
- Embedding provider/model preference (gemini-embeddings ):
- Do documents contain sensitive data that must not be sent to third-party providers? (the documents are not sensitive )
- Provider accounts and API keys will be created by the owner and given to the agent only as staging keys through environment variables.

## 3. Compliance and data

- Applicable data-protection requirements ( the is not data protection restriction but it should have data privacy ):
- Data residency requirements (can data be processed in the EU/US? yes ):
- Retention periods for documents, conversations, logs:

## 4. Budget and operations

- Monthly infrastructure budget (staging / production):
- Maximum average AI cost per query and per tenant per month:
- Required availability and who is on call:
- Render region (choose the one closest to users that meets residency needs):
- Custom domain(s)[we use localhost ]:

## 5. Identity and access

- Login method for the web UI (email + password, Google only ):
- Roles needed beyond viewer/editor/admin:

## 6. Accounts to prepare

- GitHub repository (you chose PUBLIC; consider PRIVATE during development) with branch protection, secret scanning + push protection, Dependabot and CodeQL enabled, and GitHub Environments (staging, production) with required reviewers for production
- License decision (open source license or proprietary terms)
- Render account and API key (staging first)
- LangSmith Cloud account and API key (staging project)
- Grafana Cloud account and tokens
- S3-compatible storage bucket (AWS S3, Cloudflare R2, other)
- LLM and embedding provider keys
- Remote Terraform state backend (Terraform Cloud, S3-compatible)
