# How this history was made, and how to make it again

This file records exactly how the repository was built: the sources, the commands, the software, the decisions
made by hand, and what an AI model did and did not do. Anyone with Python and git can rebuild it and check it.

## Short version

```sh
git clone https://github.com/lexifina/uk-law-history && cd uk-law-history
python tools/ukhistory.py check --history data/history.json     # every version against legislation.gov.uk now
python tools/ukhistory.py repo  --history data/history.json --repo ../rebuilt
git -C ../rebuilt log --format=%H        # the same law commits, with the same hashes, as this repository
```

On 28 October 2026 the second command reproduced all 11 law commits of this repository byte for byte. Their hashes
are identical, from the first (Royal Assent, 13 March 2014) to the last (9 December 2021).

## Sources

All legal text and all information about changes come from **legislation.gov.uk**, published by The National
Archives under the Open Government Licence v3.0. Nothing was typed in, summarised or rewritten. The build read:

| What | Where | Requests |
| --- | --- | ---: |
| Each provision's current XML, which lists its point-in-time versions | `https://www.legislation.gov.uk/<instrument>/<section or regulation>/<n>/data.xml` | 9 |
| Each point-in-time version's XML | `…/<n>/<version>/data.xml`, where version is `enacted`, `made` or a date | 26 |
| The changes register for each instrument | `https://www.legislation.gov.uk/changes/affected/<instrument>/data.feed?results-count=500&page=<p>` | 3 |
| Each instrument's introduction, for its title and its enacted, made, laid and in-force dates | `…/<instrument>/introduction/data.xml` | 11 |

The data was retrieved on 28 October 2026, at about two requests a second, with the user agent `Lexifina
uk-legislation history (https://github.com/alan-yahya/uk-law-history)`. The repository has since moved to
`lexifina/uk-law-history`, and later builds name that address.

## The build, step by step

These are the commands that made this repository, in order. The build script is `tools/ukhistory.py`. It is the
same file as `scripts/uk-law-git/ukhistory.py` in Lexifina's own repository (git blob
`7b96cdb0d933c668f0330b342683a8bf8b529c77`).

1. `python ukhistory.py build --cache cache2 --out history.json` reads every source above and writes
   `data/history.json`, with sha256 `e6b8e61312942f4b9865c79fe6c6f347e621028b8f390d8191f28d3e65310776`.
2. `python ukhistory.py check --history history.json --cache fresh` fetches every version again from an empty
   cache and compares the text. Its output was `all versions match`.
3. `python -m unittest test_ukhistory.py` ran 13 tests on five saved versions (`tools/fixtures/`). All passed.
4. `python ukhistory.py repo --history history.json --repo uk-law-history --extra …` wrote the 11 law commits, then
   one commit adding the README, the licence, the build script, the tests and the data.
5. `git push -u origin main` published it to GitHub.

The build uses only the Python standard library. It was run with Python 3.12.10 and git 2.46.0 on Windows 11. No
other software is involved, and no network service other than legislation.gov.uk.

## How the text and the commits are derived

Everything below is done by `tools/ukhistory.py`, deterministically. The same input gives the same output.

- **Text.** Each version's XML is read with Python's `xml.etree`.
  - Each numbered unit (subsection, paragraph, sub-paragraph) becomes one line, with its number.
  - Commentary markers and text kept only to show a repeal (`Repeal` elements) are left out.
  - Straight apostrophes become typographic ones, and spaces before punctuation are removed. The dots that stand
    for omitted words are kept.
- **Status.** A provision's status on a date comes from the "coming into force" entries for it in the changes
  register, and from each statutory instrument's own in-force date:
  - Not yet in force
  - In force for specified purposes
  - In force
  - Made, not yet in force
- **Cause.** A version is explained by the register entries for that provision whose in-force date is the
  version's date. The marks in the text and the register entries share one key, so the cause comes from the
  publisher's record, not from a comparison of texts.
- **Kind of change.** Each version is classified by what changed:
  - Royal Assent or made: the first version.
  - Came into force: the status changed.
  - Amended or temporarily amended: the words changed and a register entry explains it.
  - Temporary change ended: the words returned to an earlier version, and the change is credited to the
    temporary instrument it undoes.
  - Modified, words unchanged.
  - Revised text published.
- **Commits.** There is one commit for each day and each instrument that made a change.
  - The author is that instrument, at an address ending `.invalid`.
  - The author and committer dates are noon London time on the day the change came into force. The committer is
    `Lexifina <uk-law-history@lexifina.com>`.
  - The message lists each affected provision, each register entry with the publisher's annotation, the
    point-in-time source, and the trailers `In-force:`, `Enacted:` or `Made:`, `Affecting:` and `Effect-id:`.

## Decisions made by hand

These choices were made when the tool was written, after looking at the data. They are in the code and can be
changed there.

1. **Commits are dated the day a change came into force**, not the day it was made or published, at noon London time
   so the date reads the same in any time zone.
2. **A reversion ignores trailing punctuation.** When the temporary change to reg. 13(3) ended on 25 September 2020,
   legislation.gov.uk's text also gained a full stop that the earlier versions lack. That is treated as the old
   words returning.
3. **A statutory instrument brings itself into force**, so the register has no separate entry for it. The build
   adds one, dated the instrument's own in-force date and credited to the instrument, regulation 1.
4. **Register keys lose their `key-` prefix.** legislation.gov.uk writes them as `key-` and 32 hex digits. GitHub's
   push protection blocked the first push because it took them for API keys of an email service. The history keeps
   the 32 digits only.
5. **The test fixtures are trimmed.** The `UnappliedEffects` block was removed from two of the five saved XML files,
   for the same reason. The tests do not use it.
6. **Effect types are kept as the publisher writes them** ("words omitted", "power to modify conferred (temp.)").
   The reader on lexifina.com puts them in plain words. The repository does not.

## What an AI model did

This repository was built on 28 October 2026 in **Claude Code**, Anthropic's coding tool, by the model **Claude Opus
5.5** (model id `claude-opus-5-5`), working from a goal set by the user at Lexifina. The goal was to build a git
history of UK law with proper dates, after researching projects such as c3e/grundgesetz, using the data Lexifina
already had, with a public repository and a reader on lexifina.com.

The model:

- **Researched the prior art.** It did this with a research sub-agent of the same model, which read the
  repositories, their commits through the GitHub API, and legislation.gov.uk's documentation. The findings are in
  the next section.
- **Read the legislation.gov.uk XML** to work out how versions, changes and dates are recorded.
- **Wrote all the code and text in this repository:** `tools/ukhistory.py`, `tools/test_ukhistory.py`, the README,
  this file and the licence file, and chose the design described in them.
- **Ran the commands listed above** and checked the results: the tests, the re-fetch, a rebuild compared hash for
  hash, and the files on GitHub.

The model did **not**:

- **Write or edit any legal text.** Every word of every provision, every date and every description of a change is
  copied by the script from legislation.gov.uk's XML.
- **Take part in building the history.** No AI model is called when the history is built or checked. Rebuilding it
  needs no model and gives the same result.

The user decided what was in scope and when the repository was made public or private. The work was not reviewed
line by line by a lawyer. As the README says, for anything that matters the legislation itself should be read.

## The research behind the design

These projects were studied before the design was chosen (checked 28 October 2026):

- [c3e/grundgesetz](https://github.com/c3e/grundgesetz): one commit per amending law, dated when it was signed.
  Dates before 1970 are clamped.
- [bundestag/gesetze](https://github.com/bundestag/gesetze): snapshots at the time of import, not backdated. It
  stopped in 2013.
- [Archéo Lex](https://github.com/Legilibre/Archeo-Lex): one commit per consolidated version, dated the day it came
  into force. Future versions are on a separate branch.
- [legalize-uk](https://github.com/legalize-dev/legalize-uk): about 3,970 UK Acts, with one commit per amendment
  date and a generic author.

legislation.gov.uk's own [data documentation](https://github.com/legislation/data-documentation) explains point-in-time
versions, the changes register, unapplied changes and the reuse licence.

From these, this history takes the in-force date from Archéo Lex and the bootstrap from the as-enacted text from
legalize-uk. It adds:

- the instrument as author, so `git blame` names the law
- the register's key on every commit
- coming into force as a change of status
- temporary changes and their end as commits of their own
- the build script in the repository, so it can be checked and rebuilt

## Changes to this history after it was published

- **28 October 2026.** A later commit added `tools/ukhistory.py on <date> <path>`, which reads a provision on a date
  by its `In-force` trailer, so the answer does not depend on the reader's time zone. It also made `repo` refuse a
  non-empty directory, because running it twice had added a second copy of the history. The repository moved from
  `alan-yahya` to the `lexifina` organisation the same day.
- **28 October 2026.** The repository was made public, then made private on the user's instruction. This file was
  added in a commit of its own, so that the commits already published, which other repositories refer to, keep their
  hashes. A full rebuild puts this file in the documentation commit.
