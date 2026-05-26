from __future__ import annotations

import argparse
import tempfile
import zipfile
from pathlib import Path

from lxml import etree


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docx", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(args.docx) as zin:
            zin.extractall(tmp_path)

        changed = 0
        for rels_path in tmp_path.rglob("*.rels"):
            parser_xml = etree.XMLParser(remove_blank_text=False)
            tree = etree.parse(str(rels_path), parser_xml)
            for rel in tree.getroot().findall(f"{{{REL_NS}}}Relationship"):
                target = rel.get("Target", "")
                if target.endswith(".webloc"):
                    rel.set("Target", target[:-7] + ".mp4")
                    changed += 1
            tree.write(str(rels_path), xml_declaration=True, encoding="UTF-8", standalone=False)

        if args.out.exists():
            args.out.unlink()
        with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as zout:
            for path in tmp_path.rglob("*"):
                if path.is_file():
                    zout.write(path, path.relative_to(tmp_path).as_posix())
    print(f"updated_links={changed}")


if __name__ == "__main__":
    main()
