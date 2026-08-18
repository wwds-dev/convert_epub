# Ebook Converter — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

---

## v2 — current

- [ ] `P1` `bug` `@ai` The format lists are pinned rather than queried. `formats.missing_from_calibre()` re-checks them only when Calibre's packages happen to be importable — make that check run on a schedule, or on version change, so a Calibre update doesn't silently hide a new format.
- [ ] `P1` `feature` `@ai` Batch conversion of a whole folder with a per-file result list, rather than one file at a time
- [ ] `P2` `feature` `@ai` Remember the last input and output folder between launches
- [ ] `P2` `testing` `@ai` The integration suite skips entirely when Calibre is absent — make that skip loud, so a broken install doesn't look like a green run
- [ ] `P2` `bug` `@me` Confirm Calibre's `ebook-convert` is on `PATH` for a Finder-launched app after each Calibre upgrade
- [ ] `P3` `design` `@ai` Show the conversion command that will run, for anyone who wants to reproduce it in a terminal
- [ ] `P3` `docs` `@ai` Document which format pairs are lossy, since the picker treats them all alike

## v3 — later

- [ ] `P2` `feature` `@ai` Metadata editing (title, author, cover) before conversion
- [ ] `P3` `feature` `@ai` Watch-folder mode: drop a file in, get a converted one out
- [ ] `P3` `feature` `@ai` Conversion presets per target device
