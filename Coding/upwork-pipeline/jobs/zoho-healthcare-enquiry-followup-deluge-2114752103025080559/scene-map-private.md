# Scene map (private), pick 8
Sample path: invented patient Rosa Ellery, enquiry ENQ-30917, coordinator Jordan Pike, task "Call back new patient" due 11:40 AM. No health details.
1. enquiry-logic (workbench architecture, ~45 s). Purpose: the workflow logic the post asks for. New fact: run-once check first, Deluge cleans details, task, status rule, alert. Evidence: 6 nodes + rule setup panel (trigger create/edit, run-once field, bad-phone branch, owner).
2. enquiry-record (workbench record, ~35 s). Purpose: show the Deluge validation/update and resulting record. New fact: messy form input vs cleaned record, status, owner, timeline of task and alert.
3. run-twice-test (workbench outcome, ~35 s). Purpose: prove the twice-run guard with a sample test. Evidence: second save at 9:52 skipped, 1 task, 1 alert, 1 pass, test Passed.
Close: 3 directional metrics (enquiries with no task, repeat tasks/alerts, time to first callback), baseline note, 15-minute CTA.
