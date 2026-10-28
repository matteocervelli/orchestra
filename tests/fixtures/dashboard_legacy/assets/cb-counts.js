// Card totals describe unfinished work. Status counters retain their historical totals.
export const countable = (it) => !it?.hidden && !["Deployed", "Dropped"].includes(it?.status);
export const cardCount = (items, facet = null) =>
  items.filter(it => facet === "status" ? !it.hidden : countable(it)).length;
