# Git for UK law

The text of nine provisions of UK legislation on education, health and care plans, with a commit for each instrument on each day its changes to them took effect, from Royal Assent in 2014 to today. **Each commit is a law taking effect.** Its author is the Act or statutory instrument that made the change, and its date is the day the change came into force.

So the questions a lawyer asks of a provision become git commands:

| The question | The command |
| --- | --- |
| What did reg. 13 say on 1 June 2020? | `git show $(git rev-list -1 --before="2020-06-01 23:59" main):uksi/2014/1530/regulation/13.md` |
| Was s. 37 in force on 1 June 2014? | `git show $(git rev-list -1 --before="2014-06-01 23:59" main):ukpga/2014/6/section/37.md \| grep status` |
| Which law wrote each provision? | `git blame ukpga/2014/6/section/37.md` |
| What changed between two dates? | `git diff $(git rev-list -1 --before=2015-01-01 main) $(git rev-list -1 --before=2021-01-01 main)` |
| Everything one instrument changed | `git log -p --author="S.I. 2020/471"` |
| Every change to a provision | `git log -p -- uksi/2014/1530/regulation/13.md` |

If you would rather not use a terminal, the same history has a reader at **[lexifina.com/watch/uk-law](https://lexifina.com/watch/uk-law)**: pick a date and read the text in force on it, with the status, the instrument behind each change, and the words that read differently today marked.

## What is here

| Instrument | Provisions | Versions | Reader |
| --- | --- | ---: | --- |
| [Children and Families Act 2014](ukpga/2014/6/section/) (2014 c. 6) | ss. 19, 21, 36, 37 and 42 | 15 | [Read it](https://lexifina.com/watch/uk-law/ukpga/2014/6) |
| [The Special Educational Needs and Disability Regulations 2014](uksi/2014/1530/regulation/) (S.I. 2014/1530) | regs. 6, 11, 12 and 13 | 11 | [Read it](https://lexifina.com/watch/uk-law/uksi/2014/1530) |

These are the provisions that govern an EHC plan: assessing a child's needs, what the plan must contain, the timescales for issuing it, and the duty to secure the provision it specifies. The record starts with them because they are what we use; more will follow.

Each provision is one Markdown file at the path of its legislation.gov.uk address, so `uksi/2014/1530/regulation/13.md` is [legislation.gov.uk/uksi/2014/1530/regulation/13](https://www.legislation.gov.uk/uksi/2014/1530/regulation/13). Each subsection, paragraph and sub-paragraph is one line, so `git blame` names an instrument for each of them. A short header gives the provision's status on that date, its extent, and the point-in-time version on legislation.gov.uk that the text is taken from.

## The date we use

A UK change has several dates. An Act is enacted on Royal Assent. A statutory instrument is made, then usually laid before Parliament, and comes into force on a date it sets or that a later order sets. The changes it makes can come into force on different days, for different purposes, or only for a time.

Commits are dated on the day a change **came into force**, because that is the date that decides which text governs a set of facts. legislation.gov.uk publishes a new point-in-time version of a provision on each day an amendment or commencement comes into force, and every one of those versions is a commit here. Each commit message carries the other dates (`Enacted:` or `Made:`) of the instrument that made the change. Commits are timed at noon, London time, so the date reads the same in any time zone.

Coming into force is part of the history. An Act's sections usually do nothing on Royal Assent. Section 37, on EHC plans, was enacted on 13 March 2014, came into force for some purposes on 1 April 2014 and fully on 1 September 2014. Each step is a commit that changes the `status:` line, so the text on any date says whether it was law on that date.

Temporary changes are commits too, and so is their end. During the pandemic, reg. 13(3) was amended from 1 May to 25 September 2020 so that a reason relating to coronavirus (reg. 10(4)(e)) could excuse a local authority from the 20-week deadline for issuing a plan. `git log -p -- uksi/2014/1530/regulation/13.md` shows the change on the day it took effect and the old words returning on the day it lapsed, both authored by S.I. 2020/471.

## How it is checked

Every version is the publisher's own text. The text of each commit is legislation.gov.uk's point-in-time version for that day, and each file's `source:` line links it. `python tools/ukhistory.py check` fetches every version again and compares it with the history.

Every change is explained by the publisher's own record. legislation.gov.uk keeps a register of every change made to a piece of legislation: what kind of change it is, which provision of which instrument made it, and when it came into force. The marks in the published text and the entries in that register share a key, and each commit carries it as `Effect-id:` (legislation.gov.uk writes it with a `key-` prefix, left off here because secret scanners mistake it for an API key), so a commit's explanation comes from the register and not from comparing texts. The publisher's annotation for each change is quoted in the commit message.

The register also says which changes the publisher has **not yet applied** to the text. Changes are usually applied weeks or months after they come into force, and until then the latest revised text can be out of date. The build lists every unapplied change to these provisions in the data. On the date of this build there were none.

## What "author" means here

The author of a line is the **instrument** that gave it its current words: the Act as enacted, or the instrument that last amended it. The author of a commencement is the commencement order, or the instrument itself where it sets its own date. It is not the minister who made the instrument or the department that drafted it. Authors' addresses end in `.invalid`, because legislation has no email address.

## What it does not show

- **Changes that leave the words alone.** A provision can be modified, disapplied or applied with modifications without its words changing. These changes are commits with the same words and are described in the message. Between 2020 and 2021 the Coronavirus Act 2020 gave the Secretary of State a temporary power to modify the duty in s. 42 by notice. The power and its expiry are both commits, but the notices issued under it were not legislation and are not recorded.
- **Transitional and saving provisions.** For some children, orders kept the old law on statements of special educational needs running alongside these provisions. The messages name those orders. The text does not show who they applied to.
- **Different versions for different parts of the UK.** Part 3 of the Children and Families Act 2014 extends to England and Wales and applies in England. Each file gives its extent. Where legislation.gov.uk keeps separate versions for different countries, this history does not yet follow them.
- **Changes not yet in force.** Prospective amendments are not committed until they come into force. None were outstanding for these provisions when this was built.
- **Court decisions and guidance.** A judgment does not change the words of a provision, and the SEND Code of Practice is statutory guidance, not legislation.

Each commit links to the instrument's own words, and for anything that matters the legislation itself should be read.

## Earlier work

Others have kept law in git before. [c3e/grundgesetz](https://github.com/c3e/grundgesetz) keeps Germany's Basic Law with a commit for each amending law, dated when it was signed. [Archéo Lex](https://github.com/Legilibre/Archeo-Lex) keeps French codes with a commit for each consolidated version, dated when it came into force. [legalize-uk](https://github.com/legalize-dev/legalize-uk) keeps thousands of UK Acts as files with a commit for each amendment date. This history is much smaller. It is about provisions, and it keeps the cause of every change: one commit for each instrument on each day, with the instrument as author, the effect from the publisher's register, coming into force as a change of status, and temporary changes and their end as commits of their own.

## How it is built

`tools/ukhistory.py` builds the history. It uses only the Python standard library, and it is the same code that produces the data behind the reader. `python tools/ukhistory.py build` reads every point-in-time version and the changes register from legislation.gov.uk and writes `data/history.json`. `python tools/ukhistory.py repo --repo <dir>` writes the commits. The build is deterministic: the same data gives the same commits. It is rebuilt when the data is updated, so the history may be rewritten.

The build sends at most a few requests a second and names itself in its user agent, within legislation.gov.uk's fair-use limits.

[REPRODUCE.md](REPRODUCE.md) records exactly how the history was made: the sources, every command, the software, the decisions made by hand, and what the AI model that built it did and did not do. [RESEARCH.md](RESEARCH.md) has the research behind the design.

Built by [Lexifina](https://lexifina.com). For corrections, open an issue.

## Licence

© Crown and database right. Derived from content available under the Open Government Licence v3.0 from legislation.gov.uk. This history is not endorsed by The National Archives or legislation.gov.uk.

The history, commit messages and README are released under [CC BY 4.0](LICENSE.md), and `tools/ukhistory.py` under the MIT licence.
