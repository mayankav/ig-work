"""Synthetic source records for isolated unit tests only. Never production data."""
import copy
import bibliography
import claim_support


def with_support(entry):
    entry = copy.deepcopy(entry)
    book = {"author": "Test Author", "title": "Synthetic Source", "year": 2000,
            "work_key": "/works/OL1W", "scan_ids": ["synthetic-source"]}
    entry["line"] = bibliography.citation_line(book)
    entry["claim_support"] = {}
    for claim in entry["claims"]:
        passage = "This is a synthetic test passage. " + claim
        record = {"version": claim_support.VERSION, "claim": claim, "book": book,
                  "source": {"work_key": book["work_key"], "scan_id": "synthetic-source",
                      "passages": [{"text": passage, "pages": [1],
                          "url": "https://archive.org/details/synthetic-source/page/n1"}]},
                  "proposed_by": "gemini", "checked_by": "groq", "at": "2026-09-04T00:00:00+00:00",
                  "review": {"inspected": ["claim", "control"], "uncertain": [],
                      "vetoes": [{"id": "control", "reason": "No passage supports the cheese claim."}],
                      "quotes": [{"passage": 0, "text": passage}]}}
        record["sha256"] = claim_support.digest(record)
        entry["claim_support"][claim_support.claim_key(claim)] = record
    return entry
