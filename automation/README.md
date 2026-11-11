# YouTube Content Calendar Automation

This utility converts a UTF-8 CSV content calendar into a validated batch manifest for MoneyPrinterTurbo. The channel profiles are deliberately separated: use one calendar and one profile per YouTube channel.

## Two independent channel workflows

| Channel | Profile key | Content boundary | Example calendar |
|---|---|---|---|
| Devotional | `devotional` | Bhakti, Hindu deities, epics, mythology, spiritual reflections | [devotional_channel_calendar.csv](examples/devotional_channel_calendar.csv) |
| Motivational | `motivation` | Motivational stories, discipline, mindset, life lessons, original motivational Shayari | [motivational_channel_calendar.csv](examples/motivational_channel_calendar.csv) |

Keep each channel's brand name, logo, voice, thumbnail style, descriptions, playlists, upload defaults, and analytics separate. Do not mix devotional topics into the motivational channel or vice versa. Mythology is part of the devotional channel when it is framed as devotional/epic storytelling.

## Channel configuration (Phase 3)\n\n`channel_configs.json` stores independent identity and production defaults for the two channels: language, Shorts/long-form aspect ratios, voice overrides, creative direction, thumbnail direction, music guidance, SEO defaults, and publishing safeguards. The file contains no credentials. Configure actual channel IDs and voice names only after confirming the correct accounts and provider voices.\n\nValidate the configuration from the repository root:\n\n```bash\npython automation/validate_channel_configs.py\npython -m unittest automation.tests.test_channel_configs\n```\n\nBoth channels intentionally start with publishing disabled, private visibility, mandatory human approval, and an unset `made_for_kids` declaration. Do not change the audience declaration without reviewing the actual video. The account environment-variable names are consumed by the Phase 6 Step 2 local credential validator. They are not yet wired into an upload action; publishing remains disabled.\n\n## Channel-aware production preparation (Phase 4)

After applying the content profile, apply the channel's production defaults to the enriched calendar. Non-empty row-level values take priority over channel defaults.

```bash
python automation/prepare_channel_calendar.py automation/examples/devotional_channel_calendar.devotional.csv --channel devotional
python automation/prepare_channel_calendar.py automation/examples/motivational_channel_calendar.motivation.csv --channel motivation
```

Each command creates a separate production CSV. Convert each prepared CSV into its own batch manifest:

```bash
python automation/content_calendar_to_batch.py automation/examples/devotional_channel_calendar.devotional.production.csv
python automation/content_calendar_to_batch.py automation/examples/motivational_channel_calendar.motivation.production.csv
```

Run the resulting manifests with the existing CLI only after reviewing them. Validate with:

```bash
python -m unittest automation.tests.test_prepare_channel_calendar
```

This step applies locale, voice overrides, voice rate/volume, subtitles, default aspect ratio, and channel-specific scene-friendly narration context. Thumbnail and music directions remain editorial guidance only: this phase does not create thumbnail images, generate custom music, produce SEO metadata, automatically select a verified TTS voice, or connect publishing accounts. Publishing remains a separate manually reviewed action.

## 1. Apply the correct channel profile

From the repository root:

```bash
python automation/apply_content_profile.py automation/examples/devotional_channel_calendar.csv --profile devotional
python automation/apply_content_profile.py automation/examples/motivational_channel_calendar.csv --profile motivation
```

Each command creates a new CSV with the selected channel prompt appended to each row's `video_script_prompt`. Existing row-specific instructions are preserved. The original CSV is not overwritten.

## 2. Generate batch manifests separately

```bash
python automation/content_calendar_to_batch.py automation/examples/devotional_channel_calendar.devotional.csv
python automation/content_calendar_to_batch.py automation/examples/motivational_channel_calendar.motivation.csv
```

This creates a separate JSONL manifest beside each enriched CSV. Review the files before generation.

## 3. Generate videos

```bash
python cli.py --batch-file automation/examples/devotional_channel_calendar.devotional.jsonl
python cli.py --batch-file automation/examples/motivational_channel_calendar.motivation.jsonl
```

The CLI's configured providers, API credentials, and voice settings apply. Confirm that the selected Hindi voice is available from your configured TTS provider.

## 4. Calendar columns

Required per row: either `video_subject` or `video_script`.

| Column | Purpose | Example |
|---|---|---|
| `video_subject` | Video topic | Hindi topic |
| `video_script` | Ready narration script (optional) | Hindi script |
| `video_aspect` | Output ratio | `9:16` Shorts, `16:9` long-form |
| `video_language` | Language / TTS locale | `hi-IN` |
| `video_clip_duration` | Target stock clip duration | `4` |
| `video_count` | Variations | `1` |
| `voice_name` | Configured TTS voice | Leave blank for app default |
| `bgm_type` | Background music | `random` |
| `subtitle_enabled` | Subtitles | `true` / `false` |
| `video_source` | Material provider | `pexels` |

The batch generator also accepts supported scalar `VideoParams` fields such as `video_terms`, `video_fit_mode`, `image_motion`, `video_concat_mode`, `video_transition_mode`, `video_clip_speed`, `match_materials_to_script`, `custom_audio_file`, `voice_volume`, `voice_rate`, `bgm_file`, `bgm_volume`, subtitle styling fields, `paragraph_number`, `video_script_prompt`, and `custom_system_prompt`. Unknown columns are rejected.

## 5. Validate without writing

```bash
python automation/content_calendar_to_batch.py automation/examples/devotional_channel_calendar.devotional.csv --check
python automation/content_calendar_to_batch.py automation/examples/motivational_channel_calendar.motivation.csv --check
```

The CLI batch manifest limit is 100 tasks and 1 MiB. The generator checks these limits and basic field types before writing.

## Existing native capabilities and safeguards

MoneyPrinterTurbo already contains script generation, social metadata generation, and Upload-Post cross-posting including YouTube settings. Phase 2 should orchestrate these existing capabilities, not duplicate them.

- The profile applicator prepares prompts; it does not call an AI model by itself.
- This workflow does not publish or schedule uploads automatically.
- Configure each channel's YouTube account/destination and publishing settings separately in the relevant publishing service.
- Keep uploads disabled until you review the video, title, description, tags, audience declaration, synthetic-media disclosure, and privacy.
- Review script accuracy, visual relevance, music licensing, and subtitles before publishing.
- Never assume a default TTS voice is suitable; verify it is configured and pronounce Hindi correctly.


## AI scene, thumbnail and YouTube metadata brief (Phase 5 — Step 1)

Generate a structured creative brief from a finished Hindi script. Run from the repository root after configuring a working LLM provider in MoneyPrinterTurbo:

```bash
python automation/generate_content_assets.py --channel devotional --subject "हनुमान जी की भक्ति और साहस" --script-file path/to/hanuman_script.txt
python automation/generate_content_assets.py --channel motivation --subject "अनुशासन की ताकत" --script-file path/to/discipline_script.txt
```

The output is a separate JSON file containing:
- Chronological scenes with script excerpts, visual descriptions, standalone image prompts, English stock-search terms, and motion directions.
- A channel-specific 16:9 thumbnail concept, short Hindi headline, and image-generation prompt.
- YouTube title, description, tags, and hashtags in the configured channel language.

Use `--output` to choose a destination file. The tool uses the configured MoneyPrinterTurbo LLM provider and therefore may incur provider charges or usage limits.

Validate the parser and channel separation with:

```bash
python -m unittest automation.tests.test_generate_content_assets
```

**Scope boundary:** this step generates creative prompts and metadata only. It does not render image files, compose a thumbnail image, generate a video, or upload/schedule content. Use the image prompts with a separately configured image provider or approved image-generation workflow. Review every generated scene for script accuracy, cultural sensitivity, licensing, and visual consistency. Review SEO copy for factual accuracy before publishing. Public uploads remain disabled and require human approval.


## Scene image rendering (Phase 5 — Step 2)

After generating and reviewing a Phase 5 asset package, you can render a small set of scene illustrations and an optional thumbnail using the repository's Codex image adapter.

First run a dry-run plan (no image requests are made):

```bash
python automation/render_scene_images.py path/to/hanuman_script.devotional.assets.json --max-scene-images 3 --include-thumbnail
```

Actual rendering is deliberately opt-in. Configure and authorize the Codex image provider in MoneyPrinterTurbo, then add `--execute`:

```bash
python automation/render_scene_images.py path/to/hanuman_script.devotional.assets.json --max-scene-images 3 --include-thumbnail --execute
```

For motivational assets, pass that channel's generated JSON package instead. The tool:
- Uses the existing Codex image authorization and image-generation adapter; it does not store credentials in files.
- Processes requests sequentially and caps scene generation at 12 images per run, plus one optional thumbnail.
- Skips existing output files, validates returned PNG files, and writes an `image_manifest.json` with per-image status.
- Stops on an image-provider error and does not automatically retry a request whose billing outcome may be uncertain.

Image-generation access, quotas, and any associated usage charges depend on the configured Codex account and current provider terms. Review those before using `--execute`. A dry run does not require image-provider authorization.

Test the input validation and dry-run planner:

```bash
python -m unittest automation.tests.test_render_scene_images
```

This step creates individual PNG assets; it does not assemble a finished video or guarantee visual consistency across scenes. Review the images, add any required continuity corrections, and compose the final video/thumbnail in a separate step. Keep public uploads disabled pending human review.


## Local scene-image video assembly (Phase 5 — Step 3)

Once scene PNGs have been generated with `render_scene_images.py --execute`, prepare a task that feeds those images to MoneyPrinterTurbo's existing local-material pipeline:

```bash
python automation/prepare_image_video_task.py \
  --assets path/to/hanuman_script.devotional.assets.json \
  --image-manifest path/to/hanuman_script.devotional.assets.images/image_manifest.json \
  --script-file path/to/hanuman_script.txt \
  --aspect 16:9
```

For a Shorts output, use `--aspect 9:16` (the default). The tool:
- Requires an executed image manifest and uses only scene images marked generated or skipped-existing; thumbnail images are excluded.
- Sorts images by scene number, copies them into `storage/local_videos/<package-channel>/`, and writes a one-task JSONL manifest under `storage/local_videos/`.
- Configures the existing local image renderer, sequential scene order, slow zoom, subtitles, and the selected output aspect ratio.
- Does not generate new images, audio, or metadata and does not publish or schedule anything.

Then run the prepared task:

```bash
python cli.py --batch-file storage/local_videos/hanuman-script-devotional.video.jsonl
```

The actual output filename is printed by the preparation command; use that exact path. Use a separate assets package and image manifest for each channel. The existing engine turns each still image into a short moving clip and extends/combines the clips to cover the narration. **This initial integration does not align scene changes to exact narration timestamps**: the images play in order and may repeat to cover long audio. For long-form videos, review the result carefully; this Step 3 workflow does not align scene changes to narration timestamps. Use the Phase 5 Step 5 timed-scene preparation below when you have an approved SRT-based timeline.

Run the unit tests with:

```bash
python -m unittest automation.tests.test_prepare_image_video_task
```

This is a preparation utility only. It does not bypass the existing CLI, alter the core renderer, or upload content. Human review remains mandatory.


## Narration-aligned scene timeline (Phase 5 — Step 4)

After the final narration audio has been transcribed to SRT, align each generated scene's `narration_excerpt` against the subtitle cues:

```bash
python automation/build_scene_timeline.py \
  --assets path/to/story.devotional.assets.json \
  --image-manifest path/to/story.devotional.assets.images/image_manifest.json \
  --subtitles path/to/narration.srt
```

The utility:
- Uses the scene excerpt text from the AI asset package and only images marked generated/skipped-existing in an executed image manifest.
- Matches excerpts against SRT cue text in chronological order, using approximate token matching to tolerate minor speech-recognition differences.
- Writes `scene_timeline.json` with start/end times, duration, match score and image path for each scene.
- Marks low-confidence or unmatched scenes for manual review instead of silently assigning a misleading timestamp.

Optional: set a stricter match threshold with `--min-score 0.70`. The default is 0.55. If the command exits with status 1, one or more scenes need manual review; status 2 indicates invalid input or an execution error.

Validate with:

```bash
python -m unittest automation.tests.test_build_scene_timeline
```

**Important boundary:** this is a timing-analysis and review artifact only. It does not modify the video renderer or automatically apply the timeline to the final MP4 yet. Whisper/SRT recognition differences can affect match confidence, so inspect every scene boundary. Phase 5 Step 5 below converts an approved timeline into per-scene timed MP4 clips and a task manifest for the existing renderer.

## Timed scene video preparation (Phase 5 — Step 5)

Once Step 4 has produced an approved `scene_timeline.json`, prepare a local video task that renders each still for its narration interval and then passes the resulting clips to the existing MoneyPrinterTurbo video pipeline.

Use the **same final narration audio file** that was used to create the SRT/timeline:

```bash
python automation/prepare_timed_scene_video_task.py \
  --timeline path/to/scene_timeline.json \
  --image-root path/to/story.devotional.assets.images \
  --audio-file path/to/final_narration.mp3 \
  --script-file path/to/final_script.txt \
  --aspect 16:9
```

For a Shorts video, use `--aspect 9:16`. Use `--image-motion static` if you prefer no zoom movement. The tool:
- Requires every scene to be aligned and every image to be present under `--image-root`; it stops rather than guessing timings for low-confidence scenes.
- Holds the first image from the beginning of the video, changes scenes at the next aligned narration start, and holds the final image through the audio tail plus a short safety margin.
- Renders one MP4 clip per scene, copies the narration audio and clips into a channel-specific folder under `storage/local_videos/`, and writes a one-task JSONL manifest directly under `storage/local_videos/` (the optional `--output` path must also be directly inside that directory).
- Uses the same narration audio as a custom audio input, so the generated video does not depend on regenerating TTS.

Run the prepared task using the exact manifest path printed by the command:

```bash
python cli.py --batch-file storage/local_videos/<printed-manifest-name>.jsonl
```

**Subtitle note:** custom audio does not provide a TTS subtitle maker. To burn subtitles through the existing pipeline, configure the MoneyPrinterTurbo subtitle provider as `whisper`; other providers may skip subtitle generation for custom audio. The SRT used to build the scene timeline is used for timing analysis, not automatically burned into the MP4 by this preparation utility.

Test with:

```bash
python -m unittest automation.tests.test_prepare_timed_scene_video_task
```

This step prepares timed scene clips and a task manifest; it does not upload or schedule content. The final renderer still applies the engine's standard clip concatenation and safety margin. Inspect the complete MP4, especially scene boundaries and the final narration tail, before publishing. Keep the devotional and motivational asset packages, audio, and manifests separate.

## Final rendered-video quality gate (Phase 5 — Step 6)

After the CLI has produced the final MP4, run a metadata-based quality gate against the exact narration audio:

```bash
python automation/validate_rendered_video.py \
  --video-file path/to/final-1.mp4 \
  --audio-file path/to/final_narration.mp3 \
  --aspect 16:9 \
  --report path/to/quality_report.json
```

For Shorts, use `--aspect 9:16`. The gate uses FFprobe to verify:
- The final MP4 contains both video and audio streams.
- Frame dimensions match the requested aspect ratio within a 2% tolerance.
- The final video covers at least 99.5% of the narration duration by default.
- The video does not exceed the narration duration by more than 8 seconds by default (the timed-scene workflow adds a short final hold).

Optional controls:
- `--min-audio-coverage 0.99` adjusts the minimum duration coverage.
- `--max-extra-seconds 10` adjusts the allowed video tail.
- `--ffprobe /path/to/ffprobe` selects a specific FFprobe executable.

The command returns exit code 0 and a JSON report when the checks pass; it returns exit code 2 with a clear failure message when a check fails. FFprobe must be installed and available on PATH.

Test the metadata checks with:

```bash
python -m unittest automation.tests.test_validate_rendered_video
```

**Quality boundary:** this is a technical file-integrity gate, not an editorial review. It cannot judge whether the images match the narration, whether scene cuts feel natural, whether the Hindi pronunciation is correct, whether the audio sounds clean, or whether subtitles are actually burned into the picture. Watch and listen to the complete MP4 before publishing. The tool does not upload or schedule content.


## YouTube publishing approval package (Phase 6 — Step 1)

Create a review-only publishing manifest after the final MP4 and thumbnail have been rendered and checked. The tool keeps the devotional and motivational channels separate and does not upload or schedule content.

Example for the devotional channel:

```bash
python automation/prepare_youtube_publishing_package.py \
  --channel devotional \
  --assets path/to/hanuman.assets.json \
  --video path/to/final-1.mp4 \
  --thumbnail path/to/thumbnail.png \
  --made-for-kids no \
  --synthetic-media yes
```

For the motivational channel, use `--channel motivation` and that channel's own asset package. The audience and synthetic-media answers are mandatory per-video inputs; review the actual content before choosing them. Do not assume every video has the same audience classification.

The output defaults to the video filename with `.publishing.json` appended in place of its extension. It contains:
- Channel identity and channel-specific Upload-Post account environment-variable *name* (never credentials).
- Final video and optional thumbnail paths, title, description, tags, hashtags and configured privacy status.
- Explicit per-video audience and synthetic-media declarations.
- A pending-human-review checklist covering the final video, thumbnail, metadata, music/copyright, audience, synthetic-media disclosure and destination account.
- Approval fields left blank, `upload_authorized=false`, and the channel upload configuration still required to be disabled.

The utility refuses cross-channel asset packages, missing media files, invalid YouTube metadata and channel configurations that enable uploads. It does not change channel configuration, read environment variables or API keys, call Upload-Post, publish, or schedule. A human must review and approve the package in a future, separately implemented publishing step.

Run tests:

```bash
python -m unittest automation.tests.test_prepare_youtube_publishing_package
```


## Secure channel publishing credentials (Phase 6 — Step 2)

The two channels use separate Upload-Post API-key and account-username environment variables. Do not put credential values in `channel_configs.json`, CSV files, JSON manifests, source code, screenshots, or Git commits.

Environment-variable names are declared per channel in `channel_configs.json`:
- Devotional: `MPT_DEVOTIONAL_UPLOAD_POST_API_KEY` and `MPT_DEVOTIONAL_UPLOAD_POST_USERNAME`
- Motivation: `MPT_MOTIVATION_UPLOAD_POST_API_KEY` and `MPT_MOTIVATION_UPLOAD_POST_USERNAME`

Set the values in the private environment of the machine/container that runs MoneyPrinterTurbo. For a temporary local shell session, for example:

```bash
export MPT_DEVOTIONAL_UPLOAD_POST_API_KEY="your-devotional-api-key"
export MPT_DEVOTIONAL_UPLOAD_POST_USERNAME="your-devotional-upload-post-username"
export MPT_MOTIVATION_UPLOAD_POST_API_KEY="your-motivation-api-key"
export MPT_MOTIVATION_UPLOAD_POST_USERNAME="your-motivation-upload-post-username"
```

Do not paste real values into chat or commit them. Use your deployment platform's secret manager for persistent deployment, with access limited to the publishing runtime.

Validate each channel independently without printing credentials or contacting Upload-Post:

```bash
python automation/validate_channel_upload_accounts.py --channel devotional
python automation/validate_channel_upload_accounts.py --channel motivation
```

The resolver returns an in-memory account snapshot compatible with the existing `UploadPostService(account=...)` interface. It refuses missing credentials, malformed environment-variable names, reused key/username variable names, or a channel configuration with uploads enabled. The CLI reports presence only.

**Scope boundary:** this step validates local secret presence and account separation; it does not authenticate against Upload-Post, confirm the remote account's connected YouTube channel, modify the existing upload pipeline, or enable publishing. The actual YouTube destination must be confirmed in the Upload-Post dashboard before any future upload integration. Uploads remain disabled and require human approval.


## Explicitly approved YouTube publishing (Phase 6 — Step 3)

The publishing command is a separate, one-video action. It reuses the existing Upload-Post service but does not turn on global or channel-level auto-upload. Channel configuration must continue to contain `upload_enabled=false`.

### 1. Review and approve the package

Open the `.publishing.json` file created in Step 1. Only after watching the complete MP4 and reviewing the thumbnail, metadata, rights, audience declaration, synthetic-media declaration and destination account:

- Set `workflow.status` to `"approved"`.
- Set `workflow.upload_authorized` to `true`.
- Set every item in `workflow.checks` to `true`.
- Fill `workflow.approval.approved_by` with the responsible human approver.
- Fill `workflow.approval.approved_at` with an ISO-8601 timestamp.
- Keep `publishing_account_env` unchanged; it must match the selected channel configuration.

Do not mark the package approved merely to test the command. Choose the audience and synthetic-media declarations based on the actual finished video and applicable YouTube requirements.

### 2. Validate without uploading

Set the selected channel's API key and username in the private runtime environment as documented in Step 2, then run:

```bash
python automation/publish_approved_youtube_package.py \
  --channel devotional \
  --manifest path/to/video.publishing.json
```

For the motivational channel, use `--channel motivation` and its own manifest and credentials. This default mode makes no network request and does not change the manifest.

### 3. Execute one explicitly approved upload

Only after the dry-run is ready and the correct destination account has been confirmed in Upload-Post, run:

```bash
python automation/publish_approved_youtube_package.py \
  --channel devotional \
  --manifest path/to/video.publishing.json \
  --execute \
  --confirm-upload
```

The command submits only to YouTube, using the approved title, description, tags, privacy, made-for-kids and synthetic-media values. It enables publishing only in a one-shot in-memory account snapshot for this invocation. It writes an execution-attempt record to the manifest before making the network request.

**Duplicate protection:** a manifest with any recorded execution attempt is blocked from another automatic run. If the result is `outcome_unconfirmed`, do not retry; reconcile the request ID in Upload-Post first. A failed or interrupted attempt also requires manual investigation before creating a new approved package.

**Scope and safety:** this command does not schedule a future publication time, publish to other platforms, enable global auto-upload, alter channel configuration, verify that the remote Upload-Post account is connected to the intended YouTube channel, or guarantee successful processing by YouTube. Confirm the connected destination in the provider dashboard. Public visibility is possible only if the human-approved manifest explicitly specifies it; private is the channel default.

Run tests:

```bash
python -m unittest automation.tests.test_publish_approved_youtube_package
python -m unittest test.services.test_upload_post_synthetic_media_declaration
```

These tests are added to the repository; they must be executed in your local/runtime environment before production use.


## Channel-wise publishing outcome reports (Phase 6 — Step 4)

After running the approved publishing command, aggregate the local `*.publishing.json` manifests into separate devotional and motivational channel summaries:

```bash
python automation/build_publishing_report.py \
  --input-dir path/to/publishing-packages \
  --output-json path/to/reports/publishing_report.json \
  --output-csv path/to/reports/publishing_report.csv
```

The input directory is searched recursively. The report includes:
- One record per valid publishing manifest, with channel, subject, title, privacy and audience declarations.
- Workflow status: pending review, approved, submitting, completed, failed or outcome unconfirmed.
- Human approval identity/time, attempt start/end time, Upload-Post request ID and whether an error was recorded.
- Separate totals for each channel, including completed, failed, unconfirmed, pending-review and approved-not-submitted counts.
- Warnings for invalid manifests, without aborting the entire report.

The CSV is UTF-8 with BOM for spreadsheet compatibility. The JSON and CSV include local file paths; store and share them only with people authorized to see your production file structure. Raw error text and credentials are intentionally excluded.

**Measurement boundary:** this is an operational publishing report, not YouTube performance analytics. It does not fetch views, impressions, watch time, CTR, subscribers, revenue, audience retention, or confirm public availability on YouTube. A completed Upload-Post response means the provider reported completion; verify the video in YouTube Studio. For actual channel performance, use YouTube Studio/YouTube Analytics separately.

Run tests:

```bash
python -m unittest automation.tests.test_build_publishing_report
```

Tests are added but must be run in your environment before relying on the report in production.


## YouTube Analytics read-only integration (Phase 6 — Step 5)

This step retrieves performance reports independently for the devotional and motivation channels using Google's YouTube Analytics API and verifies account identity through YouTube Data API. It never uploads, schedules, edits, or deletes content.

### One-time Google Cloud setup

1. In Google Cloud Console, create or select a project and enable **YouTube Analytics API** and **YouTube Data API v3**.
2. Configure the OAuth consent screen for your use case and create an OAuth client of type **Desktop app**.
3. Download the OAuth client JSON to a private local folder. Never commit it or paste its contents into chat.
4. Set each channel's `youtube_channel_id` in `automation/channel_configs.json` after verifying the channel ID in YouTube Studio.
5. Set the relevant environment variable. Example (Linux/macOS):
   ```bash
   export MPT_DEVOTIONAL_GOOGLE_OAUTH_CLIENT_SECRETS="$HOME/.config/mpt/google-devotional-client.json"
   export MPT_MOTIVATION_GOOGLE_OAUTH_CLIENT_SECRETS="$HOME/.config/mpt/google-motivation-client.json"
   ```
   Use separate OAuth clients or explicitly authorize the correct Google account for each channel. The script verifies the authenticated channel ID before requesting Analytics data.

### Run a report

```bash
python automation/youtube_analytics_readonly.py --channel devotional
python automation/youtube_analytics_readonly.py --channel motivation
```

The default date range is the last 28 complete days (ending yesterday). Specify a range and output path when required:

```bash
python automation/youtube_analytics_readonly.py --channel devotional --start-date 2026-10-01 --end-date 2026-10-31 --output storage/analytics/devotional_october.json
```

On first run, a browser opens for Google OAuth consent. Only `youtube.readonly` and `yt-analytics.readonly` scopes are requested. Access and refresh tokens are stored separately under `~/.config/mpt/youtube-analytics/{channel}.json` with restrictive file permissions where supported. Use `--reauthorize` to repeat consent. Keep OAuth client JSON and token files outside the repository.

### Included reports

- Daily channel activity: views, engaged views, estimated minutes watched, average view duration/percentage, subscribers gained/lost, likes, comments and shares, split by creator content type where available.
- Top 50 videos ranked by estimated minutes watched.
- Traffic-source type breakdown by views and estimated minutes watched.
- Verified channel identity and requested date range.

Thumbnail impressions and CTR are intentionally not claimed in this first targeted-query integration. Google's documentation lists these in YouTube Reporting API reach reports. Audience-retention curves are deferred to a separately validated report. Analytics data can be delayed or adjusted by YouTube.

### Security and operational boundaries

- Read-only OAuth scopes only; no write or upload scopes.
- Channel ID is checked against the authenticated account before Analytics requests run.
- Separate token files per channel; OAuth client JSON and tokens remain outside the repository.
- `upload_enabled` remains false and human publishing approval is unchanged.
- Treat generated reports as private channel performance data.

Validate helper functions without making Google API calls:

```bash
python -m unittest automation.tests.test_youtube_analytics_readonly
```


## YouTube Performance Intelligence (Phase 6 — Step 6)

Build a local, rule-based analysis from one or both channel exports generated by Phase 6 Step 5. This step makes no Google API calls and does not modify or publish channel content.

Generate Step 5 exports first, after configuring the correct channel IDs and completing read-only OAuth:

```bash
python automation/youtube_analytics_readonly.py --channel devotional
python automation/youtube_analytics_readonly.py --channel motivation
```

Analyze one channel:

```bash
python automation/build_youtube_performance_intelligence.py \
  --input storage/analytics/devotional_YYYY-MM-DD_YYYY-MM-DD.json \
  --output-json storage/analytics/devotional_intelligence.json \
  --output-md storage/analytics/devotional_intelligence.md
```

Analyze both channels independently and create a side-by-side comparison:

```bash
python automation/build_youtube_performance_intelligence.py \
  --input storage/analytics/devotional_YYYY-MM-DD_YYYY-MM-DD.json \
  --input storage/analytics/motivation_YYYY-MM-DD_YYYY-MM-DD.json \
  --output-json storage/analytics/channel_intelligence.json \
  --output-md storage/analytics/channel_intelligence.md
```

The report includes views, estimated watch hours, weighted average view duration and percentage, engagement rate, subscriber conversion, net subscribers, creator-content-type breakdown (when returned by Analytics), first-half versus second-half period movement, top 10 videos by estimated watch time, traffic-source mix, and transparent rule-based next-step recommendations. Each channel remains a separate identity and data set.

**Interpretation boundaries:** this is descriptive analysis, not causal attribution or a virality prediction. The Step 5 export does not include thumbnail impressions/CTR, retention curves, revenue, or video titles; the report does not fabricate those insights. Average view percentage is not a retention curve. Estimated watch time is not the official YouTube Partner Program public-watch-hours counter; use YouTube Studio Earn for authoritative eligibility progress. Do not infer Shorts-versus-long-form from duration; use the creator content type dimension when present. Top-video IDs require separately validated metadata enrichment before topic/title analysis.

Run unit tests:

```bash
python -m unittest automation.tests.test_build_youtube_performance_intelligence
```

The tool reads local JSON exports only; it does not upload, schedule, edit, delete, or change channel settings.


## Content Intelligence & Growth Planner (Phase 6 — Step 7)

Turn a Phase 6 Step 6 intelligence export into separate, channel-specific editorial pillars, topic ideas, format-test priorities, creative experiments and a 14-day execution framework. This is a local planning utility; it does not call an AI provider or publish content.

Create the Step 6 input first:

```bash
python automation/build_youtube_performance_intelligence.py \
  --input storage/analytics/devotional_YYYY-MM-DD_YYYY-MM-DD.json \
  --input storage/analytics/motivation_YYYY-MM-DD_YYYY-MM-DD.json \
  --output-json storage/analytics/channel_intelligence.json
```

Build the growth plan:

```bash
python automation/build_youtube_content_growth_plan.py \
  --input storage/analytics/channel_intelligence.json \
  --output-json storage/analytics/content_growth_plan.json \
  --output-md storage/analytics/content_growth_plan.md
```

Optional reviewed video catalog: create a UTF-8 CSV with columns `channel,video_id,title,topic,format` and pass `--catalog-csv path/to/video_catalog.csv`. Exact video IDs join the catalog to Step 6 top-video rows. This enables topic analysis only for rows that have been manually mapped; the planner does not guess titles or topics from IDs.

The plan provides:
- Separate devotional and motivation content pillars and Hindi editorial idea banks.
- Format opportunity signals based on watch hours and subscriber gains per 1,000 views, requiring at least 100 views for each of two compared creator-content types.
- Four controlled experiments covering opening hooks, format mix, recurring series and packaging.
- A practical 14-day review and testing framework.
- Explicit limitations where CTR, retention curves, returning viewers or topic metadata are unavailable.

The 100-view comparison threshold is an internal planning filter, not a YouTube benchmark. Format comparisons are directional and do not prove causation. CTR and returning-viewer outcomes must be checked in YouTube Studio when available. The plan does not guarantee views, subscribers, virality or watch hours. Keep channel identities, audience promises, assets and metadata separate.

Run tests:

```bash
python -m unittest automation.tests.test_build_youtube_content_growth_plan
```

The planner reads local JSON/CSV files only. It does not make API calls, generate scripts or images, upload, schedule, or change channel settings.


## Data-led Growth Calendar Generator (Phase 6 — Step 8)

Convert a Phase 6 Step 7 growth plan into a dated 14-day editorial calendar and a separate MoneyPrinterTurbo-compatible production CSV. Generate each channel separately so its editorial identity and output files stay isolated.

Example for the devotional channel:

    python automation/build_youtube_growth_calendar.py \
      --input storage/analytics/content_growth_plan.json \
      --channel devotional \
      --start-date 2026-11-12 \
      --posts-per-week 5 \
      --format-mix data-led \
      --output-dir storage/calendars/devotional

For the motivation channel, change --channel motivation and use a separate output directory. The default cadence is five posts per week (10 slots over 14 days); choose 1–14 posts per week to control production volume.

Format mix options:
- data-led (default): if Step 7 contains a directional comparison of creator content types, schedule two slots for the observed leading type for every one slot of the other type. If evidence is insufficient, alternate Shorts and long-form.
- balanced: alternate Shorts and long-form.
- shorts-heavy: two Shorts slots for every long-form slot.
- long-form-heavy: two long-form slots for every Shorts slot.

Two files are created:
- <channel>_editorial_calendar.csv: publish date, channel, format, content pillar, topic, aspect ratio and review status for planning.
- <channel>_production.csv: only supported MoneyPrinterTurbo task fields, including Hindi script-generation prompt, format aspect ratio, subtitles and stock-material source.

### Continue into the existing production workflow

    # 1. Add the channel's reusable Hindi prompt profile
    python automation/apply_content_profile.py storage/calendars/devotional/devotional_production.csv --profile devotional

    # 2. Apply channel defaults and scene-friendly creative context
    python automation/prepare_channel_calendar.py storage/calendars/devotional/devotional_production.devotional.csv --channel devotional

    # 3. Validate the prepared production CSV without writing a manifest
    python automation/content_calendar_to_batch.py storage/calendars/devotional/devotional_production.devotional.production.csv --check

    # 4. Create a batch manifest after validation
    python automation/content_calendar_to_batch.py storage/calendars/devotional/devotional_production.devotional.production.csv

Use the corresponding motivation profile and its own paths for the motivational channel. Check actual output filenames printed by each command; do not mix channel CSVs, scripts, media or manifests.

**Scope and approval boundary:** this step creates dated editorial slots and production task inputs. It does not generate scripts, images, audio or videos; does not call Google/YouTube APIs; and does not upload or schedule content. The editorial dates are planning targets only, not platform-scheduled publication times. Continue through the existing render, quality-check and review-only publishing-package steps. A human must approve each video before any upload; channel upload_enabled remains false.

Run tests:

    python -m unittest automation.tests.test_build_youtube_growth_calendar

The test also verifies that generated production CSV rows are accepted by the existing batch CSV converter.


## End-to-end production workflow planner (Phase 6 — Step 9)

Build a channel-specific runbook that connects the existing creative brief, scene-image, narration-timeline, timed-render and publishing-review utilities. Start with the final Hindi narration script:

```bash
python automation/build_youtube_production_workflow.py \
  --channel devotional \
  --subject "हनुमान जी की भक्ति और साहस" \
  --script path/to/final_hindi_script.txt \
  --output-dir storage/workflows/devotional \
  --aspect 16:9
```

For the motivational channel, use `--channel motivation` and a different output directory. Optional existing artifacts can be supplied with `--assets`, `--image-manifest`, `--subtitles`, `--audio`, `--image-root`, `--timeline`, `--timed-manifest`, `--video`, and `--thumbnail`.

The JSON runbook:
- Lists the exact repository commands and prerequisites for each stage.
- Marks downstream stages blocked until the required files exist, then can be regenerated as production progresses.
- Separates devotional and motivational asset/output paths.
- Provides an image-render dry-run command and a separate explicit `--execute` command.
- Requires the exact final narration audio that generated the SRT before timed scene preparation.
- Keeps publishing at a human-review-only checkpoint.

**Safety boundary:** this is a planner, not an autonomous runner. It does not execute commands or provider calls, render videos, upload, or schedule. The publishing package remains review-only; upload authorization and public visibility remain disabled. Review factual accuracy, cultural sensitivity, visual relevance, licensing, subtitles, audience declaration and synthetic-media disclosure before any publication.

Test:

```bash
python -m unittest automation.tests.test_build_youtube_production_workflow
```


## Production execution checkpoint tracker (Phase 6 — Step 10)

After generating a Step 9 workflow runbook, initialize a separate persistent checkpoint file for that channel:

```bash
python automation/track_youtube_production_checkpoints.py init \
  --workflow storage/workflows/devotional/devotional_workflow.json \
  --state storage/workflows/devotional/devotional_checkpoints.json
```

Use a different workflow and state path for `motivation`. Check progress and the safe resume point:

```bash
python automation/track_youtube_production_checkpoints.py status \
  --workflow storage/workflows/devotional/devotional_workflow.json \
  --state storage/workflows/devotional/devotional_checkpoints.json
```

When a stage has actually been run and its output has been reviewed, record it with one or more evidence files and the human reviewer's identifier:

```bash
python automation/track_youtube_production_checkpoints.py complete \
  --workflow storage/workflows/devotional/devotional_workflow.json \
  --state storage/workflows/devotional/devotional_checkpoints.json \
  --stage creative_brief \
  --evidence storage/workflows/devotional/devotional.assets.json \
  --reviewed-by "reviewer-id" \
  --note "Script, scenes and metadata reviewed"
```

Available stage IDs are `creative_brief`, `scene_images`, `scene_timeline`, `timed_video_task`, `render_video`, and `publishing_review`. Record the actual output file(s) for each stage as evidence. A stage cannot be marked complete when it is blocked in the current runbook, when an earlier stage is incomplete, or when evidence is missing. The tracker stores SHA-256 hashes and detects evidence files that change after approval.

If new artifacts make previously blocked stages available, regenerate the Step 9 runbook and synchronize the checkpoint file:

```bash
python automation/track_youtube_production_checkpoints.py sync \
  --workflow storage/workflows/devotional/devotional_workflow.json \
  --state storage/workflows/devotional/devotional_checkpoints.json
```

Sync preserves only valid, sequentially completed checkpoints. If upstream evidence changes, that checkpoint and all downstream checkpoints are invalidated. Record a failure with `fail --state ... --stage ... --reason "..."`; restart from a stage with `reset --state ... --stage ...`, which clears that stage and every downstream checkpoint.

**Scope and safeguards:** the tracker records evidence and human decisions; it does not execute commands, retry provider calls, render media, authorize uploads, or schedule publication. It keeps each channel's state separate. Keep checkpoint JSON and generated media in local storage, not in Git, and do not include API keys, OAuth tokens or other credentials in evidence notes.

Test:

```bash
python -m unittest automation.tests.test_track_youtube_production_checkpoints
```


## Production performance, cost and quality intelligence (Phase 6 — Step 11)

Combine local checkpoint evidence with optional technical video-quality reports, the existing publishing-outcome report, and a cost ledger containing actual recorded provider charges:

```bash
python automation/build_youtube_production_intelligence.py \
  --checkpoint storage/workflows/devotional/devotional_checkpoints.json \
  --checkpoint storage/workflows/motivation/motivation_checkpoints.json \
  --quality-report storage/quality/devotional_video_quality.json \
  --publishing-report storage/reports/publishing_report.json \
  --cost-ledger storage/reports/provider_cost_ledger.json \
  --output-json storage/reports/production_intelligence.json \
  --output-csv storage/reports/production_intelligence.csv
```

Use only files that actually exist. Omit optional report inputs when unavailable. The cost ledger format is:

```json
{
  "records": [
    {
      "channel": "devotional",
      "stage": "scene_images",
      "provider": "provider-name",
      "amount": 12.5,
      "currency": "INR",
      "source": "provider-invoice"
    }
  ]
}
```

Each amount must be an actual recorded charge from an invoice, provider usage page, or other reliable account record. Do not enter estimated or assumed prices as actual spend. Multiple currencies are kept separate and are never added together.

The report includes:
- Per-channel workflow and stage totals, failed/blocked/pending stages, stale evidence, evidence file counts and file sizes.
- Technical quality outcomes from supplied FFprobe validation JSON reports; a report is assigned to a channel only when its video path includes an explicit `devotional` or `motivation` path segment.
- Publishing package outcomes from the existing local publishing report, kept separate from YouTube audience analytics.
- Optional provider cost totals grouped by channel and currency.
- JSON detail and a channel-level CSV summary.

**Interpretation limits:** without a cost ledger, costs are unknown—not zero. Evidence file sizes are not storage charges. Technical validation does not assess storytelling, cultural accuracy, Hindi pronunciation, subtitle readability, visual quality or retention. Publishing outcomes do not equal views, watch hours, revenue or monetization eligibility. No external APIs are called and no provider prices are inferred.

Test:

```bash
python -m unittest automation.tests.test_build_youtube_production_intelligence
```
