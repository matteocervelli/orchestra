// Generated from Atrium apps/webapp/src/features/orchestra/repositoryFilter.ts.
// Source SHA-256: cd8a4b271bdfbc7478c6eca56a35a3843a22e1c524c48a30e349d088d40371ab
// TypeScript 5.9.3; target/module ES2022; strict; skipLibCheck. Do not edit.
// Closed presentation keys from Orchestra dashboard/common.py registered authorities.
const CANONICAL = [
    "app-himalaia", "app-ratio", "adlimen-ui", "claude-dotfiles", "nexus", "atrium",
    "orchestra", "adlimen-cicd", "adlimen-infra", "adlimen-harness", "adlimen-auth",
    "limen-assistant",
];
const registered = new Map([
    ...CANONICAL.map(name => [name, name]),
    ["himalaia", "app-himalaia"], ["ratio", "app-ratio"],
    ["adlimenui", "adlimen-ui"], ["dotfiles", "claude-dotfiles"],
    ...CANONICAL.map(name => [`matteocervelli/${name}`, name]),
]);
const keys = new Map([
    ...registered,
    ...[...registered].map(([key, value]) => [`${key}.`, value]),
]);
export const repositoryFilterKey = (value) => keys.get(value) ?? value;
export const repositoryFilters = (values) => [...new Set(values.map(repositoryFilterKey))];
/** Add a project match only for the complete, already normalized text query. */
export function matchesRepositoryQuery(repo, normalizedQuery) {
    const target = keys.get(normalizedQuery);
    return target !== undefined && repositoryFilterKey(repo ?? "") === target;
}
/** Present a copy after decoding; the source/cache item and nested evidence stay unchanged. */
export function projectRepository(item) {
    if (item.repo == null)
        return item;
    const repo = repositoryFilterKey(item.repo);
    return repo === item.repo ? item : { ...item, repo };
}
export function repositoryCounts(counts) {
    const projected = new Map();
    for (const [repo, count] of Object.entries(counts)) {
        const key = repositoryFilterKey(repo);
        projected.set(key, (projected.get(key) ?? 0) + count);
    }
    return Object.fromEntries(projected);
}
