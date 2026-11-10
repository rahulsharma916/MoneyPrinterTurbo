# YouTube Content Calendar Automation

This utility converts a UTF-8 CSV content calendar into a validated batch manifest for MoneyPrinterTurbo. The channel profiles are deliberately separated: use one calendar and one profile per YouTube channel.

## Two independent channel workflows

| Channel | Profile key | Content boundary | Example calendar |
|---|---|---|---|
| Devotional | `devotional` | Bhakti, Hindu deities, epics, mythology, spiritual reflections | [devotional_channel_calendar.csv](examples/devotional_channel_calendar.csv) |
| Motivational | `motivation` | Motivational stories, discipline, mindset, life lessons, original motivational Shayari | [motivational_channel_calendar.csv](examples/motivational_channel_calendar.csv) |

Keep each channel's brand name, logo, voice, thumbnail style, descriptions, playlists, upload defaults, and analytics separate. Do not mix devotional topics into the motivational channel or vice versa. Mythology is part of the devotional channel when it is framed as devotional/epic storytelling.

## Channel configuration (Phase 3)\n\n`channel_configs.json` stores independent identity and production defaults for the two channels: language, Shorts/long-form aspect ratios, voice overrides, creative direction, thumbnail direction, music guidance, SEO defaults, and publishing safeguards. The file contains no credentials. Configure actual channel IDs and voice names only after confirming the correct accounts and provider voices.\n\nValidate the configuration from the repository root:\n\n```bash\npython automation/validate_channel_configs.py\npython -m unittest automation.tests.test_channel_configs\n```\n\nBoth channels intentionally start with publishing disabled, private visibility, mandatory human approval, and an unset `made_for_kids` declaration. Do not change the audience declaration without reviewing the actual video. The account environment-variable names are placeholders; they are not connected to the existing Upload-Post integration yet.\n\n## 1. Apply the correct channel profile

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
