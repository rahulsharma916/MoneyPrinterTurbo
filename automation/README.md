# YouTube Content Calendar Automation

This first integration milestone adds a small, dependency-free utility that converts a CSV content calendar into a batch manifest accepted by MoneyPrinterTurbo's existing CLI. It does not modify the video-generation engine and does not upload or publish anything.

## 1. Prepare your calendar

Start from [examples/hindi_youtube_calendar.csv](examples/hindi_youtube_calendar.csv). One row is one video. Keep the CSV in UTF-8 encoding.

Required per row: either `video_subject` or `video_script`.

Useful columns:

| Column | Purpose | Example |
| --- | --- | --- |
| `video_subject` | Topic / subject | `हनुमान जी से मिलने वाली 5 सीख` |
| `video_script` | Ready narration script (optional) | Hindi script text |
| `video_aspect` | Output ratio | `9:16` Shorts, `16:9` long-form |
| `video_language` | Language / TTS locale | `hi-IN` |
| `video_clip_duration` | Target stock clip duration in seconds | `4` |
| `video_count` | Variations to generate | `1` |
| `voice_name` | Configured TTS voice | Leave blank to use app defaults |
| `bgm_type` | Background music setting | `random` |
| `subtitle_enabled` | Enable subtitles | `true` / `false` |
| `video_source` | Material provider | `pexels` |

Additional supported columns are the corresponding scalar fields from `VideoParams`: `video_terms` (separate terms with semicolons), `video_fit_mode`, `image_motion`, `video_concat_mode`, `video_transition_mode`, `video_clip_speed`, `match_materials_to_script`, `custom_audio_file`, `voice_volume`, `voice_rate`, `bgm_file`, `bgm_volume`, subtitle styling fields, `paragraph_number`, `video_script_prompt`, and `custom_system_prompt`. Unknown columns are rejected to prevent silent typos.

## 2. Generate and validate the manifest

From the repository root:

```bash
python automation/content_calendar_to_batch.py automation/examples/hindi_youtube_calendar.csv
```

Validate without writing a file:

```bash
python automation/content_calendar_to_batch.py automation/examples/hindi_youtube_calendar.csv --check
```

By default, the tool writes a UTF-8 JSONL file beside the CSV. To create a JSON array instead:

```bash
python automation/content_calendar_to_batch.py automation/examples/hindi_youtube_calendar.csv --format json
```

## 3. Generate videos with MoneyPrinterTurbo

Review the generated manifest, confirm API keys / providers / voice configuration in `config.toml`, then run:

```bash
python cli.py --batch-file automation/examples/hindi_youtube_calendar.jsonl
```

The CLI's own generation settings and provider credentials still apply. The generator enforces the current CLI manifest limits (100 tasks and 1 MiB) and validates basic types and enumerated values before writing.

## Important safeguards

- No automatic publishing, scheduling, or YouTube account connection is performed by this utility.
- Review scripts, visual relevance, music licensing, subtitles, and the final video before uploading.
- The sample uses `hi-IN` as a language hint; choose a voice actually available in your configured TTS provider.
- Keep local audio paths relative to the manifest location, as the CLI resolves manifest-relative media paths.


## 4. Apply a Hindi channel content profile

Phase 2 adds reusable prompt profiles for four content pillars: devotional, mythology, motivation, and Shayari. These profiles guide the existing script-generation workflow; they do not bypass the configured language model or guarantee factual accuracy.

Apply a profile to a copy of your calendar:

```bash
python automation/apply_content_profile.py automation/examples/hindi_youtube_calendar.csv --profile devotional
```

Other profile names: `mythology`, `motivation`, and `shayari`. The output is a new CSV file with the profile prompt appended to each row's `video_script_prompt`; existing row-specific instructions are preserved.

Then create the batch manifest from the enriched CSV:

```bash
python automation/content_calendar_to_batch.py automation/examples/hindi_youtube_calendar.devotional.csv
```

You can choose an explicit output path with `-o`. The catalog lives in [content_profiles.json](content_profiles.json), and the applicator is [apply_content_profile.py](apply_content_profile.py).

## 5. Existing native capabilities discovered in MoneyPrinterTurbo

The repository already includes script generation, platform-specific social metadata generation, and Upload-Post cross-posting (including YouTube configuration). Phase 2 will extend and orchestrate these existing capabilities rather than build duplicate services. Account credentials must be configured by the user. Keep uploads disabled until the video, audience declaration, privacy, synthetic-media disclosure, and metadata have been reviewed.
