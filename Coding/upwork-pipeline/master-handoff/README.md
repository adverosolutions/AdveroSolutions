# Maintained source for Lorenzo’s Upwork master

Start at `00-MASTER.md`. This folder is the versioned source, not a new demo
batch. It consolidates the saved conversation decisions and links them to the
actual UI image evidence, templates, operating steps and locked proposal.

Build the self-contained local reading/transfer package:

```sh
/usr/bin/python3 build_handbook.py
```

Outputs:

- Repository-root `UPWORK_MASTER.html`: visible launcher.
- Pipeline `.local/upwork-master-handbook/START_HERE.html`: browser-friendly handbook.
- Pipeline `.local/upwork-master-handbook.zip`: private transfer ZIP.

The builder uses explicit source roots, excludes job folders/live queue/credentials,
checks frozen preview hashes and verifies the exported inventory. It does not run
models, fetch the web, start a server, mutate the queue or open the browser.
`02-UI-REFERENCE-GUIDE.md` is generated from saved research plus the current
candidate overlay; edit its generator/evidence, not a generated export.
`04-LOCKED-PROPOSAL-AND-FACTS.md` is generated verbatim from section 6 onward of
`UPWORK_PROCESS.md` into the package.

Every source change that should reach another model needs a refreshed export.
The ZIP is private and is deliberately not committed; Git tracks its reproducible
source. Package verification/build checks are recorded in `VERIFICATION.md`.
They do not establish native production approval or a pass by another model.
