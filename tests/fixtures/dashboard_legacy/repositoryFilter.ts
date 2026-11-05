// Closed presentation keys from Orchestra dashboard/common.py registered authorities.
const CANONICAL = [
  "app-himalaia", "app-ratio", "adlimen-ui", "claude-dotfiles", "nexus", "atrium",
  "orchestra", "adlimen-cicd", "adlimen-infra", "adlimen-harness", "adlimen-auth",
  "limen-assistant",
] as const;
const registered = new Map<string, string>([
  ...CANONICAL.map(name => [name, name] as const),
  ["himalaia", "app-himalaia"], ["ratio", "app-ratio"],
  ["adlimenui", "adlimen-ui"], ["dotfiles", "claude-dotfiles"],
  ...CANONICAL.map(name => [`matteocervelli/${name}`, name] as const),
]);
const keys = new Map([
  ...registered,
  ...[...registered].map(([key, value]) => [`${key}.`, value] as const),
]);

export const repositoryFilterKey = (value: string): string => keys.get(value) ?? value;
export const repositoryFilters = (values: readonly string[]): string[] =>
  [...new Set(values.map(repositoryFilterKey))];

/** Add a project match only for the complete, already normalized text query. */
export function matchesRepositoryQuery(repo: string | null | undefined, normalizedQuery: string): boolean {
  const target = keys.get(normalizedQuery);
  return target !== undefined && repositoryFilterKey(repo ?? "") === target;
}

/** Present a copy after decoding; the source/cache item and nested evidence stay unchanged. */
export function projectRepository<T extends { repo?: string | null | undefined }>(item: T): T {
  if (item.repo == null) return item;
  const repo = repositoryFilterKey(item.repo);
  return repo === item.repo ? item : { ...item, repo };
}

export function repositoryCounts(counts: Readonly<Record<string, number>>): Record<string, number> {
  const projected = new Map<string, number>();
  for (const [repo, count] of Object.entries(counts)) {
    const key = repositoryFilterKey(repo);
    projected.set(key, (projected.get(key) ?? 0) + count);
  }
  return Object.fromEntries(projected);
}
