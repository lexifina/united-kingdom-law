"""UK legislation as a git history, built from legislation.gov.uk.

    python ukhistory.py build  [--cache DIR] [--out history.json]
    python ukhistory.py repo   --history history.json --repo DIR
    python ukhistory.py check  --history history.json        # re-fetch and compare every version's text
    python ukhistory.py on 2020-06-01 uksi/2014/1530/regulation/13   # a provision as it stood on a date

Standard library only, so the public repository can carry this file and anyone can rebuild it.

Every point-in-time version that legislation.gov.uk publishes for a provision becomes one state of that provision's
file. A version starts on the date it took effect, which is the date the commit carries; the change that explains it
is the effect in the publisher's changes register whose in-force date is that day. The effect and the marks in the
text share one key (CommentaryRef / EffectId), so each commit names the instrument, provision and effect type that
made it, from the register rather than from a diff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BASE = "https://www.legislation.gov.uk"
USER_AGENT = "Lexifina uk-legislation history (https://github.com/lexifina/uk-law-history)"
NS = {
    "leg": "http://www.legislation.gov.uk/namespaces/legislation",
    "ukm": "http://www.legislation.gov.uk/namespaces/metadata",
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
}
HAS_VERSION = "http://purl.org/dc/terms/hasVersion"

# The provisions in the record. Each is (instrument, provision kind, number), as in legislation.gov.uk's URIs.
PROVISIONS: List[Tuple[str, str, str]] = [
    ("ukpga/2014/6", "section", "19"),
    ("ukpga/2014/6", "section", "21"),
    ("ukpga/2014/6", "section", "36"),
    ("ukpga/2014/6", "section", "37"),
    ("ukpga/2014/6", "section", "42"),
    ("uksi/2014/1530", "regulation", "6"),
    ("uksi/2014/1530", "regulation", "11"),
    ("uksi/2014/1530", "regulation", "12"),
    ("uksi/2014/1530", "regulation", "13"),
]

LEVELS = {"P2": 0, "P3": 1, "P4": 2, "P5": 3, "P6": 4, "P7": 5}
SKIP = {"CommentaryRef", "FootnoteRef", "Repeal", "MarginNoteRef"}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def effect_id(raw: Optional[str]) -> str:
    """The register's key for a change, without its "key-" prefix.

    legislation.gov.uk writes keys as "key-" and 32 hex digits, which secret scanners take for an API key, so the
    history carries the hex digits alone. The marks in the text and the entries in the register share the key.
    """
    return re.sub(r"^key-", "", raw or "")


# --- fetching -------------------------------------------------------------------------------------------------------

class Fetcher:
    def __init__(self, cache: Path, delay: float = 0.4):
        self.cache = cache
        self.delay = delay
        cache.mkdir(parents=True, exist_ok=True)

    def get(self, path: str) -> bytes:
        url = path if path.startswith("http") else BASE + path
        key = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[1])[:180] + "-" + hashlib.sha1(url.encode()).hexdigest()[:8]
        hit = self.cache / key
        if hit.exists():
            return hit.read_bytes()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    body = r.read()
                break
            except Exception as error:  # noqa: BLE001 - retried, then reported
                if attempt == 4:
                    raise SystemExit(f"could not fetch {url}: {error}")
                time.sleep(2 * (attempt + 1))
        hit.write_bytes(body)
        time.sleep(self.delay)
        return body


# --- reading CLML ---------------------------------------------------------------------------------------------------

def tidy(text: str) -> str:
    text = text.replace(" ", " ").replace("'", "’")
    text = re.sub(r"\s+", " ", text).strip()
    # No space before punctuation, except before the dots that stand for omitted words.
    return re.sub(r"\s+([,;:)]|\.(?!\.))", r"\1", text)


def text_of(el: ET.Element) -> str:
    """The words in force in an element: commentary markers and text kept only to show a repeal are left out."""
    parts: List[str] = [el.text or ""]
    for child in el:
        if local(child.tag) not in SKIP:
            parts.append(text_of(child))
        parts.append(child.tail or "")
    return "".join(parts)


@dataclass
class Line:
    depth: int
    label: Optional[str]
    text: str

    def as_dict(self) -> Dict[str, Any]:
        return {"depth": self.depth, "label": self.label, "text": self.text}


def label_of(p: ET.Element, level: int) -> Optional[str]:
    num = p.find("leg:Pnumber", NS)
    if num is None:
        return None
    value = tidy(text_of(num))
    return f"({value})" if value and level >= 0 else value or None


def block(p: ET.Element, level: int, out: List[Line]) -> None:
    """One numbered unit: its own words on one line with its number, then its children, then any closing words."""
    label = label_of(p, level)
    depth = max(level, 0)
    first = True
    for para in p:
        if not local(para.tag).endswith("para"):
            continue
        for child in para:
            tag = local(child.tag)
            if tag == "Text":
                words = tidy(text_of(child))
                if not words:
                    continue
                out.append(Line(depth, label if first else None, words))
                first = False
            elif tag in LEVELS:
                if first and label:
                    out.append(Line(depth, label, ""))
                    first = False
                block(child, LEVELS[tag], out)
            elif tag in ("UnorderedList", "OrderedList"):
                for item in child.findall("leg:ListItem", NS):
                    words = tidy(text_of(item))
                    if words:
                        out.append(Line(depth + 1, None, words))
    if first and label:
        out.append(Line(depth, label, "..."))


def parse_version(raw: bytes) -> Dict[str, Any]:
    root = ET.fromstring(raw)
    group = root.find(".//leg:P1group", NS)
    p1 = root.find(".//leg:P1", NS)
    heading = tidy(text_of(group.find("leg:Title", NS))) if group is not None and group.find("leg:Title", NS) is not None else ""
    lines: List[Line] = []
    if p1 is not None:
        for para in p1:
            if not local(para.tag).endswith("para"):
                continue
            for child in para:
                tag = local(child.tag)
                if tag == "Text":
                    words = tidy(text_of(child))
                    if words:
                        lines.append(Line(0, None, words))
                elif tag in LEVELS:
                    block(child, LEVELS[tag], lines)
    scope = group if group is not None else p1
    # Commentary is referenced by CommentaryRef markers and by the CommentaryRef attribute of an Addition or
    # Substitution.
    refs = sorted({effect_id(r.get("Ref") or r.get("CommentaryRef")) for r in (scope.iter() if scope is not None else [])
                   if (local(r.tag) == "CommentaryRef" and r.get("Ref")) or r.get("CommentaryRef")})
    comments = {}
    for c in root.iter(f"{{{NS['leg']}}}Commentary"):
        if effect_id(c.get("id")) in refs:
            comments[effect_id(c.get("id"))] = {"type": c.get("Type"), "text": tidy(text_of(c))}
    return {
        "heading": heading,
        "lines": [l.as_dict() for l in lines],
        "extent": (scope.get("RestrictExtent") if scope is not None else None) or None,
        "start": (scope.get("RestrictStartDate") if scope is not None else None) or None,
        "end": (scope.get("RestrictEndDate") if scope is not None else None) or None,
        "commentaries": comments,
    }


def versions_of(raw: bytes) -> List[str]:
    root = ET.fromstring(raw)
    return [l.get("title") for l in root.iter(f"{{{NS['atom']}}}link") if l.get("rel") == HAS_VERSION and l.get("title")]


def instrument_meta(raw: bytes, uri: str) -> Dict[str, Any]:
    root = ET.fromstring(raw)
    md = root.find("ukm:Metadata", NS)
    title = md.findtext("dc:title", default="", namespaces=NS).strip()
    kind = uri.split("/")[0]
    year, number = uri.split("/")[1:3]
    meta: Dict[str, Any] = {"uri": uri, "title": title, "kind": kind, "year": int(year), "number": int(number)}
    enacted = md.find(".//ukm:EnactmentDate", NS)
    made = md.find(".//ukm:Made", NS)
    laid = md.find(".//ukm:Laid", NS)
    cif = md.find(".//ukm:ComingIntoForce/ukm:DateTime", NS)
    if enacted is not None:
        meta["enacted"] = enacted.get("Date")
    if made is not None:
        meta["made"] = made.get("Date")
    if laid is not None:
        meta["laid"] = laid.get("Date")
    if cif is not None:
        meta["coming_into_force"] = cif.get("Date")
    meta["citation"] = citation_of(kind, int(year), int(number))
    return meta


def citation_of(kind: str, year: int, number: int) -> str:
    if kind == "ukpga":
        return f"{year} c. {number}"
    if kind == "uksi":
        return f"S.I. {year}/{number}"
    return f"{kind} {year}/{number}"


# --- the changes register -------------------------------------------------------------------------------------------

def effects_for(fetch: Fetcher, instrument: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    page = 1
    while True:
        raw = fetch.get(f"/changes/affected/{instrument}/data.feed?results-count=500&page={page}")
        root = ET.fromstring(raw)
        for e in root.iter(f"{{{NS['ukm']}}}Effect"):
            affected = [s.get("URI", "") for s in e.findall("ukm:AffectedProvisions/ukm:Section", NS)]
            affected += [s.get("URI", "") for s in e.findall("ukm:AffectedProvisions/ukm:SectionRange", NS)]
            affecting_uri = (e.get("AffectingURI") or "").split("/id/", 1)[-1]
            out.append({
                "id": effect_id(e.get("EffectId")),
                "type": e.get("Type"),
                "affected_provisions": e.get("AffectedProvisions"),
                "affected": [a.split("/id/", 1)[-1] for a in affected],
                "affecting": affecting_uri,
                "affecting_title": tidy(e.findtext("ukm:AffectingTitle", default="", namespaces=NS)),
                "affecting_provisions": e.get("AffectingProvisions"),
                "applied": e.get("Applied") == "true",
                "requires_applied": e.get("RequiresApplied") == "true",
                "comments": e.get("Comments") or None,
                "in_force": [
                    {"date": f.get("Date"), "qualification": f.get("Qualification"), "prospective": f.get("Prospective") == "true"}
                    for f in e.findall("ukm:InForceDates/ukm:InForce", NS)
                ],
            })
        more = root.find(".//leg:morePages", NS)
        if more is None or not more.text or int(more.text) <= 0 and page >= 1 and not _has_next(root):
            break
        page += 1
        if page > 20:
            break
    return out


def _has_next(root: ET.Element) -> bool:
    return any(l.get("rel") == "next" for l in root.iter(f"{{{NS['atom']}}}link"))


def touches(effect: Dict[str, Any], provision: str) -> bool:
    return any(a == provision or a.startswith(provision + "/") for a in effect["affected"])


# --- building the history -------------------------------------------------------------------------------------------

KIND = {
    "enacted": "Enacted",
    "made": "Made",
    "commenced": "Came into force",
    "amended": "Amended",
    "temporary": "Temporarily amended",
    "reverted": "Temporary change ended",
    "modified": "Modified, words unchanged",
    "editorial": "Revised text published",
}


def status_on(date: str, inforce: List[Dict[str, Any]], instrument: Dict[str, Any]) -> str:
    started = [f for f in inforce if f["date"] and f["date"] <= date]
    if not inforce:
        cif = instrument.get("coming_into_force")
        if instrument["kind"] != "ukpga" and cif:
            return "In force" if date >= cif else "Made, not yet in force"
        return "In force"
    if not started:
        return "Not yet in force"
    if any("specified purposes" not in (f["qualification"] or "") for f in started):
        return "In force"
    return "In force for specified purposes"


def build(fetch: Fetcher) -> Dict[str, Any]:
    instruments: Dict[str, Dict[str, Any]] = {}
    effects: Dict[str, List[Dict[str, Any]]] = {}
    for inst in sorted({p[0] for p in PROVISIONS}):
        instruments[inst] = instrument_meta(fetch.get(f"/{inst}/introduction/data.xml"), inst)
        effects[inst] = effects_for(fetch, inst)

    affecting_meta: Dict[str, Dict[str, Any]] = {}
    provisions: List[Dict[str, Any]] = []
    for inst, word, num in PROVISIONS:
        pid = f"{inst}/{word}/{num}"
        meta = instruments[inst]
        current = fetch.get(f"/{pid}/data.xml")
        mine = [e for e in effects[inst] if touches(e, pid)]
        inforce = [f for e in mine if e["type"] == "coming into force" for f in e["in_force"]]
        versions: List[Dict[str, Any]] = []
        for key in versions_of(current):
            parsed = parse_version(fetch.get(f"/{pid}/{key}/data.xml"))
            original = key in ("enacted", "made")
            date = meta.get("enacted") or meta.get("made") if original else key
            versions.append({
                "key": key,
                "date": date,
                "url": f"{BASE}/{pid}/{key}",
                "heading": parsed["heading"],
                "lines": parsed["lines"],
                "extent": parsed["extent"],
                "status": status_on(date, inforce, meta),
                "commentaries": parsed["commentaries"],
            })
        versions.sort(key=lambda v: (v["date"], v["key"] not in ("enacted", "made")))

        if meta["kind"] != "ukpga" and meta.get("coming_into_force"):
            # A statutory instrument brings itself into force; the register records no separate effect for that.
            mine.append({
                "id": f"{inst}-coming-into-force", "type": "coming into force", "affected_provisions": "whole instrument",
                "affected": [inst], "affecting": inst, "affecting_title": meta["title"], "affecting_provisions": "reg. 1",
                "applied": True, "requires_applied": True, "comments": None,
                "in_force": [{"date": meta["coming_into_force"], "qualification": "wholly in force", "prospective": False}],
            })
        changes = []
        for n, v in enumerate(versions):
            prev = versions[n - 1] if n else None
            cause = [e for e in mine if any(f["date"] == v["date"] for f in e["in_force"])] if prev else []
            text_changed = bool(prev) and _words(prev) != _words(v)
            textual = [e for e in cause if not _non_textual(e)]
            if not prev:
                kind = "enacted" if v["key"] == "enacted" else "made"
            elif text_changed:
                earlier = [w for w in versions[: n - 1] if _loose(w) == _loose(v)]
                if earlier and not textual:
                    # The words return to an earlier version: a temporary change has ended. The cause is the
                    # temporary change being undone.
                    kind = "reverted"
                    cause = [mine_e for mine_e in mine if mine_e["id"] in changes[-1]["effects"] and not _non_textual(mine_e)]
                elif any("temp" in (e["type"] or "") or "temp" in _comment_for(v, e) for e in textual):
                    kind = "temporary"
                elif textual:
                    kind = "amended"
                else:
                    kind = "editorial"
            elif v["status"] != prev["status"]:
                kind = "commenced"
            else:
                kind = "modified" if cause else "editorial"
            for e in cause:
                if e["affecting"] and e["affecting"] not in affecting_meta:
                    affecting_meta[e["affecting"]] = {}
            changes.append({"version": v["key"], "date": v["date"], "kind": kind, "effects": [e["id"] for e in cause]})

        outstanding = [e["id"] for e in mine if e["requires_applied"] and not e["applied"]]
        provisions.append({
            "id": pid,
            "instrument": inst,
            "kind": word,
            "number": num,
            "label": f"{'Section' if word == 'section' else 'Regulation'} {num}",
            "cite": f"{meta['title']}, {'s.' if word == 'section' else 'reg.'} {num}",
            "heading": versions[-1]["heading"],
            "current_url": f"{BASE}/{pid}",
            "versions": versions,
            "changes": changes,
            "effects": {e["id"]: e for e in mine},
            "outstanding": outstanding,
        })

    for uri in sorted(affecting_meta):
        try:
            affecting_meta[uri] = instrument_meta(fetch.get(f"/{uri}/introduction/data.xml"), uri)
        except SystemExit:
            affecting_meta[uri] = {"uri": uri, "title": "", "citation": uri}

    return {
        "schema": 1,
        "source": {
            "publisher": "legislation.gov.uk (The National Archives)",
            "licence": "© Crown and database right. Derived from content available under the Open Government Licence v3.0 from legislation.gov.uk.",
            "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
            "retrieved": time.strftime("%Y-%m-%d"),
        },
        "instruments": instruments,
        "affecting": affecting_meta,
        "provisions": provisions,
    }


def _words(v: Dict[str, Any]) -> List[Tuple[int, Optional[str], str]]:
    return [(l["depth"], l["label"], l["text"]) for l in v["lines"]]


def _loose(v: Dict[str, Any]) -> List[Tuple[int, Optional[str], str]]:
    # The publisher sometimes tidies punctuation when it reverts a temporary change; that is not a change of law.
    return [(d, l, re.sub(r"[\s.,;:]+$", "", t)) for d, l, t in _words(v)]


def _non_textual(e: Dict[str, Any]) -> bool:
    t = e["type"] or ""
    return t == "coming into force" or t.startswith(("modified", "applied", "excluded", "power", "expiry", "amendment to earlier"))


def _comment_for(v: Dict[str, Any], e: Dict[str, Any]) -> str:
    c = v["commentaries"].get(e["id"])
    return (c or {}).get("text", "")


# --- the repository -------------------------------------------------------------------------------------------------

def provision_path(pid: str) -> str:
    return pid + ".md"


def render(p: Dict[str, Any], v: Dict[str, Any], instrument: Dict[str, Any]) -> str:
    head = [
        "---",
        f"title: {p['cite']}",
        f"heading: {v['heading']}",
        f"status: {v['status']}",
        f"extent: {v['extent'] or ''}".rstrip(),
        f"version: {v['key']}",
        f"source: {v['url']}",
        "---",
        "",
        f"# {p['number']} {v['heading']}",
        "",
    ]
    body: List[str] = []
    prev_depth = None
    for line in v["lines"]:
        words = f"{line['label']} {line['text']}".strip() if line["label"] else line["text"]
        if line["depth"] == 0:
            if body:
                body.append("")
            body.append(words)
        else:
            if prev_depth == 0:
                body.append("")
            indent = "  " * (line["depth"] - 1)
            body.append(f"{indent}- {words}" if line["label"] else f"{indent}  {words}")
        prev_depth = line["depth"]
    return "\n".join(head + body) + "\n"


def commits(history: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Group provision changes into commits: one per day and cause, oldest first."""
    groups: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for p in history["provisions"]:
        versions = {v["key"]: v for v in p["versions"]}
        for c in p["changes"]:
            v = versions[c["version"]]
            effs = [p["effects"][i] for i in c["effects"]]
            if c["kind"] in ("enacted", "made"):
                cause = p["instrument"]
            else:
                # The effect that explains the version names the commit: the commencement for a commencement, the
                # amendment for an amendment. Other effects on the same day are listed in the message.
                lead = [e for e in effs if (e["type"] == "coming into force") == (c["kind"] == "commenced")] or effs
                cause = ",".join(sorted({e["affecting"] for e in lead})) or "publisher"
            key = (c["date"], cause, c["kind"] if c["kind"] in ("enacted", "made", "reverted", "editorial") else "change")
            g = groups.setdefault(key, {"date": c["date"], "cause": cause, "items": []})
            g["items"].append({"provision": p, "version": v, "change": c, "effects": effs})
    order = {"enacted": 0, "made": 0}
    return [groups[k] for k in sorted(groups, key=lambda k: (k[0], order.get(k[2], 1), k[1]))]


def short_cite(p: Dict[str, Any]) -> str:
    inst = p["instrument"]
    names = {"ukpga/2014/6": "Children and Families Act 2014", "uksi/2014/1530": "SEND Regulations 2014"}
    return f"{names.get(inst, inst)} {'s.' if p['kind'] == 'section' else 'reg.'} {p['number']}"


def short_cites(ps: List[Dict[str, Any]]) -> str:
    """Several provisions of one instrument: "Children and Families Act 2014 ss. 19, 21 and 36"."""
    if len(ps) == 1:
        return short_cite(ps[0])
    head = short_cite(ps[0]).rsplit(" ", 2)[0]
    plural = "ss." if ps[0]["kind"] == "section" else "regs."
    nums = [p["number"] for p in ps]
    return f"{head} {plural} {', '.join(nums[:-1])} and {nums[-1]}"


def author_of(meta: Dict[str, Any]) -> Tuple[str, str]:
    """The instrument that made a change, as a git author: its citation and title, at an address that cannot exist."""
    cite, title = meta.get("citation") or meta["uri"], meta.get("title") or ""
    name = f"{cite} ({title})" if title and title != cite else cite
    return name[:200], re.sub(r"[^a-z0-9]+", "-", meta["uri"].lower()).strip("-") + "@legislation.invalid"


def message(group: Dict[str, Any], history: Dict[str, Any]) -> Tuple[str, str, Tuple[str, str]]:
    items = group["items"]
    first = items[0]
    kind = first["change"]["kind"]
    inst = history["instruments"][first["provision"]["instrument"]]
    by_instrument: Dict[str, List[Dict[str, Any]]] = {}
    for i in items:
        by_instrument.setdefault(i["provision"]["instrument"], []).append(i["provision"])
    where = "; ".join(short_cites(ps) for ps in by_instrument.values())
    if kind in ("enacted", "made"):
        subject = f"{inst['title']}: {'Royal Assent' if kind == 'enacted' else 'made'}"
        author = author_of(inst)
        affecting: List[Dict[str, Any]] = []
    else:
        affecting = [history["affecting"].get(u) or {"uri": u} for u in group["cause"].split(",") if u != "publisher"]
        kinds = {i["change"]["kind"] for i in items}
        label = KIND[kind].lower() if len(kinds) == 1 else "changes"
        title = affecting[0].get("title") or affecting[0].get("citation") if affecting else "legislation.gov.uk"
        subject = f"{title}: {label}, {where}"
        author = author_of(affecting[0]) if affecting else ("legislation.gov.uk", "publisher@legislation.invalid")
    body: List[str] = []
    for i in items:
        p, v, c = i["provision"], i["version"], i["change"]
        body.append(f"{p['cite']}: {KIND[c['kind']].lower()}. Status: {v['status']}.")
        for e in i["effects"]:
            dates = "; ".join(f"{f['date']} ({f['qualification']})" if f["qualification"] else f["date"] for f in e["in_force"] if f["date"])
            body.append(f"  {e['type']} by {e['affecting_title'] or e['affecting']}, {e['affecting_provisions']}"
                        + (f", in force {dates}" if dates else ""))
            note = v["commentaries"].get(e["id"])
            if note and note["text"]:
                body.append(f"  Publisher's note: {note['text']}")
        body.append(f"  Source: {v['url']}")
    trailers = [f"In-force: {group['date']}"]
    for a in affecting or [inst]:
        if a.get("enacted"):
            trailers.append(f"Enacted: {a['enacted']}")
        if a.get("made"):
            trailers.append(f"Made: {a['made']}")
        trailers.append(f"Affecting: {BASE}/{a['uri']}")
    for e in sorted({e["id"] for i in items for e in i["effects"] if e["id"] and re.fullmatch(r"[0-9a-f]{32}", e["id"])}):
        trailers.append(f"Effect-id: {e}")
    return subject, "\n".join(body) + "\n\n" + "\n".join(trailers) + "\n", author


def git(repo: Path, *args: str, env: Optional[Dict[str, str]] = None, data: Optional[bytes] = None) -> str:
    result = subprocess.run(["git", *args], cwd=repo, env={**os.environ, **(env or {})}, input=data,
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", "replace").strip()


def london_noon(date: str) -> str:
    # British Summer Time runs from the last Sunday of March to the last Sunday of October.
    import datetime as dt
    y, m, d = map(int, date.split("-"))
    day = dt.date(y, m, d)

    def last_sunday(month: int) -> dt.date:
        last = dt.date(y, month, 31)
        return last - dt.timedelta(days=(last.weekday() + 1) % 7)

    offset = "+0100" if last_sunday(3) <= day < last_sunday(10) else "+0000"
    return f"{date}T12:00:00{offset}"


def write_repo(history: Dict[str, Any], repo: Path, extra: Dict[str, str], committer: Tuple[str, str]) -> int:
    # The history is always written from scratch: writing into an existing repository would add a second copy.
    if repo.exists() and any(repo.iterdir()):
        raise SystemExit(f"{repo} is not empty; the history is written into a new, empty directory")
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "core.autocrlf", "false")
    n = 0
    for group in commits(history):
        for i in group["items"]:
            p, v = i["provision"], i["version"]
            path = repo / provision_path(p["id"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render(p, v, history["instruments"][p["instrument"]]), encoding="utf-8", newline="\n")
            git(repo, "add", provision_path(p["id"]))
        subject, body, (author, address) = message(group, history)
        when = london_noon(group["date"])
        env = {
            "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": address, "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_NAME": committer[0], "GIT_COMMITTER_EMAIL": committer[1], "GIT_COMMITTER_DATE": when,
        }
        git(repo, "commit", "-q", "--allow-empty", "-F", "-", env=env, data=(subject + "\n\n" + body).encode("utf-8"))
        n += 1
    for name, content in extra.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        git(repo, "add", name)
    if extra:
        env = {"GIT_AUTHOR_NAME": committer[0], "GIT_AUTHOR_EMAIL": committer[1],
               "GIT_COMMITTER_NAME": committer[0], "GIT_COMMITTER_EMAIL": committer[1]}
        stamp = history["source"]["retrieved"] + "T12:00:00+0000"
        env.update({"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
        git(repo, "commit", "-q", "-m", "README: how to read the history, how it is built and checked, and what it does not show", env=env)
        n += 1
    return n


# --- reading the history on a date ---------------------------------------------------------------------------------

def on_date(repo: Path, date: str, path: str) -> str:
    """The file as it stood at the end of a day, chosen by the In-force trailer, so the answer does not depend on the
    reader's time zone. Says so plainly when the provision did not yet exist."""
    log = git(repo, "log", "--format=%H %(trailers:key=In-force,valueonly,separator=)", "main", "--", path)
    best = None
    for row in log.splitlines():
        sha, _, day = row.partition(" ")
        if day and day.strip() <= date:
            best = sha
            break
    if best is None:
        first = log.splitlines()[-1].partition(" ")[2].strip() if log else ""
        return f"{path} did not exist on {date}." + (f" It was enacted or made on {first}." if first else "")
    return git(repo, "show", f"{best}:{path}")


# --- checking -------------------------------------------------------------------------------------------------------

def check(history: Dict[str, Any], fetch: Fetcher) -> int:
    bad = 0
    for p in history["provisions"]:
        for v in p["versions"]:
            fresh = parse_version(fetch.get(f"/{p['id']}/{v['key']}/data.xml"))
            if fresh["lines"] != v["lines"]:
                bad += 1
                print(f"DIFFERS {p['id']} {v['key']}")
    print("all versions match" if not bad else f"{bad} versions differ")
    return bad


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--cache", default=".cache")
    b.add_argument("--out", default="history.json")
    r = sub.add_parser("repo")
    r.add_argument("--history", default="history.json")
    r.add_argument("--repo", required=True)
    r.add_argument("--extra", nargs="*", default=[], help="files to add in a final commit, as repo-path=local-path")
    r.add_argument("--committer", default="Lexifina <uk-law-history@lexifina.com>")
    o = sub.add_parser("on", help="print a provision as it stood on a date: on 2020-06-01 uksi/2014/1530/regulation/13")
    o.add_argument("date")
    o.add_argument("path")
    o.add_argument("--repo", default=".")
    c = sub.add_parser("check")
    c.add_argument("--history", default="history.json")
    c.add_argument("--cache", default=".cache-check")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.cmd == "on":
        path = args.path if args.path.endswith(".md") else args.path.strip("/") + ".md"
        print(on_date(Path(args.repo), args.date, path))
        return 0
    if args.cmd == "build":
        history = build(Fetcher(Path(args.cache)))
        Path(args.out).write_text(json.dumps(history, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"{len(history['provisions'])} provisions, {sum(len(p['versions']) for p in history['provisions'])} versions -> {args.out}")
        return 0
    history = json.loads(Path(args.history).read_text(encoding="utf-8"))
    if args.cmd == "repo":
        name, email = re.match(r"(.*?)\s*<(.*)>", args.committer).groups()
        extra = {}
        for pair in args.extra:
            dest, src = pair.split("=", 1)
            extra[dest] = Path(src).read_text(encoding="utf-8")
        print(f"{write_repo(history, Path(args.repo), extra, (name, email))} commits -> {args.repo}")
        return 0
    return 1 if check(history, Fetcher(Path(args.cache), delay=0.2)) else 0


if __name__ == "__main__":
    sys.exit(main())
