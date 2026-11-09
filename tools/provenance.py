#!/usr/bin/env python3
"""
provenance.py — what a PDF says about where it came from.

    pip install pikepdf c2pa-python      # c2pa-python is optional
    python provenance.py invoice.pdf

Prints, in this order: the Info dictionary, the XMP fields that matter,
every embedded file (a C2PA manifest is one of them), the catalog's
associated files, and a raw-bytes scan for the strings an assistant
leaves behind. If c2pa-python is installed it also asks that library to
read and validate the manifest.

Nothing here proves anything. A marker says "this tool wrote this file";
its absence says nothing at all. That is the whole point of the article.
"""

import re
import sys
import zlib

import pikepdf

MARKERS = [b"c2pa", b"trainedAlgorithmicMedia", b"chatgpt.com", b"OpenAI", b"ChatGPT", b"Claude", b"Gemini", b"Copilot"]


def info(pdf: pikepdf.Pdf) -> None:
    print("== Info dictionary")
    for key in ("/Creator", "/Producer", "/CreationDate", "/ModDate", "/Title", "/Author"):
        if key in pdf.docinfo:
            print(f"  {key:14} {str(pdf.docinfo[key])!r}")
    print(f"  {'PDF version':14} {pdf.pdf_version}")


def xmp(pdf: pikepdf.Pdf) -> None:
    print("== XMP")
    try:
        # the IPTC namespace that carries "trainedAlgorithmicMedia" is not one pikepdf knows by default
        from pikepdf.models.metadata import XmpDocument
        XmpDocument.register_xml_namespace("http://iptc.org/std/Iptc4xmpExt/2008-02-29/", "Iptc4xmpExt")
    except Exception:
        pass
    try:
        with pdf.open_metadata() as meta:
            if not len(meta):
                print("  (none)")
                return
            wanted = (
                "xmp:CreatorTool", "pdf:Producer", "xmp:CreateDate", "xmp:ModifyDate",
                "Iptc4xmpExt:DigitalSourceType",     # http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia
                "dcterms:provenance", "xmpMM:History", "xmpMM:DocumentID", "xmpMM:InstanceID",
            )
            for key in wanted:
                if key in meta:
                    print(f"  {key:32} {meta[key]!r}")
    except Exception as e:  # malformed XMP is itself a fact
        print(f"  unreadable: {e}")


def attachments(pdf: pikepdf.Pdf) -> None:
    print("== Embedded files")
    if not pdf.attachments:
        print("  (none)")
        return
    for name, spec in pdf.attachments.items():
        stream = spec.get_file()
        data = stream.read_bytes()
        subtype = str(stream.obj.get("/Subtype", "?"))
        head = data[:16]
        looks_c2pa = subtype == "/application/c2pa" or name.lower().endswith(".c2pa") or b"jumb" in data[:32] or b"c2pa" in data[:64]
        print(f"  {name!r}: {len(data)} bytes, mime {subtype}, starts {head!r}" + ("  <- C2PA manifest" if looks_c2pa else ""))
        # claim generator and assertion labels are plain UTF-8 inside the CBOR/JUMBF boxes
        for label in sorted(set(re.findall(rb"c2pa\.(?:actions|assertions|claim|created|hash\.data|hash\.boxes|icon|signature|ingredient|thumbnail\.[a-z]+)(?:\.v\d)?", data))):
            print(f"      {label.decode()}")
        for m in sorted(set(re.findall(rb"(?:ChatGPT|OpenAI|GPT-4o|DALL\xc2\xb7E|Sora|trainedAlgorithmicMedia)[^\x00\"]{0,40}", data))):
            print(f"      {m.decode(errors='replace')}")


def associated(pdf: pikepdf.Pdf) -> None:
    print("== Catalog /AF (associated files)")
    af = pdf.Root.get("/AF")
    if af is None:
        print("  (none)")
        return
    for spec in af:
        print(f"  {str(spec.get('/F', '?'))}  relationship {str(spec.get('/AFRelationship', '?'))}")


def raw_scan(path: str, pdf: pikepdf.Pdf) -> None:
    print("== Marker strings")
    raw = open(path, "rb").read()
    inflated = bytearray()
    for obj in pdf.objects:
        if isinstance(obj, pikepdf.Stream):
            try:
                inflated += obj.read_bytes()
            except Exception:
                pass
    for marker in MARKERS:
        n_raw, n_streams = raw.count(marker), inflated.count(marker)
        if n_raw or n_streams:
            print(f"  {marker.decode():26} raw ×{n_raw}  inside streams ×{n_streams}")
    urls = sorted(set(re.findall(rb"https?://[^\s\"'<>)]{4,80}", raw + inflated)))
    if urls:
        print("  URLs:", ", ".join(u.decode(errors="replace") for u in urls[:12]))


def c2pa_validate(path: str) -> None:
    print("== c2pa-python")
    try:
        import c2pa  # noqa
    except ImportError:
        print("  not installed")
        return
    try:
        with c2pa.Reader(path) as reader:
            manifest = reader.json()
        print(manifest[:1200])
    except Exception as e:
        print(f"  {type(e).__name__}: {e}")


if __name__ == "__main__":
    path = sys.argv[1]
    with pikepdf.open(path) as pdf:
        info(pdf)
        xmp(pdf)
        attachments(pdf)
        associated(pdf)
        raw_scan(path, pdf)
    c2pa_validate(path)
