from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

NS = {"w": W_NS, "wp": WP_NS, "a": A_NS, "r": R_NS}


def qn(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def dxa_to_emu(dxa: int) -> int:
    return int(round(dxa * 635))


def set_dxa_attr(el: etree._Element, attr: str, value: int) -> None:
    el.set(qn(W_NS, attr), str(max(1, int(round(value)))))


def drawing_media_path(inline: etree._Element, rels: dict[str, str], media_dir: Path) -> Path | None:
    blip = inline.xpath(".//a:blip", namespaces=NS)
    if not blip:
        return None
    rid = blip[0].get(qn(R_NS, "embed")) or blip[0].get(qn(R_NS, "link"))
    if not rid:
        return None
    target = rels.get(rid)
    if not target:
        return None
    if target.startswith("media/"):
        return media_dir / Path(target).name
    return None


def image_ratio(path: Path | None, fallback: float = 1.0) -> float:
    if path is None or not path.exists():
        return fallback
    try:
        with Image.open(path) as im:
            w, h = im.size
        return w / h if h else fallback
    except Exception:
        return fallback


def table_index_for_node(node: etree._Element, tables: list[etree._Element]) -> int | None:
    tbl = node.xpath("ancestor::w:tbl[1]", namespaces=NS)
    if not tbl:
        return None
    try:
        return tables.index(tbl[0])
    except ValueError:
        return None


def cell_start_col(node: etree._Element) -> int:
    tc = node.xpath("ancestor::w:tc[1]", namespaces=NS)
    if not tc:
        return 0
    cell = tc[0]
    row = cell.getparent()
    col = 0
    for sibling in row.xpath("./w:tc", namespaces=NS):
        if sibling is cell:
            return col
        span = sibling.xpath("./w:tcPr/w:gridSpan/@w:val", namespaces=NS)
        col += int(span[0]) if span else 1
    return col


def scale_table_widths(tbl: etree._Element, scale: float) -> None:
    for grid_col in tbl.xpath("./w:tblGrid/w:gridCol", namespaces=NS):
        old = int(grid_col.get(qn(W_NS, "w"), "1"))
        set_dxa_attr(grid_col, "w", old * scale)

    for width_el in tbl.xpath(".//w:tcPr/w:tcW", namespaces=NS):
        old = int(width_el.get(qn(W_NS, "w"), "1"))
        set_dxa_attr(width_el, "w", old * scale)

    for width_el in tbl.xpath("./w:tblPr/w:tblW", namespaces=NS):
        width_el.set(qn(W_NS, "type"), "dxa")
        total = sum(
            int(g.get(qn(W_NS, "w"), "0"))
            for g in tbl.xpath("./w:tblGrid/w:gridCol", namespaces=NS)
        )
        set_dxa_attr(width_el, "w", total)


def fit_inline(inline: etree._Element, width_dxa: int, height_dxa: int) -> None:
    cx, cy = dxa_to_emu(width_dxa), dxa_to_emu(height_dxa)
    for extent in inline.xpath("./wp:extent", namespaces=NS):
        extent.set("cx", str(cx))
        extent.set("cy", str(cy))
    for ext in inline.xpath(".//a:xfrm/a:ext", namespaces=NS):
        ext.set("cx", str(cx))
        ext.set("cy", str(cy))


def restore_layout(input_path: Path, output_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(input_path) as zin:
            zin.extractall(tmp_path)

        word = tmp_path / "word"
        document_xml = word / "document.xml"
        rels_xml = word / "_rels" / "document.xml.rels"
        media_dir = word / "media"

        parser = etree.XMLParser(remove_blank_text=False)
        doc = etree.parse(str(document_xml), parser)
        root = doc.getroot()
        rels_tree = etree.parse(str(rels_xml), parser)
        rels = {
            rel.get("Id"): rel.get("Target")
            for rel in rels_tree.getroot()
            if rel.get("Id") and rel.get("Target")
        }

        tables = root.xpath("//w:tbl", namespaces=NS)

        # Feishu renders this doc in a standard 820px reading column, while the
        # first two tables are horizontally scrollable at roughly 2,800px wide.
        # The downloaded DOCX had those same pixel widths translated as tiny
        # DXA values, so this restores the web/table scale.
        for idx in (0, 1):
            if idx < len(tables):
                scale_table_widths(tables[idx], 3.68)

        for inline in root.xpath("//wp:inline", namespaces=NS):
            t_idx = table_index_for_node(inline, tables)
            if t_idx not in (0, 1):
                continue

            col = cell_start_col(inline)
            media = drawing_media_path(inline, rels, media_dir)
            ratio = image_ratio(media, fallback=1.33)

            if t_idx == 0 and col == 2:
                # First table "示意图" column: web card is about 302 x 226px.
                width = 3320
                height = int(width / ratio)
                fit_inline(inline, width, height)
            elif t_idx == 1 and col >= 2:
                # Second table item cards are compact video/image previews.
                width = 900
                height = 1600 if ratio > 0.9 else int(width / max(ratio, 0.55))
                fit_inline(inline, width, height)
            elif col >= 3:
                # First table performer cells: restore narrow vertical video
                # cards as seen in Feishu, instead of square thumbnails.
                width = 900
                height = 1600
                fit_inline(inline, width, height)

        doc.write(
            str(document_xml),
            xml_declaration=True,
            encoding="UTF-8",
            standalone=False,
        )

        if output_path.exists():
            output_path.unlink()

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for path in tmp_path.rglob("*"):
                if path.is_file():
                    zout.write(path, path.relative_to(tmp_path).as_posix())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.input, args.out.with_suffix(".source-backup.docx"))
    restore_layout(args.input, args.out)


if __name__ == "__main__":
    main()
