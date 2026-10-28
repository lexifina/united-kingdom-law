"""Tests for ukhistory.py, on point-in-time versions saved from legislation.gov.uk.

    python -m unittest test_ukhistory.py        (from the folder this file is in)
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import ukhistory as uk  # noqa: E402

FIX = HERE / "fixtures"


def fixture(name: str) -> bytes:
    return (FIX / name).read_bytes()


class ParseVersion(unittest.TestCase):
    def test_numbered_units_become_lines_with_their_depth(self):
        v = uk.parse_version(fixture("reg13-2015-09-01.xml"))
        self.assertEqual(v["heading"], "Timescales for EHC plans")
        labels = [(l["depth"], l["label"]) for l in v["lines"]]
        self.assertEqual(labels[:4], [(0, "(1)"), (1, "(a)"), (2, "(i)"), (2, "(ii)")])
        # The words closing paragraph (2), after its list, are their own unnumbered line.
        closing = [l for l in v["lines"] if l["label"] is None]
        self.assertTrue(closing[0]["text"].startswith("as soon as practicable"))
        self.assertEqual(v["extent"], "E+W")

    def test_a_temporary_substitution_reads_as_the_words_in_force(self):
        v = uk.parse_version(fixture("reg13-2020-05-01.xml"))
        last = v["lines"][-1]["text"]
        self.assertTrue(last.endswith("regulation 10(4)(a) to (e)."), last)
        self.assertNotIn("(d)", last)
        # The substituted word's annotation is found through the Addition element's CommentaryRef attribute.
        notes = [c["text"] for c in v["commentaries"].values() if c["type"] == "F"]
        self.assertTrue(any("temp. until 25.9.2020" in n for n in notes), notes)

    def test_omitted_words_keep_the_publishers_dots_and_drop_the_marker(self):
        v = uk.parse_version(fixture("s37-2015-04-01.xml"))
        e = [l for l in v["lines"] if l["label"] == "(e)"][0]["text"]
        self.assertTrue(e.endswith("Chronically Sick and Disabled Persons Act 1970 ...;"), e)

    def test_quotes_are_typographic(self):
        v = uk.parse_version(fixture("reg13-2015-09-01.xml"))
        self.assertIn("child’s", v["lines"][0]["text"])
        self.assertNotIn("'", "".join(l["text"] for l in v["lines"]))

    def test_versions_are_listed_from_the_current_document(self):
        self.assertEqual(uk.versions_of(fixture("s42-current.xml")), ["enacted", "2014-09-01", "2020-03-25", "2021-12-09"])


class Classify(unittest.TestCase):
    def test_a_reverted_temporary_change_matches_despite_tidied_punctuation(self):
        before = {"lines": uk.parse_version(fixture("reg13-2015-09-01.xml"))["lines"]}
        after = {"lines": uk.parse_version(fixture("reg13-2020-09-25.xml"))["lines"]}
        self.assertNotEqual(uk._words(before), uk._words(after))
        self.assertEqual(uk._loose(before), uk._loose(after))

    def test_status_follows_commencement(self):
        inforce = [{"date": "2014-04-01", "qualification": "for specified purposes"},
                   {"date": "2014-09-01", "qualification": "in force in so far as not already in force"}]
        act = {"kind": "ukpga"}
        self.assertEqual(uk.status_on("2014-03-13", inforce, act), "Not yet in force")
        self.assertEqual(uk.status_on("2014-04-01", inforce, act), "In force for specified purposes")
        self.assertEqual(uk.status_on("2014-09-01", inforce, act), "In force")
        si = {"kind": "uksi", "coming_into_force": "2014-09-01"}
        self.assertEqual(uk.status_on("2014-06-04", [], si), "Made, not yet in force")
        self.assertEqual(uk.status_on("2014-09-01", [], si), "In force")

    def test_non_textual_effects(self):
        self.assertTrue(uk._non_textual({"type": "power to modify conferred (temp.)"}))
        self.assertTrue(uk._non_textual({"type": "coming into force"}))
        self.assertFalse(uk._non_textual({"type": "words omitted"}))


class Repository(unittest.TestCase):
    def test_noon_in_london_time(self):
        self.assertEqual(uk.london_noon("2020-05-01"), "2020-05-01T12:00:00+0100")
        self.assertEqual(uk.london_noon("2014-03-13"), "2014-03-13T12:00:00+0000")
        self.assertEqual(uk.london_noon("2021-12-09"), "2021-12-09T12:00:00+0000")

    def test_short_citations(self):
        ps = [{"instrument": "ukpga/2014/6", "kind": "section", "number": n} for n in ("19", "21", "36")]
        self.assertEqual(uk.short_cites(ps), "Children and Families Act 2014 ss. 19, 21 and 36")
        self.assertEqual(uk.short_cites(ps[:1]), "Children and Families Act 2014 s. 19")

    def test_authors_are_instruments_at_invalid_addresses(self):
        name, email = uk.author_of({"uri": "uksi/2020/471", "citation": "S.I. 2020/471", "title": "The X Regulations 2020"})
        self.assertEqual(name, "S.I. 2020/471 (The X Regulations 2020)")
        self.assertEqual(email, "uksi-2020-471@legislation.invalid")

    def test_render_puts_one_unit_on_a_line(self):
        v = uk.parse_version(fixture("reg13-2020-05-01.xml"))
        p = {"cite": "SEND Regulations 2014, reg. 13", "number": "13"}
        md = uk.render(p, {**v, "status": "In force", "key": "2020-05-01", "url": "https://example"}, {})
        self.assertIn("status: In force\n", md)
        self.assertIn("\n- (a) give them at least 15 days", md)
        self.assertIn("\n  - (i) make representations", md)

    def test_commits_are_dated_and_authored_by_the_change(self):
        history = _tiny_history()
        with tempfile.TemporaryDirectory() as tmp:
            n = uk.write_repo(history, Path(tmp), {}, ("Lexifina", "uk-law-history@lexifina.com"))
            self.assertEqual(n, 2)
            log = subprocess.run(["git", "log", "--format=%ad|%an|%ae|%s", "--date=iso-strict"], cwd=tmp,
                                 capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertTrue(log[0].startswith("2020-05-01T12:00:00+01:00|S.I. 2020/471 (The X Regulations 2020)|uksi-2020-471@legislation.invalid|"), log[0])
        self.assertIn("temporarily amended, SEND Regulations 2014 reg. 13", log[0])
        self.assertTrue(log[1].startswith("2014-06-04T12:00:00+01:00|S.I. 2014/1530"), log[1])

    def test_the_history_is_never_written_over_an_existing_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            uk.write_repo(_tiny_history(), Path(tmp), {}, ("Lexifina", "x@lexifina.com"))
            with self.assertRaises(SystemExit):
                uk.write_repo(_tiny_history(), Path(tmp), {}, ("Lexifina", "x@lexifina.com"))

    def test_a_provision_on_a_date_follows_the_in_force_trailer(self):
        path = "uksi/2014/1530/regulation/13.md"
        with tempfile.TemporaryDirectory() as tmp:
            uk.write_repo(_tiny_history(), Path(tmp), {}, ("Lexifina", "x@lexifina.com"))
            self.assertIn("did not exist on 2014-01-01", uk.on_date(Path(tmp), "2014-01-01", path))
            self.assertIn("to (d)", uk.on_date(Path(tmp), "2020-04-30", path))
            self.assertIn("to (e)", uk.on_date(Path(tmp), "2020-05-01", path))


def _tiny_history():
    made = uk.parse_version(fixture("reg13-2015-09-01.xml"))
    temp = uk.parse_version(fixture("reg13-2020-05-01.xml"))
    effect = {"id": "4530778c99921686d320ee4007062a10", "type": "word substituted (temp.)", "affecting": "uksi/2020/471",
              "affecting_title": "The X Regulations 2020", "affecting_provisions": "reg. 10",
              "in_force": [{"date": "2020-05-01", "qualification": "wholly in force"}]}
    versions = [
        {**made, "key": "made", "date": "2014-06-04", "status": "Made, not yet in force", "url": "u1"},
        {**temp, "key": "2020-05-01", "date": "2020-05-01", "status": "In force", "url": "u2"},
    ]
    return {
        "source": {"retrieved": "2026-10-28"},
        "instruments": {"uksi/2014/1530": {"uri": "uksi/2014/1530", "title": "The Special Educational Needs and Disability Regulations 2014",
                                           "citation": "S.I. 2014/1530", "kind": "uksi", "made": "2014-06-04"}},
        "affecting": {"uksi/2020/471": {"uri": "uksi/2020/471", "title": "The X Regulations 2020", "citation": "S.I. 2020/471", "made": "2020-04-28"}},
        "provisions": [{
            "id": "uksi/2014/1530/regulation/13", "instrument": "uksi/2014/1530", "kind": "regulation", "number": "13",
            "cite": "The Special Educational Needs and Disability Regulations 2014, reg. 13", "versions": versions,
            "changes": [{"version": "made", "date": "2014-06-04", "kind": "made", "effects": []},
                        {"version": "2020-05-01", "date": "2020-05-01", "kind": "temporary", "effects": [effect["id"]]}],
            "effects": {effect["id"]: effect},
        }],
    }


if __name__ == "__main__":
    unittest.main()
