# Phase 6 Step 13 — Production Readiness & Controlled Launch Gate

## Purpose

Provide a read-only, evidence-based preflight for the first production pilot on both
independent channels: Devotional and Motivation. A passing audit means the two pilot
videos are ready for manual review. It does **not** authorize publishing or production
go-live.

## Create a local readiness manifest

Create `storage/config/production_readiness_manifest.json` locally (do not commit it).
Use the template below and replace placeholders with local file paths and operator-
verified values. Never paste credentials or token contents into the manifest or GitHub.

```json
{
  "manifest_type": "youtube_production_readiness_manifest",
  "schema_version": 1,
  "public_uploads_enabled": false,
  "human_approval_required": true,
  "channels": {
    "devotional": {
      "channel_id": "YOUR_DEVOTIONAL_CHANNEL_ID",
      "oauth_client_secrets_file": "/secure/path/devotional-client-secret.json",
      "oauth_token_file": "/secure/path/devotional-token.json",
      "oauth_verified": false,
      "channel_access_verified": false,
      "upload_scope_verified": false,
      "providers": {
        "narration": {"name": "YOUR_PROVIDER", "configured": false, "verified": false},
        "image": {"name": "YOUR_PROVIDER", "configured": false, "verified": false},
        "video": {"name": "YOUR_PROVIDER", "configured": false, "verified": false}
      },
      "pilot_video_file": "storage/pilots/devotional-pilot.mp4",
      "pilot_quality_report_file": "storage/pilots/devotional-quality.json",
      "upload_approved": false
    },
    "motivation": {
      "channel_id": "YOUR_MOTIVATION_CHANNEL_ID",
      "oauth_client_secrets_file": "/secure/path/motivation-client-secret.json",
      "oauth_token_file": "/secure/path/motivation-token.json",
      "oauth_verified": false,
      "channel_access_verified": false,
      "upload_scope_verified": false,
      "providers": {
        "narration": {"name": "YOUR_PROVIDER", "configured": false, "verified": false},
        "image": {"name": "YOUR_PROVIDER", "configured": false, "verified": false},
        "video": {"name": "YOUR_PROVIDER", "configured": false, "verified": false}
      },
      "pilot_video_file": "storage/pilots/motivation-pilot.mp4",
      "pilot_quality_report_file": "storage/pilots/motivation-quality.json",
      "upload_approved": false
    }
  }
}
```

Set a verification flag to `true` only after an operator has actually completed and
checked that step. OAuth verification must confirm the intended Google account and
channel, and confirm the required YouTube upload scope for the publishing workflow.
The audit checks that referenced credential files exist; it never reads their contents
or independently authenticates them.

Each quality report must be JSON with `"status": "passed"` and a `"video_file"`
path resolving to the exact pilot video configured for that channel.

## Run

From the repository root:

```bash
python automation/build_youtube_production_readiness.py \
  --manifest storage/config/production_readiness_manifest.json \
  --output-json storage/reports/production_readiness.json \
  --output-md storage/reports/production_readiness.md
```

A non-zero exit code means one or more readiness gates are blocked. Resolve the
reported blockers and rerun the audit. Outputs belong in local storage and must not
contain secret values.

## Release gates

1. Both channel IDs are configured and independently verified.
2. OAuth client and token files exist; Google OAuth, channel access and upload scope
   are operator-verified separately for each channel.
3. Narration, image and video providers are configured and verified independently
   for each channel.
4. One pilot video per channel exists and its matching final-render quality report
   passes.
5. Public uploads remain disabled and every upload requires separate human approval.
6. Manually review narration, factual accuracy, rights/licensing, visuals, subtitles,
   thumbnail, metadata and final playback before any upload.

## Safety boundary

This step only audits local evidence. It does not make API calls, reveal or parse
credentials, invoke paid/free providers, render, schedule, retry or upload. The report
always sets `production_authorized=false` and `public_uploads_enabled=false`.
A successful preflight advances the project to manual pilot review; it is not a
production go-live authorization.

## Tests

```bash
python -m unittest automation.tests.test_build_youtube_production_readiness
```
