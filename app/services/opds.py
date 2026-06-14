"""OPDS 1.2 catalog builder — Atom XML via `lxml.etree` (no third-party).

Pure helpers: the API layer (`app/api/opds.py`) queries the DB and calls
these to assemble navigation / acquisition feeds. Acquisition entries
point at the existing CBZ download endpoint (`/api/chapters/{id}/file`).

Spec: https://specs.opds.io/opds-1.2
"""

from __future__ import annotations

from datetime import datetime, timezone

from lxml import etree

# --- namespaces -------------------------------------------------------------
ATOM = "http://www.w3.org/2005/Atom"
OPDS = "http://opds-spec.org/2010/catalog"
DCTERMS = "http://purl.org/dc/terms/"
OPENSEARCH = "http://a9.com/-/spec/opensearch/1.1/"
_NSMAP = {None: ATOM, "opds": OPDS, "dcterms": DCTERMS}

# --- content types ----------------------------------------------------------
NAV_CT = "application/atom+xml;profile=opds-catalog;kind=navigation"
ACQ_CT = "application/atom+xml;profile=opds-catalog;kind=acquisition"
OPENSEARCH_CT = "application/opensearchdescription+xml"
CBZ_CT = "application/vnd.comicbook+zip"

# --- link rels --------------------------------------------------------------
REL_ACQUISITION = "http://opds-spec.org/acquisition"
REL_THUMBNAIL = "http://opds-spec.org/image/thumbnail"
REL_SUBSECTION = "subsection"

ROOT_HREF = "/opds/v1.2/root"


def _iso(dt: datetime | None = None) -> str:
    d = dt or datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(parent: etree._Element, tag: str, text: str) -> etree._Element:
    el = etree.SubElement(parent, f"{{{ATOM}}}{tag}")
    el.text = text
    return el


def add_link(
    parent: etree._Element, href: str, *, rel: str, type: str, title: str | None = None,
) -> etree._Element:
    el = etree.SubElement(parent, f"{{{ATOM}}}link")
    el.set("href", href)
    el.set("rel", rel)
    el.set("type", type)
    if title:
        el.set("title", title)
    return el


def feed(
    feed_id: str,
    title: str,
    self_href: str,
    *,
    kind: str,
    up_href: str | None = None,
) -> etree._Element:
    """Create an OPDS feed root (navigation or acquisition)."""
    self_ct = NAV_CT if kind == "navigation" else ACQ_CT
    f = etree.Element(f"{{{ATOM}}}feed", nsmap=_NSMAP)
    _text(f, "id", feed_id)
    _text(f, "title", title)
    _text(f, "updated", _iso())
    add_link(f, self_href, rel="self", type=self_ct)
    add_link(f, ROOT_HREF, rel="start", type=NAV_CT)
    if up_href:
        add_link(f, up_href, rel="up", type=NAV_CT)
    return f


def add_nav_entry(
    parent: etree._Element,
    entry_id: str,
    title: str,
    href: str,
    *,
    summary: str | None = None,
    thumb_href: str | None = None,
) -> etree._Element:
    e = etree.SubElement(parent, f"{{{ATOM}}}entry")
    _text(e, "id", entry_id)
    _text(e, "title", title)
    _text(e, "updated", _iso())
    if summary:
        _text(e, "summary", summary)
    add_link(e, href, rel=REL_SUBSECTION, type=NAV_CT)
    if thumb_href:
        add_link(e, thumb_href, rel=REL_THUMBNAIL, type="image/jpeg")
    return e


def add_acquisition_entry(
    parent: etree._Element,
    entry_id: str,
    title: str,
    acquisition_href: str,
    *,
    size: int | None = None,
    thumb_href: str | None = None,
    updated: datetime | None = None,
    summary: str | None = None,
) -> etree._Element:
    e = etree.SubElement(parent, f"{{{ATOM}}}entry")
    _text(e, "id", entry_id)
    _text(e, "title", title)
    _text(e, "updated", _iso(updated))
    if summary:
        _text(e, "summary", summary)
    link = add_link(e, acquisition_href, rel=REL_ACQUISITION, type=CBZ_CT)
    if size is not None:
        link.set("length", str(size))
    if thumb_href:
        add_link(e, thumb_href, rel=REL_THUMBNAIL, type="image/jpeg")
    return e


def serialize(feed_el: etree._Element) -> bytes:
    return etree.tostring(feed_el, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def opensearch_description(search_template: str) -> bytes:
    """OpenSearch description document pointing at the OPDS search URL."""
    root = etree.Element(f"{{{OPENSEARCH}}}OpenSearchDescription", nsmap={None: OPENSEARCH})
    etree.SubElement(root, f"{{{OPENSEARCH}}}ShortName").text = "MangaSama"
    etree.SubElement(root, f"{{{OPENSEARCH}}}Description").text = "Cerca nel catalogo MangaSama"
    etree.SubElement(root, f"{{{OPENSEARCH}}}InputEncoding").text = "UTF-8"
    url = etree.SubElement(root, f"{{{OPENSEARCH}}}Url")
    url.set("type", ACQ_CT)
    url.set("template", search_template)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")
