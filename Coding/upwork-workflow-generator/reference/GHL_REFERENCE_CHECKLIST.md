# GHL reference import: what to check

**Before anything else:** create a NEW workflow for this import and import into that, never into an existing workflow. Keep it in **Draft**. **Never publish it.** It has SMS, email, call, webhook and review-request steps, and its triggers fire on the live `call-booked` and `call-cancelled` tags, so a published copy would message and call real contacts.

File: `~/Desktop/GHL-Imports/REFERENCE-all-step-types.ghl.json`, compiled from `examples/ghl_reference_all_types.json` with the id map `upwork_gen/catalog/ghl_ids_ebyNANPagaK7ycf1pfge.json`. Rebuild it with:

```
cd ~/Desktop/AdveroSolutions/Coding/upwork-workflow-generator && python3 -m upwork_gen.compile_ghl examples/ghl_reference_all_types.json ~/Desktop/GHL-Imports/REFERENCE-all-step-types.ghl.json
```

Every generated id (workflow, node, branch, goal condition, trigger) and every timestamp is new on each rebuild; everything else is the same each time.

Import it into the new, empty Draft workflow with the Backup & Audit extension. Open every step. On each one, check that it has an icon, has no orange dot, and has its panel fields filled. If something is wrong, set it by hand as the table below says, then save (Save only, not Publish). Once all steps are right, export the workflow with the extension to `reference/ghl_export_reference_all_types.json`. Every shape in that export is then verified, and the tests get locked to it.

Scope: only the tag added and tag removed triggers are in this pass. The other trigger types the compiler emits (form, survey, reply, contact created, pipeline stage, opportunity, appointment, inbound webhook, missed call, invoice, order, birthday, task) are out of scope for this pass: their type strings are research only, and one wrong trigger type can make the extension's trigger write fail for the whole reference. The appointment trigger type (`appointment` vs `appointment_status`) is UNVERIFIED.

Status key: **V** = GHL's builder saved this shape in a real export after the step was checked by hand (verified). **F** = imported cleanly on 2026-09-22. **R** = research only, not saved by GHL yet. **UNVERIFIED** = a specific behaviour still to test in GHL.

## What the 2026-09-23 export showed

`reference/ghl_export_reference_all_types.json` was captured at 04:51 after Lorenzo checked every step, re-added the broken ones by hand and saved (workflow `updatedAt` 04:39:44). It has both triggers and all 29 steps. The compiler now matches it (`TestReferenceExportLock`). An earlier export, taken before the save, is kept at `.tmp/upwork-overhaul-baselines/ghl_export_reference_all_types.first_roundtrip.json`.

- **18 AI step:** GHL's step is type `chatgpt` ("GPT powered by OpenAI"). Its attributes are `type`, `apiKey` "", `event` "simple-prompt", `model` "gpt-5-mini", `temperature` "0.2" (a string), `promptText` (the prompt), `actionType` "custom", an `actionParams` block, `memoryKey` "", and the two `exclude...FromHistory` flags. The step also has `stepIndex` 1. The compiled `gpt_powered` with `prompt` did not survive import. The compiler now emits GHL's whole shape. Model and temperature default to the export's values unless the spec sets `model` / `temperature`.
- **21 Send Review Request:** GHL's step is type `review_request` with `{type, overrideReviewLink: "default", review_type: "sms"}`. The compiled `send_review_request` with `{}` was broken. The compiler now emits GHL's shape. `review_type` "sms" is the export's value, because the spec has no channel param.
- **Adopted** (the panel needs these):
  - Task: `dueDate` and `assignedTo` ("contact.assigned_user"), and the step-level `workflowsActionType` INTERNAL and `stepIndex`. The task had no icon and no due date or assignee after the first import.
  - Update contact field: GHL's `fields` list keyed by the field id from the id map. `type` is "string", as the export shows for a text field.
  - Assign to user: `user_list` plus the round-robin keys. User ids come only from the id map (`user:<name>`), which has no user entries yet. With no known user, `user_list` stays empty and the compiler warns.
- **Not adopted** (GHL defaults the first import worked without):
  - Task: `__customInputs__`.
  - Add note: a colour and an attributes `type`. GHL's own 2026-09-21 export has `color: null`.
  - Add to workflow: `input_trigger_params` and an attributes `type`.
- **Unchanged since import, now V:** the triggers and every other step were checked and saved by GHL as compiled. GHL adds `schedule_config: {}` to triggers; the import works without it. `pipelineName`, `valueName`, `targetNodeName`, `fieldName`, `user_listNames` and `location_name` are the extension's name mirrors of ids, and its importer strips them.
- **25 Go To:** GHL's keys are `targetNodeId` + `type: "goto"`, and the compiler now emits them. The target in the export is **01 Add Tag call-booked** because Lorenzo left GHL's default target and did not try step 27. **Cross-branch Go To target: UNVERIFIED.** The compiler keeps the spec's target, and warns when a Go To points into an If/Else branch it is not inside.

The steps for the next pass are in **Next pass** below the table.

| Step | Status | Look at | If wrong, set by hand | Export 2026-09-23 |
|---|---|---|---|---|
| T1 Trigger Tag Added Filter call-booked | V | Filter shows "Tag Added is call-booked" (last time it said "No filters applied") | Add the filter Tag Added = call-booked. If the trigger itself is missing after import, add it by hand (tag added: call-booked) | GHL kept the condition tagsAdded / index-of-true / call-booked; adds `schedule_config: {}` |
| T2 Trigger Tag Removed Filter call-cancelled | V | Filter shows "Tag Removed is call-cancelled" | Add the filter Tag Removed = call-cancelled. If the trigger itself is missing after import, add it by hand (tag removed: call-cancelled) | GHL kept the condition tagsRemoved / index-of-true / call-cancelled; adds `schedule_config: {}` |
| 01 Add Tag call-booked | V | Tag chip call-booked | Pick call-booked | Saved as compiled |
| 02 Remove Tag call-cancelled | V | Tag chip call-cancelled | Pick call-cancelled | Saved as compiled |
| 03 Send SMS Body Filled | V | Message box has the REFERENCE SMS text | Paste the text | Saved as compiled |
| 04 Send Email Subject and Body Filled | V | Subject and email editor both filled | Paste the body into the editor | Saved as compiled, `body` included |
| 05 Wait 2 Days | V | Wait shows 2 Days | Set 2 Days | Saved as compiled |
| 06 Create Opportunity in Call Booked | V/F | Pipeline is Call Booked Pipeline, stage is Call Booked, name is filled | Pick the pipeline and stage | Saved as compiled |
| 07 Update Opportunity to Cancelled | V | Icon present, pipeline is Call Booked Pipeline, stage is Cancelled, status is open | Pick the pipeline, stage and status | Saved as compiled (`pipelineName`, `valueName` are exporter mirrors) |
| 08 Wait 1 Hour | V | Wait shows 1 Hour (it was blank when the unit was "hours") | Set 1 Hour | Saved as compiled, unit `hour` |
| 09 Internal Notification SMS to Assigned User | V | Type is SMS, recipient is the assigned user, message filled | Set type SMS, user Assigned, paste the text | Saved as compiled |
| 10 Internal Notification Email to Assigned User | V | Type is Email, recipient is the assigned user, subject and body filled | Set type Email, user Assigned, subject, body | Saved as compiled |
| 11 Internal Notification In-App | V | Type is Notification, title and body filled | Paste the title and body | Saved as compiled |
| 12 Add Task Due in 1 Day | V | Icon present (it was missing before), title and description filled, due in 1 day, assigned user | Set the due date and assignee. This is the most likely one to need fixing | GHL added `dueDate`, `assignedTo`, `workflowsActionType`, `stepIndex` (adopted) and `__customInputs__` (not adopted) |
| 13 Manual Action Call as Add Note | V | Add Note step with the title and note text | Paste the text. For a real Manual Action, swap the step and note what the export shows | GHL set a colour and `type` (not adopted: GHL's 2026-09-21 export has color null) |
| 14 Call With Whisper | V | Whisper text filled, timeout is 25 s | Paste the whisper, set 25 s | Saved as compiled |
| 15 Update Contact Field Call Notes | V | Field is Call Notes, value is filled | Pick Call Notes, paste the value | GHL's shape is a `fields` list keyed by the field id (adopted; id from the id map). Number/date field type UNVERIFIED |
| 16 Assign to User Round Robin | V | Round robin across users | Pick round robin and the users | GHL's shape is `user_list` + round-robin keys (adopted); user ids only from the id map, none there yet. Two or more users UNVERIFIED |
| 17 Webhook POST | V | Method is POST, URL is example.com/ghl-reference-test | Set the method and URL | Saved as compiled |
| 18 AI Step Prompt Filled | V | GPT step with the prompt filled | Paste the prompt | Re-added by hand: type `chatgpt`, prompt in `promptText`, model gpt-5-mini, temperature "0.2" (adopted in full) |
| 19 Add to Workflow Sales Request Follow-Up | V | Target is "Your Sales Request Follow-Up System" | Pick that workflow | Saved as compiled; GHL added `input_trigger_params` and `type` (not adopted). Renamed by hand |
| 20 Remove from Workflow Sales Request Follow-Up | V | Icon present, target is "Your Sales Request Follow-Up System" | Pick that workflow | Saved as compiled |
| 21 Send Review Request | V | Icon present, a Send Review Request step with no orange dot | Replace it with a Send Review Request step and note what its panel asks for | Re-added by hand: type `review_request`, `overrideReviewLink` default, `review_type` sms (adopted) |
| 22 Goal Tag Added call-cancelled | V | "Select type of goal" shows Added Contact Tag = call-cancelled, and there is no orange dot | Pick Added Contact Tag, then call-cancelled, then If not met: End | Saved as compiled (`add_contact_tag`, action exit) |
| 23 If Else Has Tag call-booked | V | Branch "Has call-booked" has the condition Tags includes call-booked; the None branch exists | Add the condition Contact Details > Tags > Includes > call-booked | Saved as compiled, tag condition included |
| 24 Yes Branch Update Opportunity to Showed | V | Same checks as step 07, but the stage is Showed | Same fixes as step 07 | Saved as compiled, as 07 |
| 25 Yes Branch Go To Step 27 | V keys; cross-branch target UNVERIFIED | Go To icon, target is step 27 | Pick step 27 as the target | GHL's keys are `targetNodeId` + `type: "goto"` (compiler matches). Target left at GHL's default, step 01; step 27 not tried. Next pass: try to pick step 27, save, note whether GHL allowed it |
| 26 No Branch Remove Tag call-booked | V | Sits in the None branch, tag is call-booked | Pick call-booked | Saved as compiled |
| 27 No Branch Send SMS Last Step | V | Last step in the None branch | Paste the text | Saved as compiled |
| 28 End Nothing After Step 27 | n/a | Nothing appears after step 27 | Delete anything that follows it | Nothing after step 27 |

## Next pass

Same rules as the first pass: a NEW workflow, kept in Draft, never published.

1. Rebuild `~/Desktop/GHL-Imports/REFERENCE-all-step-types.ghl.json` with the rebuild command at the top of this file, so the file carries the shapes adopted from the 2026-09-23 export.
2. Create a NEW, empty Draft workflow and import the rebuilt file into it with the Backup & Audit extension.
3. Confirm these steps need no hand fix, which is what the adopted shapes should give. Open each one and check it has an icon, no orange dot, and its panel fields filled:
   - **12 Add Task Due in 1 Day:** due in 1 day, assignee is the contact's assigned user.
   - **15 Update Contact Field Call Notes:** field is Call Notes, value filled.
   - **16 Assign to User Round Robin:** the step imports, but it will show **no user** until `user:<name>` entries exist in the id map (`upwork_gen/catalog/ghl_ids_ebyNANPagaK7ycf1pfge.json`). An empty user list here is expected, not a failure.
   - **18 AI Step Prompt Filled:** a GPT step with the prompt filled, model gpt-5-mini, temperature 0.2.
   - **21 Send Review Request:** a Send Review Request step with no orange dot.
   Note any of them that still needed a hand fix, and what was fixed.
4. Open step **25 Yes Branch Go To Step 27** and try to pick step **27 No Branch Send SMS Last Step** (it is in the other branch) as the target. Note whether GHL allowed it.
5. Save (Save only, not Publish), reload the page, and check that step 25's target and the steps above kept their values.
6. Export the workflow again with the extension to `reference/ghl_export_reference_all_types.json`, and note the capture time here.

Still open after this pass: an Update Contact Field on a number or date field (only a text field has been saved so far) and an Assign to User with two users (only one has been saved).
