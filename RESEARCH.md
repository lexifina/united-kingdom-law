# UK law in git: research and decisions (28 October 2026)

## Prior art, checked on the repositories themselves

- **c3e/grundgesetz.** One commit per amending law, authored by the head of state who signed it, dated the signing
  date at Berlin midnight. Trailers carry `Announced:` and repeatable `Effective-since:`. Dates before 1970 are
  clamped to 1970-01-01 and the real ones kept in trailers. One Markdown file per article. Last pushed 2018.
- **bundestag/gesetze.** Current-text snapshots, committed at import time and not backdated. It stalled after 2013
  because it needed manual work for each Federal Law Gazette (Bundesgesetzblatt).
- **Archéo Lex (France).**
  - One commit per consolidated version, dated the day the version came into force. The author is `Législateur <>`.
  - Future versions go on a `-futur` branch, and a repeal is a commit that removes the file.
- **legalize-uk.**
  - About 3,970 Acts as files named `ukpga-1998-42.md`.
  - Each Act starts with an as-enacted commit, then has one commit per in-force amendment date.
  - The author is a generic bot.
  - The repository is about 8 GB, and GitHub's per-file history API returns 500 on it.
- **DC Council law-xml.** Daily batches committed by staff, with real dates.
- **The National Archives' GitHub organisation.** It has the CLML schema and data documentation, but no git history
  of legislation.

## legislation.gov.uk

- A provision's `data.xml` lists every point-in-time version as `atom:link rel="http://purl.org/dc/terms/hasVersion"`.
  These are `enacted` or `made` plus one dated version for each day an amendment or commencement came into force.
- The text marks changes with `Addition`, `Substitution` and `Repeal` (where `RetainText` shows a repeal that is kept
  on screen) and `CommentaryRef`. The commentary types are:
  - F: textual amendment
  - I: commencement
  - C: modification
  - E: extent
- `/changes/affected/<instrument>/data.feed` is the changes register. Each effect gives its type, the affecting
  instrument and provisions, `InForceDates` with qualification, and the `Applied` and `RequiresApplied` flags. Its
  `EffectId` is the same key as the `CommentaryRef` in the text, so every mark has a structured cause.
- Unapplied effects (`RequiresApplied` true and `Applied` false) are the publisher's editorial lag. Its target is
  three months.
- Required attribution: "© Crown and database right. Derived from content available under the Open Government
  Licence v3.0 from legislation.gov.uk." Do not imply endorsement. Fair use is no more than 3,000 requests per five
  minutes, with a named user agent.
- Pitfalls:
  - The base date is 1 February 1991; no history before it, and dated requests silently redirect to the base-date
    version.
  - Territorial versions run in parallel.
  - The publisher tidies punctuation between versions; for example, reg. 13(3) gained a full stop when the 2020
    change ended.

## Decisions

1. A commit is dated the day the change came into force, at noon London time, so it reads as the same day in any
   time zone. The enacted or made date goes in a trailer, `Enacted:` or `Made:`.
2. One commit per day per instrument that made the change. The author is that instrument, at
   `<uri>@legislation.invalid`, so `git blame` names the law. This matches us-code-history (`pl-…@public-law.invalid`).
3. Every point-in-time version is a commit, including versions where the words did not change:
   - commencement changes the `status:` line;
   - a modification that leaves the words alone is still a commit, described in its message.
4. A temporary change and its end are separate commits. A reversion is detected by matching an earlier version,
   ignoring trailing punctuation, and it is credited to the temporary instrument it undoes.
5. Every commit carries the effect IDs from the register. The `key-` prefix is dropped, because GitHub push
   protection takes `key-` plus 32 hex digits for a Mailgun API key.
6. One file per provision, at the path of its legislation.gov.uk URI. Each subsection, paragraph and sub-paragraph is
   on its own line.
7. The build script uses only the standard library and is shipped in the public repository.
   `check` re-fetches every version and compares it with the history.

## Not yet done

- Prospective versions, on a separate branch.
- Territorial versions.
- Notices made under powers of modification.
- More provisions.
