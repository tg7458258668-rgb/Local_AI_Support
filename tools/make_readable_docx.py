from __future__ import annotations

import argparse
import copy
import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

NS = {
    "w": W_NS,
    "wp": WP_NS,
    "a": A_NS,
}


def qn(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def dxa_to_emu(dxa: int) -> int:
    return int(round(dxa * 635))


def text_of(node: etree._Element) -> str:
    return "".join(node.xpath(".//w:t/text()", namespaces=NS)).strip()


def set_w(el: etree._Element, value: int) -> None:
    el.set(qn(W_NS, "w"), str(int(value)))


def ensure_child(parent: etree._Element, tag: str, after: str | None = None) -> etree._Element:
    child = parent.find(tag)
    if child is not None:
        return child
    child = etree.Element(tag)
    if after is None:
        parent.insert(0, child)
        return child
    siblings = list(parent)
    insert_at = 0
    for idx, sibling in enumerate(siblings):
        if sibling.tag == after:
            insert_at = idx + 1
    parent.insert(insert_at, child)
    return child


def cell_infos(row: etree._Element) -> list[tuple[int, int, etree._Element]]:
    infos: list[tuple[int, int, etree._Element]] = []
    col = 0
    for tc in row.xpath("./w:tc", namespaces=NS):
        span_val = tc.xpath("./w:tcPr/w:gridSpan/@w:val", namespaces=NS)
        span = int(span_val[0]) if span_val else 1
        infos.append((col, span, tc))
        col += span
    return infos


def clear_grid_span(tc: etree._Element) -> None:
    for grid_span in tc.xpath("./w:tcPr/w:gridSpan", namespaces=NS):
        grid_span.getparent().remove(grid_span)


def set_grid_span(tc: etree._Element, span: int) -> None:
    tc_pr = ensure_child(tc, qn(W_NS, "tcPr"))
    for old in tc_pr.xpath("./w:gridSpan", namespaces=NS):
        tc_pr.remove(old)
    grid_span = etree.Element(qn(W_NS, "gridSpan"))
    grid_span.set(qn(W_NS, "val"), str(span))
    tc_pr.append(grid_span)


def set_cell_width(tc: etree._Element, width: int) -> None:
    tc_pr = ensure_child(tc, qn(W_NS, "tcPr"))
    tc_w = tc_pr.find(qn(W_NS, "tcW"))
    if tc_w is None:
        tc_w = etree.Element(qn(W_NS, "tcW"))
        tc_pr.insert(0, tc_w)
    tc_w.set(qn(W_NS, "type"), "dxa")
    set_w(tc_w, width)


def set_cell_margins(tbl: etree._Element, margin: int = 90) -> None:
    tbl_pr = ensure_child(tbl, qn(W_NS, "tblPr"))
    tbl_cell_mar = tbl_pr.find(qn(W_NS, "tblCellMar"))
    if tbl_cell_mar is None:
        tbl_cell_mar = etree.Element(qn(W_NS, "tblCellMar"))
        tbl_pr.append(tbl_cell_mar)
    for side in ("top", "left", "bottom", "right"):
        el = tbl_cell_mar.find(qn(W_NS, side))
        if el is None:
            el = etree.Element(qn(W_NS, side))
            tbl_cell_mar.append(el)
        el.set(qn(W_NS, "type"), "dxa")
        set_w(el, margin)


def set_fixed_table_width(tbl: etree._Element, widths: list[int]) -> None:
    tbl_pr = ensure_child(tbl, qn(W_NS, "tblPr"))
    tbl_w = tbl_pr.find(qn(W_NS, "tblW"))
    if tbl_w is None:
        tbl_w = etree.Element(qn(W_NS, "tblW"))
        tbl_pr.insert(0, tbl_w)
    tbl_w.set(qn(W_NS, "type"), "dxa")
    set_w(tbl_w, sum(widths))

    layout = tbl_pr.find(qn(W_NS, "tblLayout"))
    if layout is None:
        layout = etree.Element(qn(W_NS, "tblLayout"))
        tbl_pr.append(layout)
    layout.set(qn(W_NS, "type"), "fixed")

    old_grid = tbl.find(qn(W_NS, "tblGrid"))
    if old_grid is not None:
        tbl.remove(old_grid)
    grid = etree.Element(qn(W_NS, "tblGrid"))
    for width in widths:
        grid_col = etree.Element(qn(W_NS, "gridCol"))
        set_w(grid_col, width)
        grid.append(grid_col)
    tbl.insert(1 if tbl.find(qn(W_NS, "tblPr")) is not None else 0, grid)


def set_paragraph_spacing(paragraph: etree._Element, before: int = 0, after: int = 0) -> None:
    p_pr = ensure_child(paragraph, qn(W_NS, "pPr"))
    spacing = p_pr.find(qn(W_NS, "spacing"))
    if spacing is None:
        spacing = etree.Element(qn(W_NS, "spacing"))
        p_pr.append(spacing)
    spacing.set(qn(W_NS, "before"), str(before))
    spacing.set(qn(W_NS, "after"), str(after))


def set_font_size(node: etree._Element, half_points: int) -> None:
    for r in node.xpath(".//w:r", namespaces=NS):
        r_pr = r.find(qn(W_NS, "rPr"))
        if r_pr is None:
            r_pr = etree.Element(qn(W_NS, "rPr"))
            r.insert(0, r_pr)
        for tag in ("sz", "szCs"):
            size = r_pr.find(qn(W_NS, tag))
            if size is None:
                size = etree.Element(qn(W_NS, tag))
                r_pr.append(size)
            size.set(qn(W_NS, "val"), str(half_points))


def set_vertical_center(tc: etree._Element) -> None:
    tc_pr = ensure_child(tc, qn(W_NS, "tcPr"))
    v_align = tc_pr.find(qn(W_NS, "vAlign"))
    if v_align is None:
        v_align = etree.Element(qn(W_NS, "vAlign"))
        tc_pr.append(v_align)
    v_align.set(qn(W_NS, "val"), "center")


def set_text_align(tc: etree._Element, align: str) -> None:
    for p in tc.xpath(".//w:p", namespaces=NS):
        p_pr = ensure_child(p, qn(W_NS, "pPr"))
        jc = p_pr.find(qn(W_NS, "jc"))
        if jc is None:
            jc = etree.Element(qn(W_NS, "jc"))
            p_pr.append(jc)
        jc.set(qn(W_NS, "val"), align)
        set_paragraph_spacing(p, 0, 40)


def set_header_shading(row: etree._Element, fill: str) -> None:
    for tc in row.xpath("./w:tc", namespaces=NS):
        tc_pr = ensure_child(tc, qn(W_NS, "tcPr"))
        shd = tc_pr.find(qn(W_NS, "shd"))
        if shd is None:
            shd = etree.Element(qn(W_NS, "shd"))
            tc_pr.append(shd)
        shd.set(qn(W_NS, "fill"), fill)


def set_drawings_to_width(node: etree._Element, max_width_dxa: int) -> None:
    max_cx = dxa_to_emu(max_width_dxa)
    for inline in node.xpath(".//wp:inline", namespaces=NS):
        ext = inline.find(qn(WP_NS, "extent"))
        if ext is None:
            continue
        old_cx = int(ext.get("cx", "0") or 0)
        old_cy = int(ext.get("cy", "0") or 0)
        if not old_cx or not old_cy:
            continue
        cx = min(max_cx, old_cx if old_cx > max_cx else max_cx)
        cy = int(round(old_cy * (cx / old_cx)))
        ext.set("cx", str(cx))
        ext.set("cy", str(cy))
        for a_ext in inline.xpath(".//a:xfrm/a:ext", namespaces=NS):
            a_ext.set("cx", str(cx))
            a_ext.set("cy", str(cy))


def make_label_paragraph(text: str) -> etree._Element:
    p = etree.Element(qn(W_NS, "p"))
    p_pr = etree.SubElement(p, qn(W_NS, "pPr"))
    spacing = etree.SubElement(p_pr, qn(W_NS, "spacing"))
    spacing.set(qn(W_NS, "before"), "120")
    spacing.set(qn(W_NS, "after"), "80")
    r = etree.SubElement(p, qn(W_NS, "r"))
    r_pr = etree.SubElement(r, qn(W_NS, "rPr"))
    b = etree.SubElement(r_pr, qn(W_NS, "b"))
    b.set(qn(W_NS, "val"), "1")
    sz = etree.SubElement(r_pr, qn(W_NS, "sz"))
    sz.set(qn(W_NS, "val"), "20")
    t = etree.SubElement(r, qn(W_NS, "t"))
    t.text = text
    return p


def row_is_section(row: etree._Element) -> bool:
    texts = [text_of(tc) for _, _, tc in cell_infos(row)]
    non_empty = [t for t in texts if t]
    return len(non_empty) == 1 and "类" in non_empty[0]


def build_split_table(
    source_tbl: etree._Element,
    selected_cols: list[int],
    widths: list[int],
    picture_col_index: int | None,
    label: str,
) -> list[etree._Element]:
    new_tbl = copy.deepcopy(source_tbl)
    for tr in new_tbl.xpath("./w:tr", namespaces=NS):
        tr.getparent().remove(tr)

    set_fixed_table_width(new_tbl, widths)
    set_cell_margins(new_tbl, 100)

    source_rows = source_tbl.xpath("./w:tr", namespaces=NS)
    for row_idx, source_row in enumerate(source_rows):
        new_row = etree.Element(qn(W_NS, "tr"))
        infos = cell_infos(source_row)

        if row_is_section(source_row):
            first_text_cell = next(tc for _, _, tc in infos if text_of(tc))
            tc = copy.deepcopy(first_text_cell)
            set_grid_span(tc, len(selected_cols))
            set_cell_width(tc, sum(widths))
            set_vertical_center(tc)
            set_text_align(tc, "left")
            new_row.append(tc)
        else:
            cells_by_start = {start: tc for start, _, tc in infos}
            for out_idx, source_col in enumerate(selected_cols):
                source_tc = cells_by_start.get(source_col)
                tc = copy.deepcopy(source_tc) if source_tc is not None else etree.Element(qn(W_NS, "tc"))
                if not len(tc):
                    etree.SubElement(tc, qn(W_NS, "p"))
                clear_grid_span(tc)
                set_cell_width(tc, widths[out_idx])
                set_vertical_center(tc)
                set_text_align(tc, "center" if out_idx == 0 or source_col >= 3 else "left")
                if picture_col_index is not None and out_idx == picture_col_index:
                    set_drawings_to_width(tc, widths[out_idx] - 220)
                new_row.append(tc)

        if row_idx == 0:
            set_header_shading(new_row, "DDF4DA")
        set_font_size(new_row, 17)
        new_tbl.append(new_row)

    set_font_size(new_tbl, 17)
    return [make_label_paragraph(label), new_tbl]


def split_wide_table(
    tbl: etree._Element,
    core_cols: list[int],
    asset_cols: list[int],
    chunk_size: int,
    widths_for_count,
    picture_col_index: int | None,
    table_name: str,
) -> list[etree._Element]:
    chunks = [asset_cols[i : i + chunk_size] for i in range(0, len(asset_cols), chunk_size)]
    replacement: list[etree._Element] = []
    for idx, chunk in enumerate(chunks, start=1):
        selected = core_cols + chunk
        widths = widths_for_count(len(chunk))
        label = f"{table_name} - 续表 {idx}/{len(chunks)}（素材列 {chunk[0] + 1}-{chunk[-1] + 1}）"
        replacement.extend(build_split_table(tbl, selected, widths, picture_col_index, label))
    return replacement


def set_page_landscape(root: etree._Element) -> None:
    sect_pr = root.xpath("//w:body/w:sectPr", namespaces=NS)
    if not sect_pr:
        return
    sect = sect_pr[-1]
    pg_sz = sect.find(qn(W_NS, "pgSz"))
    if pg_sz is None:
        pg_sz = etree.Element(qn(W_NS, "pgSz"))
        sect.insert(0, pg_sz)
    # A4 landscape, in twentieths of a point.
    pg_sz.set(qn(W_NS, "w"), "16838")
    pg_sz.set(qn(W_NS, "h"), "11906")
    pg_sz.set(qn(W_NS, "orient"), "landscape")

    pg_mar = sect.find(qn(W_NS, "pgMar"))
    if pg_mar is None:
        pg_mar = etree.Element(qn(W_NS, "pgMar"))
        sect.insert(1, pg_mar)
    for side in ("top", "bottom", "left", "right"):
        pg_mar.set(qn(W_NS, side), "720")
    pg_mar.set(qn(W_NS, "header"), "360")
    pg_mar.set(qn(W_NS, "footer"), "360")
    pg_mar.set(qn(W_NS, "gutter"), "0")


def normalize_regular_tables(tables: list[etree._Element], usable_width: int) -> None:
    for tbl in tables[2:]:
        grid = tbl.xpath("./w:tblGrid/w:gridCol", namespaces=NS)
        if not grid:
            continue
        widths = [int(g.get(qn(W_NS, "w"), "0") or 0) for g in grid]
        total = sum(widths)
        if total <= 0:
            continue
        if total > usable_width:
            scale = usable_width / total
            widths = [max(420, int(w * scale)) for w in widths]
        set_fixed_table_width(tbl, widths)
        set_cell_margins(tbl, 90)
        set_font_size(tbl, 18)
        for row in tbl.xpath("./w:tr", namespaces=NS):
            for idx, tc in enumerate(row.xpath("./w:tc", namespaces=NS)):
                set_vertical_center(tc)
                set_text_align(tc, "center" if idx == 0 else "left")


def replace_table(tbl: etree._Element, replacement: list[etree._Element]) -> None:
    parent = tbl.getparent()
    index = parent.index(tbl)
    parent.remove(tbl)
    for offset, node in enumerate(replacement):
        parent.insert(index + offset, node)


def transform(input_path: Path, output_path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(input_path) as zin:
            zin.extractall(tmp_path)

        document_path = tmp_path / "word" / "document.xml"
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(str(document_path), parser)
        root = tree.getroot()

        set_page_landscape(root)
        tables = root.xpath("//w:tbl", namespaces=NS)
        normalize_regular_tables(tables, usable_width=15398)

        first_replacement = split_wide_table(
            tables[0],
            core_cols=[0, 1, 2],
            asset_cols=list(range(3, 25)),
            chunk_size=5,
            widths_for_count=lambda n: [760, 1800, 3500] + [1860] * n,
            picture_col_index=2,
            table_name="全部类目版本",
        )
        second_replacement = split_wide_table(
            tables[1],
            core_cols=[0, 1],
            asset_cols=list(range(2, 25)),
            chunk_size=5,
            widths_for_count=lambda n: [900, 3000] + [2280] * n,
            picture_col_index=None,
            table_name="跟据明星整理版本",
        )

        replace_table(tables[1], second_replacement)
        replace_table(tables[0], first_replacement)

        tree.write(str(document_path), xml_declaration=True, encoding="UTF-8", standalone=False)

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
    transform(args.input, args.out)


if __name__ == "__main__":
    main()
