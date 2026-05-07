from __future__ import annotations

from pathlib import Path

from support_app.repositories.faq_repository import FAQRepository
from support_app.repositories.json_file_repository import JsonFileRepository
from support_app.repositories.rule_repository import RuleRepository


class CategoryRepository:
    def __init__(self, path: Path, faq_repo: FAQRepository, rule_repo: RuleRepository):
        self.store = JsonFileRepository(path)
        self.faq_repo = faq_repo
        self.rule_repo = rule_repo

    def list_with_usage(self) -> list[dict]:
        names = self._load_names()
        faq_counts: dict[str, int] = {}
        rule_counts: dict[str, int] = {}

        for item in self.faq_repo.list():
            name = self._clean(item.get("category", ""))
            if name:
                faq_counts[name] = faq_counts.get(name, 0) + 1
                if name not in names:
                    names.append(name)

        for item in self.rule_repo.load(include_inactive=True):
            name = self._clean(item.get("category", ""))
            if name:
                rule_counts[name] = rule_counts.get(name, 0) + 1
                if name not in names:
                    names.append(name)

        return [
            {"name": name, "faq_count": faq_counts.get(name, 0), "rule_count": rule_counts.get(name, 0)}
            for name in names
        ]

    def create(self, name: str) -> list[dict]:
        clean_name = self._clean(name)
        if not clean_name:
            raise ValueError("分类名称不能为空")

        names = self._load_names()
        if clean_name.lower() not in {item.lower() for item in names}:
            names.append(clean_name)
            self._save_names(names)
        return self.list_with_usage()

    def delete(self, name: str) -> list[dict]:
        target = self._clean(name)
        items = self.list_with_usage()
        matched = next((item for item in items if item["name"].lower() == target.lower()), None)
        if not matched:
            raise KeyError("分类不存在")
        if matched["faq_count"] or matched["rule_count"]:
            raise ValueError(f"该分类正在被 {matched['faq_count']} 条 FAQ、{matched['rule_count']} 条规则使用，不能删除")

        names = [item for item in self._load_names() if item.lower() != target.lower()]
        self._save_names(names)
        return self.list_with_usage()

    def _load_names(self) -> list[str]:
        data = self.store.load_object()
        raw_items = data.get("items", []) if isinstance(data, dict) else []
        result = []
        seen = set()
        for item in raw_items:
            name = self._clean(item)
            if name and name.lower() not in seen:
                seen.add(name.lower())
                result.append(name)
        return result

    def _save_names(self, names: list[str]) -> None:
        self.store.save_object({"items": names})

    @staticmethod
    def _clean(value: object) -> str:
        return str(value or "").strip()
