# YouTube Content Calendar Automation

This utility converts a UTF-8 CSV content calendar into a validated batch manifest for MoneyPrinterTurbo. The channel profiles are deliberately separated: use one calendar and one profile per YouTube channel.

## Two independent channel workflows

| Channel | Profile key | Content boundary | Example calendar |
|---|---|---|---|
| Devotional | `devotional` | Bhakti, Hindu deities, epics, mythology, spiritual reflections | [devotional_channel_calendar.csv](examples/devotional_channel_calendar.csv) |
| Motivational | `motivation` | Motivational stories, discipline, mindset, life lessons, original motivational Shayari | [motivational_channel_calendar.csv](examples/motivational_channel_calendar.csv) |

Keep each channel's brand name, logo, voice, thumbnail style, descriptions, playlists, upload defaults, and analytics separate. Do not mix devotional topics into the motivational channel or vice versa. Mythology is part of the devotional channel when it is framed as devotional/epic storytelling.

## Channel configuration (Phase 3)\n\n`channel_configs.json` stores independent identity and production defaults for the two channels: language, Shorts/long-form aspect ratios, voice overrides, creative direction, thumbnail direction, music guidance, SEO defaults, and publishing safeguards. The file contains no credentials. Configure actual channel IDs and voice names only after confirming the correct accounts and provider voices.\n\nValidate the configuration from the repository root:\n\n```bash\npython automation/validate_channel_configs.py\npython -m unittest automation.tests.test_channel_configs\n```\n\nBoth channels intentionally start with publishing disabled, private visibility, mandatory human approval, and an unset `made_for_kids` declaration. Do not change the audience declaration without reviewing the actual video. The account environment-variable names are placeholders; they are not connected to the existing Upload-Post integration yet.\n\n## Channel-aware production preparation (Phase 4)

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
