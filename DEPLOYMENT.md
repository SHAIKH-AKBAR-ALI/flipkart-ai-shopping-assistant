# Deployment Guide

## Architecture

- **Backend** → Hugging Face Spaces (Docker), `Akbarali1/flipkart-rag-backend`,
  serves FastAPI on port 7860 at
  `https://akbarali1-flipkart-rag-backend.hf.space`
- **Frontend** → Vercel project `flipkart-ai-shopping-assistant`
  (`https://flipkart-ai-shopping-assistant.vercel.app`), built from
  `frontend-astro/`
- **CI/CD** → GitHub Actions (`.github/workflows/deploy.yml`): push to `main`
  runs a backend health check, then deploys backend and frontend in parallel.

## GitHub Secrets Required

Go to GitHub → Settings → Secrets and variables → Actions and add:

### Backend secrets

| Secret | Value |
|---|---|
| `GROQ_API_KEY` | Groq API key |
| `ASTRA_DB_API_ENDPOINT` | AstraDB endpoint URL |
| `ASTRA_DB_APPLICATION_TOKEN` | AstraDB token |
| `ASTRA_DB_KEYSPACE` | AstraDB keyspace |
| `ASTRA_DB_COLLECTION` | AstraDB collection |
| `MOBILE_API_KEY` | Catalog-fallback API key |
| `TECHSPECS_API_ID` | TechSpecs API ID |
| `TECHSPECS_API_KEY` | TechSpecs API key |
| `LANGCHAIN_TRACING_V2` | `true` |
| `LANGCHAIN_API_KEY` | LangSmith API key |
| `LANGCHAIN_PROJECT` | `flipkart` |
| `ALLOWED_ORIGINS` | `https://flipkart-ai-shopping-assistant.vercel.app` |
| `HF_TOKEN` | From <https://huggingface.co/settings/tokens> (write access) |

### Frontend secrets

| Secret | Value |
|---|---|
| `VERCEL_TOKEN` | From <https://vercel.com/account/tokens> |
| `VERCEL_ORG_ID` | `team_SKwpC6N3KydT0soaXTMm7EI1` |
| `VERCEL_PROJECT_ID` | `prj_xrNjGAGpNUVju2Z73xhrpOyoB4v5` |

## Hugging Face Space setup (one-time)

The Space exists at <https://huggingface.co/spaces/Akbarali1/flipkart-rag-backend>
(Docker SDK, public). The CI pipeline pushes `backend/` into its git repo.

Remaining one-time step: in the Space's Settings → Variables and secrets, add
the same backend env vars as above (`GROQ_API_KEY`, `ASTRA_DB_*`, etc.) — the
Space reads them at runtime; GitHub secrets are only used by CI's health check.

`backend/README.md` carries the required Space frontmatter (`sdk: docker`),
and `backend/Dockerfile` serves on port 7860 (Spaces default).

## Deployment flow

Push to `main` → CI health check (boots `app_v2` and curls `/health` +
`/ready`) → deploy backend to HF Spaces (git push of `backend/`) → deploy
frontend to Vercel (`vercel --prod`) → done.

Pipeline runs: <https://github.com/SHAIKH-AKBAR-ALI/flipkart-ai-shopping-assistant/actions>
