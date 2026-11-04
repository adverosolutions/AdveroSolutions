# Instantly subject A/B apply log

- Applied: 2026-09-29 16:11:02 CDT
- Scope: exactly two campaigns; no other campaigns touched.
- Backup directory: `/home/box/advero/state/backups/instantly_campaigns_20260929_subject_ab/`
- Payload: PATCH with unchanged full `email_list` and full `sequences`; Step 1 duplicated A body exactly into Variant B; Step 2 preserved.

## cleaning_trigger (f347604e-48c7-4813-831c-dc7b9d4b50ae)
- Result: OK
- patch_status: `200`
- verify_status: `200`
- email_list_count: `12`
- body_len: `986`
- verified_variant_count: `2`
- verified_subjects: `['{{firstName}}, question', 'walkthroughs']`
- verified_body_lengths: `[986, 986]`
- verified_step2_variant_count: `1`

## cleaning_reactivation (8086b41e-b546-4b36-9fa0-2d01f5cc119a)
- Result: OK
- patch_status: `200`
- verify_status: `200`
- email_list_count: `12`
- body_len: `763`
- verified_variant_count: `2`
- verified_subjects: `['{{firstName}}, question', 'cancelled accounts']`
- verified_body_lengths: `[763, 763]`
- verified_step2_variant_count: `1`

