import type { CategoryKind, CategoryTree } from "../api/client";

export type CategoryInfo = {
  id: number;
  name: string;
  label: string; // "Food › Groceries" for a subcategory, "Food" for a top-level one
  kind: CategoryKind;
  parentId: number | null;
};

/** Every category (top-level and sub) by id, with a display label. */
export function indexCategories(tree: CategoryTree[]): Map<number, CategoryInfo> {
  const index = new Map<number, CategoryInfo>();
  for (const top of tree) {
    index.set(top.id, { id: top.id, name: top.name, label: top.name, kind: top.kind, parentId: null });
    for (const sub of top.subcategories) {
      index.set(sub.id, {
        id: sub.id,
        name: sub.name,
        label: `${top.name} › ${sub.name}`,
        kind: sub.kind,
        parentId: top.id,
      });
    }
  }
  return index;
}

/** Categories of one kind in tree order (each parent followed by its subcategories), for <select>s. */
export function categoryOptions(tree: CategoryTree[], kind: CategoryKind): CategoryInfo[] {
  const index = indexCategories(tree);
  return tree
    .filter((top) => top.kind === kind)
    .flatMap((top) => [top.id, ...top.subcategories.map((sub) => sub.id)])
    .map((id) => index.get(id) as CategoryInfo);
}
