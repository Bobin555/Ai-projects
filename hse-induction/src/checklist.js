export function createChecklist(ids) {
  const all = new Set(ids);
  const found = new Set();
  return {
    markFound(id) {
      if (!all.has(id) || found.has(id)) return false;
      found.add(id);
      return true;
    },
    found: () => found.size,
    total: () => all.size,
    isComplete: () => found.size === all.size,
    isFound: (id) => found.has(id),
  };
}
